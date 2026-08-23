"""
ui/verify_seam.py -- prove the seam's guarantees without a browser.

What this checks, and why each matters for the UI:

  1. plan_trip runs end to end through the seam with no key and no
     exception (acceptance #2, #3).
  2. Every slot fires and is observable through the `after` hook -- this is
     the same hook app.py turns into Chainlit steps (acceptance #4).
  3. An UNCONNECTED agent put in REAL mode reports FAILED and says so,
     rather than quietly becoming a stand-in. This inverts what this file
     used to assert. The old guarantee was "no slot ever shows a problem";
     the new one is "no slot ever hides one". Two halves:
       (a) the raw internal shapes still must not leak --
           "[flights unavailable] ..." (orchestrator_config.py:130),
           "[subagent error] ..." (subagent_client.py:98) -- they are
           reworded into a cause;
       (b) a failed slot must NOT return that slot's stand-in text, which
           is the specific substitution that made an all-fake itinerary
           look like a real one.

Every slot is a stand-in by default now, including budget: the budget slot's
real path is Shashank's repo-root RAG agent (orchestrator_config.py:
_build_budget_client), which needs deps, a key and a built vectorstore.

Run:  python ui/verify_seam.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import orchestrator  # noqa: E402
from ui.agent_seam import (  # noqa: E402
    DUMMY,
    ENV_VAR,
    FAILED,
    LABELS,
    REAL,
    _dummy_reply,
    install_seam,
)
from ui.request_parse import parse_request  # noqa: E402

ERROR_SHAPES = ("[subagent error]", "unavailable]", "unreachable")

# Captured at import, before any case mutates it. resolve_modes()
# (agent_seam.py:140-148) reads TRAVEL_UI_AGENTS straight off the process
# environment, so a value left in the caller's shell silently changed what
# this harness ran while it still printed "(defaults)" -- it reported a
# condition it was not testing. Each case now pins the var explicitly and
# restores this afterwards, so results do not depend on the shell.
_AMBIENT = os.environ.get(ENV_VAR)

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        FAILURES.append(label)


def rule(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


async def run_case(
    request: str,
    overrides: dict | None = None,
    env: str | None = None,
) -> tuple[str, list, dict]:
    """Run one case under a PINNED environment.

    `env` is the TRAVEL_UI_AGENTS value this case is meant to run under --
    None means "the var must be absent". Either way the caller's original
    value is restored afterwards, so running the harness never mutates the
    shell it was launched from.

    Returns the resolved modes alongside the results, so the report can
    print the condition that actually ran rather than the argument that
    was passed in.
    """
    observed: list[tuple[str, str, str]] = []

    async def after(slot, effective_mode, task, reply):
        observed.append((slot, effective_mode, reply))

    prior = os.environ.get(ENV_VAR)
    if env is None:
        os.environ.pop(ENV_VAR, None)
    else:
        os.environ[ENV_VAR] = env
    try:
        modes = install_seam(after=after, overrides=overrides)

        parsed = parse_request(request)
        final = await orchestrator.plan_trip(
            task=parsed["task"],
            origin_country=parsed["origin_country"],
            destination_country=parsed["destination_country"],
            stated_budget=parsed["stated_budget"],
        )
    finally:
        if prior is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = prior
    return final, observed, modes


def report(request, modes, final, observed) -> None:
    print(f"\n  request   : {request}")
    # The RESOLVED modes, not the overrides argument: what ran, not what
    # was asked for. These diverge whenever MODES or the env var contributes,
    # which is exactly the case that used to print a misleading "(defaults)".
    print(f"  resolved  : {modes}")
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
    #    every slot including budget on its stand-in).
    # Ambient config that gets silently discarded is the same hazard as
    # ambient config that silently applies -- say which one happened.
    if _AMBIENT is not None:
        rule("ENVIRONMENT")
        print(f"  {ENV_VAR} was set in the environment: {_AMBIENT!r}")
        print("  OVERRIDDEN -- each case pins this var to its own value so")
        print("  results do not depend on the calling shell. Your value is")
        print("  restored when the harness exits.")

    rule("CASE 1 -- happy path, default modes")
    request = "Plan a week in Aruba from Boston, budget $3000"
    final, observed, modes = await run_case(request, env=None)
    report(request, modes, final, observed)
    print("\n  --- assembled plan ---")
    for line in final.splitlines():
        print(f"    {line}")

    # -- Case 2: put UNCONNECTED agents in REAL mode. Their real builders
    #    cannot import (deps/keys absent by design on the fakes path), so
    #    each must report FAILED and carry its cause -- NOT quietly become
    #    a stand-in, which is what this case used to assert.
    rule("CASE 2 -- forced REAL: per-slot expected effective mode")
    overrides = {"flights": REAL, "restaurants": REAL, "destination": REAL}
    final2, observed2, modes2 = await run_case(request, overrides, env=None)
    report(request, modes2, final2, observed2)
    forced = {s: m for s, m, _ in observed2 if s in overrides}

    # WHY THIS EXPECTATION CHANGED.
    #
    # This used to assert a universal: "every forced-real agent reports
    # dummy". That held only while NO agent was connected. It is now false,
    # so the assertion is per-slot and each entry states its own reason.
    # This test is SUPPOSED to fail loudly the moment a slot's liveness
    # changes -- that is the signal, not the noise. When one flips, update
    # the map and the reason, do not relax the check.
    #
    #   destination -> FAILED: genuinely unconnected. Its builder needs
    #       ANTHROPIC_API_KEY, absent by design on this path, so the real
    #       call returns "[subagent error] Anthropic authentication failed".
    #       That used to become a stand-in; it is now surfaced as a cause.
    #   restaurants -> REAL: went live on the local Ollama RAG path
    #       (restaurant_agent/restaurant_agent_ollama.py). Note it answers
    #       retrieval-only when the Ollama tag at that file's line 36 is not
    #       pulled -- still REAL, the seam only cares that it came back
    #       usable, not which internal path produced it.
    #   flights -> FAILED, but NOT because it is unconnected. It is wired and
    #       working (flights_agent.py:184 pins a free OpenRouter model). It
    #       fails only while the free tier's daily quota is spent:
    #       "[subagent error] Rate limit exceeded: free-models-per-day".
    #       So this entry is QUOTA-DEPENDENT and will legitimately flip to
    #       REAL when the quota resets. If it fails here, read the [seam]
    #       line above before assuming a regression.
    #
    #   restaurants -> REAL: went live on the local Ollama RAG path
    #       (restaurant_agent/restaurant_agent_ollama.py). THIS ENTRY FAILS
    #       in any interpreter without chromadb, reporting FAILED instead.
    #       That is an environment difference, not a regression, so the
    #       expectation is deliberately NOT relaxed to FAILED -- run this
    #       file in the venv that has the deps (wt-sandbox's) to see it pass.
    #
    #       Be careful reading its failure message. The seam reports
    #       "No module named 'restaurant_finder'", which is misleading: the
    #       real cause is "No module named 'chromadb'". A broad
    #       `except ImportError` at restaurant_agent_ollama.py:68 catches
    #       the relative import's failure and retries it as a bare import,
    #       so the second, less informative error is the one that escapes.
    #       Verified by importing restaurant_agent.restaurant_finder
    #       directly, which reports chromadb. Worth raising with Vrushti --
    #       narrowing that except would make the seam's cause line accurate
    #       for this slot.
    EXPECTED_MODES = {
        "destination": FAILED,
        "restaurants": REAL,
        "flights": FAILED,
    }
    for slot, expected in EXPECTED_MODES.items():
        actual = forced.get(slot)
        check(
            f"{slot}: effective mode is '{expected}' as expected",
            actual == expected,
            f"got '{actual}'",
        )

    # The substantive property CASE 2 now exists to prove, and the exact
    # inverse of what it proved before: a REAL slot that could not be
    # reached must NOT come back as that slot's stand-in. This is the check
    # that would have caught the original hazard -- an itinerary assembled
    # entirely from sample data while every step looked like a result.
    #
    # It is asserted as "is not the stand-in" rather than "equals the
    # failure text" on purpose: the failure text carries a cause that
    # differs per environment (missing dep here, spent quota there), so
    # pinning the exact string would make this fail for the wrong reason.
    for slot in ("destination", "flights"):
        reply = next((r for s, _, r in observed2 if s == slot), "")
        check(
            f"{slot}: unreachable agent did NOT silently become a stand-in",
            reply != _dummy_reply(slot),
            reply.splitlines()[0][:60] if reply else "(empty)",
        )
        check(
            f"{slot}: reply says it is not connected and carries a cause",
            "Not connected" in reply and "Cause:" in reply,
            reply.splitlines()[0][:60] if reply else "(empty)",
        )

    # -- Case 3: the other direction of the seam. A slot that IS connected,
    #    forced to DUMMY, must report 'dummy' and hand back stand-in content.
    #    Without this, a seam that ignored DUMMY and always ran the real
    #    agent would still pass every check above. Costs no API calls.
    rule("CASE 3 -- connected agent forced to DUMMY: must report dummy")
    overrides3 = {"restaurants": DUMMY}
    final3, observed3, modes3 = await run_case(request, overrides3, env=None)
    report(request, modes3, final3, observed3)
    mode3 = next((m for s, m, _ in observed3 if s == "restaurants"), None)
    reply3 = next((r for s, _, r in observed3 if s == "restaurants"), "")
    check(
        "restaurants: connected agent forced to DUMMY reports 'dummy'",
        mode3 == DUMMY,
        f"got '{mode3}'",
    )
    check(
        "restaurants: forced-dummy reply is the stand-in, not live data",
        reply3 == _dummy_reply("restaurants"),
        reply3.splitlines()[0][:60] if reply3 else "(empty)",
    )

    # -- Case 4 used to check the envelope agent's refusal prose via
    #    evaluation/direct_path.render. That agent (now
    #    proposed_envelope_agent) is no longer an orchestrator option --
    #    proposed future work -- so its behaviour is not part of the UI's
    #    surface and is not asserted here. Its own checks live in
    #    budget_agent_rohan/tests/ and sandbox/run_envelope_test.py.

    rule("RESULT")
    if FAILURES:
        print(f"  {len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("  all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
