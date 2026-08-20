"""
run_jig.py — black-box scoring loop for budget agents.

Runs every case N times against a target agent and scores three things
separately, following DeepPlanning (arXiv 2601.18137): a plan can satisfy
most individual constraints and still be worthless, because one wrong number
invalidates the whole answer. Reporting a single blended number hides that.

    behaviour   did it say the right kind of thing (status, refusal, scope)
    grounding   is every dollar figure it stated traceable to a tool result
    case        1 only if both are perfect

The grounding score exists because of a real observation: with correct tool
output in hand, the agent still narrated "the remaining budget of $952",
a figure no tool produced. Deterministic tools stop the TOOL being wrong.
They do not stop the narration layer inventing numbers on top.

BLACK BOX. The target is either an importable callable or a shell command.
The command form is what lets this score a teammate's agent without knowing
anything about its internals.

KNOWN LIMITATIONS, found by running it (18 Aug 2026, n=1):

1. must_say is a substring match, so it penalises correct answers phrased
   differently. "feasible, but lodging must be at or below $74" IS the
   constrained answer; it failed only for not containing "constrain".
   Fix: assert on the number and the absence of a refusal, not a keyword.

2. The grounding check only sees NUMBERS. In the same reply the agent said
   "covers meals and activities" when activities were allocated $0, and
   "without any reserve left" when the $200 reserve was untouched. Both
   false, both invisible here. Qualitative claims about quantities are
   currently unscored.

Both are recorded rather than patched, because tightening an assertion after
seeing the result it produced makes the number meaningless.

Usage
-----
    python evaluation/run_jig.py --runs 3
    python evaluation/run_jig.py --runs 3 --target "python -m budget_agent.agent --task {task}"
    python evaluation/run_jig.py --runs 1 --target "python ../budget_agent/scripts/run_agent.py --task {task}"
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.cases import CASES  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Ignore small integers when hunting for fabricated money: they are usually
# night counts, traveller counts or list numbering, not dollar claims.
MONEY_FLOOR = 50

MONEY_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)|\b([\d,]{3,})\b")


def money_in(text: str) -> set[int]:
    """Every plausible dollar figure stated in a reply."""
    found: set[int] = set()
    for m in MONEY_RE.finditer(text):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        if not raw:
            continue
        try:
            val = int(float(raw))
        except ValueError:
            continue
        if val >= MONEY_FLOOR:
            found.add(val)
    return found


# --- targets ---------------------------------------------------------------

def local_target():
    """Our own agent, in-process. Builds the model once and reuses it."""
    from budget_agent.agent import ask, build_agent
    agent = build_agent()
    return lambda task: ask(agent, task)


def command_target(template: str):
    """Any agent, as a subprocess. This is the true black box."""
    def run(task: str) -> str:
        cmd = template.replace("{task}", task)
        proc = subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip()[-400:] or "non-zero exit")
        return proc.stdout.strip()
    return run


# --- scoring ---------------------------------------------------------------

def score(case: dict, reply: str) -> dict:
    low = reply.lower()
    failures: list[str] = []

    for phrase in case["must_say"]:
        if phrase.lower() not in low:
            failures.append(f"missing {phrase!r}")
    for phrase in case["must_not_say"]:
        if phrase.lower() in low:
            failures.append(f"said {phrase!r}")

    refused = "not covered" in low or "no published" in low
    if case["expect_refuse"] and not refused:
        failures.append("did not refuse an out-of-scope destination")
    if not case["expect_refuse"] and refused:
        failures.append("refused a covered destination")

    behaviour = 1.0 if not failures else 0.0

    stated = money_in(reply)
    fabricated = sorted(stated - set(case["allowed_money"]))
    grounding = 1.0 if not fabricated else 0.0

    return {
        "behaviour": behaviour,
        "grounding": grounding,
        "case": 1.0 if behaviour == 1.0 and grounding == 1.0 else 0.0,
        "failures": "; ".join(failures),
        "fabricated": ",".join(str(v) for v in fabricated),
        "stated_money": ",".join(str(v) for v in sorted(stated)),
    }


# --- runner ----------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", type=int, default=3,
                   help="repeats per case; >1 exposes run-to-run variance")
    p.add_argument("--target", default=None,
                   help="shell command with {task}; omit to use our agent")
    p.add_argument("--label", default=None, help="name for the results file")
    args = p.parse_args()

    invoke = command_target(args.target) if args.target else local_target()
    label = args.label or ("command" if args.target else "local")

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rows: list[dict] = []

    print(f"{len(CASES)} cases x {args.runs} runs = "
          f"{len(CASES) * args.runs} invocations\n")

    for case in CASES:
        marks = []
        for run in range(args.runs):
            started = time.time()
            try:
                reply = invoke(case["task"])
                res = score(case, reply)
                err = ""
            except Exception as exc:                  # noqa: BLE001
                reply, err = "", str(exc)[:300]
                res = {"behaviour": 0.0, "grounding": 0.0, "case": 0.0,
                       "failures": f"ERROR: {err}", "fabricated": "",
                       "stated_money": ""}
            elapsed = round(time.time() - started, 1)
            marks.append(res["case"])
            rows.append({"case_id": case["id"], "run": run + 1,
                         "seconds": elapsed, **res,
                         "task": case["task"], "reply": reply})

            flag = "ok " if res["case"] else "FAIL"
            detail = res["failures"] or (
                f"fabricated {res['fabricated']}" if res["fabricated"] else "")
            print(f"  {flag} {case['id']:<24} run {run + 1} "
                  f"{elapsed:>5}s  {detail}")

        if args.runs > 1 and len(set(marks)) > 1:
            print(f"       ^ INCONSISTENT across runs: {marks}")

    # --- summary ---
    def mean(key: str) -> float:
        return statistics.mean(r[key] for r in rows) if rows else 0.0

    summary = {
        "label": label,
        "timestamp": stamp,
        "cases": len(CASES),
        "runs_per_case": args.runs,
        "invocations": len(rows),
        "behaviour_score": round(mean("behaviour"), 3),
        "grounding_score": round(mean("grounding"), 3),
        "case_accuracy": round(mean("case"), 3),
        "median_seconds": round(statistics.median(
            r["seconds"] for r in rows), 1) if rows else 0,
        "fabrication_rate": round(
            sum(1 for r in rows if r["fabricated"]) / len(rows), 3)
        if rows else 0,
    }

    csv_path = RESULTS_DIR / f"{label}_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (RESULTS_DIR / f"{label}_{stamp}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    for k, v in summary.items():
        print(f"  {k:<20} {v}")
    print("=" * 60)
    print(f"\nrows: {csv_path}")
    print("\nbehaviour = right kind of answer")
    print("grounding = every dollar figure traceable to a tool")
    print("case      = both perfect. This is the honest number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
