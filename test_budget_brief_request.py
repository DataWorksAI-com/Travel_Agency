"""Budget's brief carries the TRAVELLER's request, not the model's rewrite of it.

Captured 28 Aug 2026, the agentic path put this above the verified ledger:

    "... Flights: B6 at $538 per person. Restaurants: mix of Champers ($95 for
     two) ... Determine if this fits the budget and provide cost breakdown."

Two failures in one paragraph. It relays three agents' figures as unverified
prose, which orchestrator_costs exists to prevent, and it orders Budget to
produce the total rule 5 tells it to withhold. Budget followed the order: it
priced lodging at $240/night to make a $3000 trip fit and returned FEASIBLE on
a total that was 78% invented.

Nothing fails loudly if `request` stops being threaded through -- the brief
just quietly goes back to the model's wording -- so it is asserted here.
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from orchestrator_costs import build_budget_brief

passed = failed = 0


def check(label, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print("  [PASS] %s" % label)
    else:
        failed += 1
        print("  [FAIL] %s\n         got %r, want %r" % (label, got, want))


src = Path("orchestrator_agent.py").read_text(encoding="utf-8")

check("_new_run accepts the traveller's request",
      'def _new_run(base_facts=None, stated_budget="", request="")' in src, True)
check("plan_trip_agentic threads the request in",
      "_new_run(base_facts, stated_budget, request=task)" in src, True)
check("the budget brief prefers the request over the model's text",
      "task=request or task" in src, True)
check("the model's composition is no longer passed unconditionally",
      "build_budget_brief(\n                task=task," in src, False)

# The fallback matters: orchestrator.py:285 records that Budget with no request
# at all invented a 3-day trip. `request or task` must keep the old behaviour
# when the request is empty, not send an empty string.
brief = build_budget_brief(
    task="" or "Plan a week in Aruba from Boston, budget $3000",
    replies={"flights": "B6: $538, direct, arrives BGI"},
    is_failure=lambda r: False,
)
check("a request reaches the brief", "Plan a week in Aruba" in brief, True)
check("trip length survives into the brief", "a week" in brief, True)

print()
print("%d/%d passing" % (passed, passed + failed))
sys.exit(1 if failed else 0)
