"""
run_pipeline.py -- run plan_trip() end to end over all six subagent
slots, capture every OUTBOUND task string, and show what actually flows
agent-to-agent.

Nothing in the orchestrator or in any agent is modified. The only
intervention is monkeypatching `orchestrator.get_client` (bound at
orchestrator.py:30 by `from orchestrator_config import get_client`) so each
slot returns a recording client instead of a real one.

Every slot, budget included, returns a deterministic fake (see fakes.py).
Budget used to run the real no-LLM envelope path here, but that agent
(proposed_envelope_agent) is no longer wired to any orchestrator slot -- it
is proposed future work, and its own harness is sandbox/run_envelope_test.py.
What this script exists to show is the OUTBOUND task strings, which do not
depend on any reply's content.

Run:  python sandbox/run_pipeline.py
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                       # orchestrator, config

import orchestrator  # noqa: E402
from sandbox import fakes  # noqa: E402

# fakes.REPLIES has no budget entry -- it was written when budget ran the real
# envelope path. fakes.py is deliberately left untouched, so the stand-in for
# this slot lives here, matching ui/agent_seam.py's own budget fallback.
BUDGET_STANDIN = (
    "Sample allocation: lodging $1,400, meals $760, activities $480, local "
    "transport $160, reserve $200. Stand-in figures, not a costed plan."
)

OUTBOUND: list[tuple[str, str]] = []   # (slot, exact task string received)


class RecordingClient:
    """Implements the SubagentClient interface: await call(task) -> str."""

    def __init__(self, slot, reply_fn):
        self.slot = slot
        self._reply_fn = reply_fn

    async def call(self, task: str) -> str:
        OUTBOUND.append((self.slot, task))
        return self._reply_fn(task)


def _get_client(name: str):
    if name == "budget":
        return RecordingClient("budget", lambda _task: BUDGET_STANDIN)
    return RecordingClient(name, lambda _task, n=name: fakes.REPLIES[n])


def rule(t):
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")


def main():
    orchestrator.get_client = _get_client   # the only intervention

    task = ("Plan a 4 night trip to Barbados for 2 people who like "
            "snorkeling and seafood.")

    rule("INPUT TO plan_trip()")
    print(f"  task                : {task}")
    print(f"  origin_country      : USA")
    print(f"  destination_country : Barbados")
    print(f"  stated_budget       : $5000")

    final = asyncio.run(orchestrator.plan_trip(
        task=task,
        origin_country="USA",
        destination_country="Barbados",
        stated_budget="$5000",
    ))

    rule("OUTBOUND TASK STRINGS -- what each slot actually received")
    for i, (slot, sent) in enumerate(OUTBOUND, 1):
        print(f"\n  --- [{i}] {slot.upper()} " + "-" * (50 - len(slot)))
        for line in sent.splitlines() or [""]:
            print(f"      {line}")

    rule("FINAL ASSEMBLED ITINERARY")
    for line in final.splitlines():
        print(f"  {line}")

    # ---- independent re-confirmation of the three claimed gaps ----------
    rule("GAP CHECKS -- measured against the strings captured above")
    sent = dict(OUTBOUND)
    parallel = [s for s in ("flights", "restaurants", "activities") if s in sent]

    print("\n  GAP 1 -- does the resolved destination reach the parallel three?")
    marker = "Bridgetown"   # the city Destination committed to
    for slot in parallel:
        print(f"      {slot:<12} contains '{marker}': "
              f"{marker in sent[slot]}")
    print(f"      Destination's own reply contains it : "
          f"{marker in fakes.DESTINATION}")

    print("\n  GAP 2 -- does an origin CITY appear anywhere outbound?")
    for slot in parallel:
        print(f"      {slot:<12} contains 'Boston': {'Boston' in sent[slot]}")
    print(f"      (plan_trip only accepts origin_COUNTRY -- there is no "
          f"origin-city parameter at all)")

    print("\n  GAP 3 -- does the budget reach the agents that search?")
    for slot in parallel:
        has = "5000" in sent[slot] or "$5,000" in sent[slot]
        print(f"      {slot:<12} contains the budget: {has}")
    print(f"      budget slot contains it            : "
          f"{'5000' in sent.get('budget', '')}")

    rule("WHAT THIS RUN DOES NOT SHOW")
    print("""
  - Model behaviour. Five of six slots are fixed strings; no LLM ran except
    none at all (Budget used the no-LLM direct path).
  - Whether envelopes IMPROVE anything. A fixed reply cannot respond to a
    ceiling, so envelopes-on and envelopes-off produce identical fake
    output by construction. See run_envelope_test.py.
  - Real failure modes. Every fake succeeds. Nothing here exercises
    LocalFunctionClient's error path.
""")


if __name__ == "__main__":
    main()
