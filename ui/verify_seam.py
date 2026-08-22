"""
ui/verify_seam.py -- prove the seam's guarantees without a browser.

What this checks, and why each matters for the UI:

  1. plan_trip runs end to end through the seam with no key and no
     exception (acceptance #2, #3).
  2. Every slot fires and is observable through the `after` hook -- this is
     the same hook app.py turns into Chainlit steps (acceptance #4).
  3. No reply reaching the UI is an error string. Specifically, an
     UNCONNECTED agent put in REAL mode degrades to its stand-in instead of
     "[flights unavailable] ..." (orchestrator_config.py:122) or
     "[subagent error] ..." (subagent_client.py:98) -- acceptance #5.
  4. Budget's own refusal paths render as ordinary prose, not a crash.

Run:  python ui/verify_seam.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import orchestrator  # noqa: E402
from ui.agent_seam import LABELS, REAL, install_seam  # noqa: E402
from ui.request_parse import parse_request  # noqa: E402

ERROR_SHAPES = ("[subagent error]", "unavailable]", "unreachable")

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def rule(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


async def run_case(request: str, overrides: dict | None = None) -> tuple[str, list]:
    observed: list[tuple[str, str, str]] = []

    async def after(slot, effective_mode, task, reply):
        observed.append((slot, effective_mode, reply))

    install_seam(after=after, overrides=overrides)

    parsed = parse_request(request)
    final = await orchestrator.plan_trip(
        task=parsed["task"],
        origin_country=parsed["origin_country"],
        destination_country=parsed["destination_country"],
        stated_budget=parsed["stated_budget"],
    )
    return final, observed


def report(request, overrides, final, observed) -> None:
    print(f"\n  request   : {request}")
    print(f"  overrides : {overrides or '(defaults)'}")
    print(f"  slots seen: {[s for s, _, _ in observed]}")
    for slot, mode, reply in observed:
        first = reply.splitlines()[0] if reply.splitlines() else ""
        print(f"    {LABELS.get(slot, slot):<16} [{mode:<6}] {first[:88]}")

    check(
        "all six slots reported through the hook",
        {s for s, _, _ in observed} == set(LABELS),
        f"{len(observed)} calls",
    )
    for slot, _, reply in observed:
        head = reply.lstrip()[:160]
        leaked = head.startswith("[") and any(m in head for m in ERROR_SHAPES)
        check(f"{slot}: no error string reaches the UI", not leaked, head[:70])
    check("final itinerary is non-empty text", bool(final and final.strip()))
    for shape in ERROR_SHAPES:
        check(f"assembled plan is free of '{shape}'", shape not in final)


async def main() -> int:
    # -- Case 1: the happy path, defaults (everything unconnected -> stand-in,
    #    Budget on its real no-LLM direct path).
    rule("CASE 1 -- happy path, default modes")
    request = "Plan a week in Aruba from Boston, budget $3000"
    final, observed = await run_case(request)
    report(request, None, final, observed)
    print("\n  --- assembled plan ---")
    for line in final.splitlines():
        print(f"    {line}")

    # -- Case 2: put two UNCONNECTED agents in REAL mode. Their real builders
    #    cannot import (deps/keys absent by design on the fakes path), so the
    #    seam must fall back to the stand-in rather than surface the
    #    "[... unavailable]" / "[subagent error]" strings.
    rule("CASE 2 -- unconnected agents forced to REAL: must degrade to stand-in")
    overrides = {"flights": REAL, "restaurants": REAL, "destination": REAL}
    final2, observed2 = await run_case(request, overrides)
    report(request, overrides, final2, observed2)
    forced = {s: m for s, m, _ in observed2 if s in overrides}
    check(
        "each forced-real unconnected agent reported effective mode 'dummy'",
        all(m == "dummy" for m in forced.values()),
        str(forced),
    )

    # -- Case 3: Budget's refusal paths, rendered directly. These are the
    #    "legitimately refuses" cases: they must be prose, not exceptions.
    rule("CASE 3 -- Budget's refusal paths are prose, not crashes")
    from evaluation.direct_path import render

    for label, task in (
        ("covered=False (uncovered destination)",
         "Plan a 5 night trip to Lisbon, Portugal, budget $2500"),
        ("missing budget / length",
         "Plan a trip to Aruba"),
    ):
        try:
            out = render(task)
            ok = isinstance(out, str) and bool(out.strip())
        except Exception as exc:  # noqa: BLE001
            out, ok = f"RAISED {exc!r}", False
        check(f"{label}: returns prose", ok)
        print(f"        {out[:150]}")

    rule("RESULT")
    if FAILURES:
        print(f"  {len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("  all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
