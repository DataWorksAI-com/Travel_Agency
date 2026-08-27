"""The travel month must be a fact, not something a model derives.

On the 14:0x run the task literally said "today's date: 2026-08-27" and the
orchestrator still told Flights to search "September 2024". Supplying the date
was not enough -- a weaker model does the arithmetic wrong, and the failure is
invisible: the agent reports no cached data for a route that has fares.
"""
import sys
from datetime import date

sys.path.insert(0, ".")
from orchestrator_agent import resolve_travel_month

passed = failed = 0


def check(label, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print("  [PASS] %s" % label)
    else:
        failed += 1
        print("  [FAIL] %s  got %r want %r" % (label, got, want))


AUG = date(2026, 8, 27)
OCT = date(2026, 10, 5)

check("bare month later this year", resolve_travel_month("5 nights in September", AUG), "2026-09")
check("same month as today resolves to this year",
      resolve_travel_month("going in August", AUG), "2026-08")
check("month already past rolls to next year",
      resolve_travel_month("going in September", OCT), "2027-09")
check("explicit year is honoured", resolve_travel_month("in September 2028", AUG), "2028-09")
check("explicit PAST year is honoured, not corrected",
      resolve_travel_month("in September 2024", AUG), "2024-09")
check("no month named", resolve_travel_month("plan a beach trip", AUG), "")
check("case insensitive", resolve_travel_month("in SEPTEMBER", AUG), "2026-09")
check("the real demo query", resolve_travel_month(
    "Plan 5 nights in Cancun for 2 people from Boston in September, total budget $3000", AUG),
    "2026-09")
check("December from August", resolve_travel_month("in December", AUG), "2026-12")
check("January from August rolls over", resolve_travel_month("in January", AUG), "2027-01")
check("month word inside another word is not matched",
      resolve_travel_month("the Mayflower marched", AUG), "")

# The fact must actually reach the agents.
import orchestrator_agent
src = __import__("inspect").getsource(orchestrator_agent)
check("travel month is wired into the task facts", "travel month" in src, True)
check("prompt tells the model to use it verbatim", "verbatim" in orchestrator_agent.SYSTEM_PROMPT, True)

print()
print("%d/%d passing" % (passed, passed + failed))
sys.exit(1 if failed else 0)
