"""
run_envelope_test.py -- what changes in the OUTBOUND task strings if Rohan's
ceilings are injected as a pre-phase, and an honest statement of what this
harness can and cannot prove about it.

Nothing in the orchestrator is modified. The injection is simulated by
wrapping the recording client, exactly as `_call_money_customs_context`
already prepends money_context at orchestrator.py:68-70.

READ THIS BEFORE QUOTING ANY RESULT BELOW
-----------------------------------------
This test shows a DIFFERENCE IN INPUT ONLY. The five non-budget slots are
fixed strings (sandbox/fakes.py); a fixed string cannot react to a ceiling.
So envelopes-on and envelopes-off produce byte-identical agent replies here
BY CONSTRUCTION, not as evidence of anything.

This harness therefore CANNOT test whether allocate-before beats
check-after. That comparison needs live agents that can actually respond to
a constraint. Do not cite this file as evidence for the HiMAP-Travel claim.

Run:  python sandbox/run_envelope_test.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "budget_agent_rohan"))

from budget_agent.orchestration import ceilings_for  # noqa: E402
from sandbox import fakes  # noqa: E402

TASK = ("Plan a 4 night trip to Barbados for 2 people who like snorkeling "
        "and seafood.")
BUDGET = "$5000"
DEST = "Barbados"


def rule(t):
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")


def main():
    money = fakes.MONEY_CUSTOMS
    ceilings = ceilings_for(TASK, stated_budget=BUDGET,
                            destination_country=DEST)

    rule("THE PRE-PHASE CALL")
    print(f"  ceilings_for(task, '{BUDGET}', '{DEST}')")
    print(f"  -> {len(ceilings)} chars, ~{len(ceilings) // 4} tokens\n")
    print(f"  {ceilings}")

    rule("OUTBOUND TO RESTAURANTS -- today")
    today = f"{money}\n\n{TASK}"
    print(f"  {today}")

    rule("OUTBOUND TO RESTAURANTS -- with the pre-phase")
    proposed = f"{ceilings}\n\n{money}\n\n{TASK}"
    print(f"  {proposed}")

    rule("DELTA")
    print(f"  today    : {len(today):>5} chars  (~{len(today) // 4} tokens)")
    print(f"  proposed : {len(proposed):>5} chars  (~{len(proposed) // 4} tokens)")
    print(f"  added    : {len(proposed) - len(today):>5} chars  "
          f"(~{(len(proposed) - len(today)) // 4} tokens)")

    rule("OUTBOUND TO ACTIVITIES -- today it gets NO injected context at all")
    print(f"  today    : {TASK}")
    print(f"\n  Activities is excluded from money_context at "
          f"orchestrator.py:70 ('money/customs likely irrelevant here -- "
          f"confirm').")
    print(f"  ORCHESTRATOR_DESIGN.md decision #3 flags that exclusion as an")
    print(f"  assumption, not a fact. For a BUDGET ceiling the exclusion is")
    print(f"  clearly wrong -- Activities is the least constrained spender.")

    rule("THE FAIL-SAFE -- every miss returns '' and changes nothing")
    cases = [
        ("destination not in corpus",
         "Plan a 4 night trip to the Maldives for 2 people.", BUDGET, "Maldives"),
        ("no trip length stated",
         "Plan a trip to Barbados for 2 people.", BUDGET, "Barbados"),
        ("no budget stated", TASK, "", "Barbados"),
    ]
    for label, t, b, d in cases:
        out = ceilings_for(t, stated_budget=b, destination_country=d)
        verdict = "'' -> task string unchanged" if out == "" else "ISSUED"
        print(f"  {label:<28} {verdict}")

    rule("WHAT THIS PROVES, AND WHAT IT DOES NOT")
    print("""
  PROVES (wiring):
    - ceilings_for() runs with no key, no network, no model
    - its output is a plain string that composes with the existing
      money_context prepend at orchestrator.py:68-70
    - on any miss it returns '', so the outbound string is byte-identical
      to today's -- it cannot break a task string it cannot improve

  DOES NOT PROVE (behaviour):
    - that any agent SEARCHES DIFFERENTLY when given a ceiling
    - that the final plan is cheaper, better, or more within budget
    - anything at all about allocate-before vs check-after

  The fakes are fixed strings. They ignore the ceiling completely. Testing
  the actual claim requires live Flights/Restaurants/Activities and a
  scored comparison across many queries -- which is week-3 work, not this.
""")


if __name__ == "__main__":
    main()
