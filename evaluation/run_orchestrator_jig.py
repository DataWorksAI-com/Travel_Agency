"""Black-box scoring loop for the orchestrator.

Ported from budget_agent_rohan/evaluation/run_jig.py, which scores one agent.
This scores the *coordination* instead, so the questions are different:

  coverage     did it call the agents this request needed?
  propagation  did the resolved city actually reach the agents downstream?
  honesty      when an agent had no data, does the final itinerary say so --
               or does it read as though the section were answered?
  grounding    every dollar figure in the final text must appear in some
               agent's reply. Ground truth is harvested from the run itself,
               not typed here, so it cannot drift from what the agents did.

Scores are kept separate and never blended, for the same reason the budget jig
keeps them separate: a run can be perfectly honest and still have skipped an
agent, and averaging the two hides both.

`propagation` is the measurement worth having. The deterministic orchestrator
computes a resolved city and never passes it on (orchestrator.py:174-176), so it
scores 0 on that column by construction, while the agentic one can score 1. That
is the difference between the two designs, expressed as a number rather than an
anecdote.

Usage
    python evaluation/run_orchestrator_jig.py                    # both, 1 run
    python evaluation/run_orchestrator_jig.py --runs 3           # variance
    python evaluation/run_orchestrator_jig.py --orchestrators agent
    python evaluation/run_orchestrator_jig.py --cases rome,tokyo

Set TRAVEL_UI_AGENTS before running. With every slot on `dummy` this costs
nothing and still measures coverage and propagation honestly -- but the honesty
column is meaningless, because a stand-in never reports a coverage gap.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Same two lines app.py runs, and for the same reasons: truststore must be
# injected before requests is imported or HTTPS hangs ~5 minutes behind the
# intercepting proxy, and the agents need the keys from .env.
import truststore  # noqa: E402

truststore.inject_into_ssl()

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

RESULTS_DIR = Path(__file__).resolve().parent / "results"
MONEY_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*(?:USD|dollars)", re.I)
MONEY_FLOOR = 10


# --- cases -----------------------------------------------------------------
# `expect_called`  slots this request genuinely needs.
# `city_reaches`   the resolved city must appear in these slots' task strings.
# `must_say`       phrases the final itinerary must contain, lowercased.
# `must_not_say`   phrases that would mean an uncovered gap was papered over.

CASES = {
    "cancun": {
        "request": "Plan a week in Cancún from Boston in September, budget $3000",
        "expect_called": ["destination", "flights", "restaurants", "activities", "budget", "money_customs"],
        "city_reaches": ["flights", "restaurants", "activities", "budget"],
        "must_say": ["cancún"],
        "must_not_say": [],
        "note": "Best coverage available: 5 of 6 agents hold real data.",
    },
    "rome": {
        "request": "Plan a week in Rome from Boston in September, budget $3000",
        "expect_called": ["destination", "flights", "restaurants", "activities", "budget", "money_customs"],
        "city_reaches": ["flights", "restaurants", "activities", "budget"],
        # Restaurants holds 6 Caribbean cities and Money & Customs 17 countries,
        # neither including Rome or Italy. Both gaps must survive into the text.
        "must_say": ["rome"],
        "must_not_say": ["bali", "cancun cost", "germany", "german"],
        "expect_gap": ["restaurants", "money_customs", "budget"],
        "note": "Mirror of cancun: Activities has curated data, Restaurants/Budget/Money do not.",
    },
    "tokyo": {
        "request": "Plan a week in Tokyo from Boston in September, budget $3000",
        "expect_called": ["destination", "flights", "restaurants", "activities", "budget", "money_customs"],
        "city_reaches": ["flights", "restaurants", "activities", "budget"],
        "must_say": ["tokyo"],
        "must_not_say": ["aruba", "bali", "cancun"],
        "expect_gap": ["restaurants", "activities", "budget"],
        "note": "Three agents uncovered. Japan IS in Money & Customs' 17.",
    },
    "aruba": {
        "request": "Plan a week in Aruba from Boston in September, budget $2500",
        "expect_called": ["destination", "flights", "restaurants", "activities", "budget", "money_customs"],
        "city_reaches": ["flights", "restaurants", "activities", "budget"],
        "must_say": ["aruba"],
        # Aruba is absent from Budget's 15 cities and Money & Customs' 17, and
        # its OpenTripMap geoname collides with a town in Italy.
        "must_not_say": ["italy", "piedmont", "castle", "bali"],
        "expect_gap": ["budget", "money_customs"],
        "note": "Worst case: 3 of 6. Also the Aruba/Italy geocode collision.",
    },
    "vague": {
        "request": "Plan a week somewhere warm from Boston in September, budget $3000",
        "expect_called": ["destination"],
        "city_reaches": ["flights", "restaurants", "activities"],
        "must_say": [],
        "must_not_say": ["somewhere warm to"],
        "note": "The propagation case. No city is named, so only Destination can "
                "resolve one -- and the fixed pipeline cannot pass it on.",
    },
    "accent": {
        "request": "Plan a week in Cancun from Boston in September, budget $3000",
        "expect_called": ["destination", "flights", "restaurants", "activities", "budget", "money_customs"],
        "city_reaches": ["flights", "restaurants", "activities", "budget"],
        "must_say": [],
        # Unaccented spelling used to geocode to Guangxi, China and get written
        # into the committed RAG corpus.
        "must_not_say": ["china", "guangxi", "asia"],
        "note": "Regression guard for the accent-fold fix in resolve_place.",
    },
}


# --- scoring ---------------------------------------------------------------

def money_in(text: str) -> set[int]:
    """Every plausible dollar figure stated in a piece of text."""
    found: set[int] = set()
    for m in MONEY_RE.finditer(text or ""):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        try:
            val = int(float(raw))
        except (TypeError, ValueError):
            continue
        if val >= MONEY_FLOOR:
            found.add(val)
    return found


def resolved_city(calls: list[dict]) -> str:
    """The city the run settled on, read from the destination reply.

    Deliberately crude: the point is not to parse the reply perfectly, only to
    find a token specific enough to look for in the downstream task strings.
    """
    for c in calls:
        if c["slot"] == "destination":
            for line in (c["reply"] or "").splitlines():
                m = re.search(r"(?:destination|city)\s*[:\-]\s*\*{0,2}([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' .\-]{2,30})", line, re.I)
                if m:
                    return m.group(1).strip(" *.,")
    return ""


def score(case: dict, final: str, calls: list[dict]) -> dict:
    low = (final or "").lower()
    called = [c["slot"] for c in calls]
    failures: list[str] = []

    # coverage -- read from the ledger, not from the text, because a model will
    # happily write a section for an agent it never called.
    expected = case["expect_called"]
    missing = [s for s in expected if s not in called]
    coverage = (len(expected) - len(missing)) / len(expected) if expected else 1.0
    if missing:
        failures.append("never called: " + ",".join(missing))

    # propagation -- did the resolved city reach the agents that need it?
    city = resolved_city(calls)
    downstream = [s for s in case["city_reaches"] if s in called]
    if not city:
        propagation = 0.0
        failures.append("no city resolved from destination's reply")
    elif not downstream:
        propagation = 0.0
        failures.append("no downstream agent was called to receive the city")
    else:
        got = [c["slot"] for c in calls
               if c["slot"] in downstream and city.lower() in (c["task"] or "").lower()]
        propagation = len(set(got)) / len(set(downstream))
        blind = sorted(set(downstream) - set(got))
        if blind:
            failures.append(f"city {city!r} never reached: " + ",".join(blind))

    # honesty
    for phrase in case["must_say"]:
        if phrase.lower() not in low:
            failures.append(f"missing {phrase!r}")
    for phrase in case["must_not_say"]:
        if phrase.lower() in low:
            failures.append(f"said {phrase!r}")
    for slot in case.get("expect_gap", []):
        if slot in called:
            reply_low = " ".join(c["reply"].lower() for c in calls if c["slot"] == slot)
            agent_admitted = any(k in reply_low for k in (
                "no data", "not available", "outside", "coverage", "hold no",
                "could not find", "not found", "not present", "no cached"))
            if agent_admitted and not any(k in low for k in (
                    "no data", "not available", "coverage", "unavailable",
                    "not found", "no restaurant", "estimate", "not in the")):
                failures.append(f"{slot} reported a gap the itinerary does not mention")
    honesty = 1.0 if not any(
        f.startswith(("missing", "said")) or "does not mention" in f for f in failures) else 0.0

    # grounding -- every figure in the final text must appear in some reply.
    from_agents: set[int] = set()
    for c in calls:
        from_agents |= money_in(c["reply"])
    fabricated = sorted(money_in(final) - from_agents)
    grounding = 1.0 if not fabricated else 0.0

    return {
        "coverage": round(coverage, 3),
        "propagation": round(propagation, 3),
        "honesty": honesty,
        "grounding": grounding,
        # NOT "case": row below sets "case" to the case NAME, and **s would
        # overwrite it with this score, losing the name from the CSV.
        "passed": 1.0 if (coverage == 1.0 and propagation == 1.0
                          and honesty == 1.0 and grounding == 1.0) else 0.0,
        "resolved_city": city,
        "calls": ",".join(called),
        "fabricated": ",".join(str(v) for v in fabricated),
        "failures": "; ".join(failures),
    }


# --- runner ----------------------------------------------------------------

async def run_once(request: str, orchestrator_mode: str) -> tuple[str, list[dict]]:
    """One planning run, with every subagent call recorded through the seam."""
    # plan_trip reads this on every call, so no module reload is needed -- and
    # reloading would drop orchestrator_config's client cache, rebuilding every
    # subagent (Destination constructs its model at import) once per run.
    os.environ["TRAVEL_UI_ORCHESTRATOR"] = orchestrator_mode

    import orchestrator
    from ui.agent_seam import install_seam
    from ui.request_parse import parse_request

    calls: list[dict] = []

    async def after(slot, mode, task, reply, elapsed):
        calls.append({"slot": slot, "mode": mode, "task": task,
                      "reply": reply, "elapsed": elapsed})

    install_seam(after=after)
    parsed = parse_request(request)
    final = await orchestrator.plan_trip(
        task=parsed["task"],
        origin_country=parsed["origin_country"],
        destination_country=parsed["destination_country"],
        stated_budget=parsed["stated_budget"],
    )
    return (final if isinstance(final, str) else str(final)), calls


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=1, help="repeats per case, for variance")
    p.add_argument("--cases", default="", help="comma-separated subset of case names")
    p.add_argument("--orchestrators", default="agent,deterministic")
    p.add_argument("--label", default="orchestrator")
    args = p.parse_args()

    names = [c.strip() for c in args.cases.split(",") if c.strip()] or list(CASES)
    unknown = [n for n in names if n not in CASES]
    if unknown:
        print(f"unknown case(s): {', '.join(unknown)}. Known: {', '.join(CASES)}")
        return 2
    modes = [m.strip() for m in args.orchestrators.split(",") if m.strip()]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    print(f"cases={','.join(names)}  orchestrators={','.join(modes)}  runs={args.runs}")
    print(f"TRAVEL_UI_AGENTS={os.environ.get('TRAVEL_UI_AGENTS', '(unset -> all dummy)')}\n")

    for mode in modes:
        for name in names:
            case = CASES[name]
            per_case: list[dict] = []
            for attempt in range(args.runs):
                started = time.perf_counter()
                try:
                    final, calls = asyncio.run(run_once(case["request"], mode))
                    err = ""
                except Exception as exc:               # a crash is a result too
                    final, calls, err = "", [], f"{type(exc).__name__}: {exc}"
                elapsed = time.perf_counter() - started

                s = score(case, final, calls) if not err else {
                    "coverage": 0.0, "propagation": 0.0, "honesty": 0.0,
                    "grounding": 0.0, "passed": 0.0, "resolved_city": "",
                    "calls": "", "fabricated": "", "failures": err,
                }
                row = {"orchestrator": mode, "case": name, "run": attempt + 1,
                       "seconds": round(elapsed, 1), **s, "final": final}
                rows.append(row)
                per_case.append(s)
                flag = "ok " if s["passed"] == 1.0 else "FAIL"
                # flush: a full matrix takes ~40 minutes, and without this the
                # rows sit in a buffer until the end whenever stdout is not a
                # TTY -- which makes a working run look like a hung one.
                print(f"  [{flag}] {mode:<13} {name:<8} run {attempt + 1}  "
                      f"cov={s['coverage']} prop={s['propagation']} "
                      f"hon={s['honesty']} grd={s['grounding']}  {elapsed:5.1f}s"
                      + (f"  -- {s['failures']}" if s["failures"] else ""),
                      flush=True)

            if args.runs > 1 and len({x["passed"] for x in per_case}) > 1:
                print(f"       ^ INCONSISTENT across runs: {[x['passed'] for x in per_case]}", flush=True)

    # --- summary
    print("\n" + "=" * 74)
    summary: dict = {}
    for mode in modes:
        mine = [r for r in rows if r["orchestrator"] == mode]
        if not mine:
            continue
        summary[mode] = {
            k: round(statistics.mean(r[k] for r in mine), 3)
            for k in ("coverage", "propagation", "honesty", "grounding", "passed")
        }
        summary[mode]["median_seconds"] = round(statistics.median(r["seconds"] for r in mine), 1)
        summary[mode]["runs"] = len(mine)

    hdr = f"{'orchestrator':<15}{'coverage':>10}{'propagation':>13}{'honesty':>9}{'grounding':>11}{'passed':>7}{'median s':>10}"
    print(hdr)
    print("-" * len(hdr))
    for mode, s in summary.items():
        print(f"{mode:<15}{s['coverage']:>10}{s['propagation']:>13}{s['honesty']:>9}"
              f"{s['grounding']:>11}{s['passed']:>7}{s['median_seconds']:>10}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = RESULTS_DIR / f"{args.label}_{stamp}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    json_path = RESULTS_DIR / f"{args.label}_{stamp}.json"
    json_path.write_text(json.dumps(
        {"summary": summary, "agents": os.environ.get("TRAVEL_UI_AGENTS", ""),
         "orchestrator_model": os.environ.get("ORCHESTRATOR_MODEL", ""),
         "cases": names, "runs": args.runs}, indent=2), encoding="utf-8")

    print(f"\nrows:    {csv_path}")
    print(f"summary: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
