"""Regression: the traveller's own budget must never become a cost.

Verbatim text from the live run of 27 Aug 2026.
"""
import sys
sys.path.insert(0, ".")
from orchestrator_costs import extract_line_items, build_budget_brief

ACTIVITIES = (
    "Confirmed Activities:\n"
    "Cancun Underwater Museum (MUSA) -- Cultural, price tier unknown\n"
    "Budget Context:\n"
    "With $3,000 total budget for 2 travelers over 5 nights, you have "
    "approximately $300/night for accommodation plus activities.\n"
)

RESTAURANTS = (
    "El Muelle Seafood -- Seafood. About $35 per person, rated 4.5/5.\n"
    "Taco Loco -- Mexican. About $10 per person, rated 4.2/5.\n"
)

FLIGHTS_PASSING_MENTION = (
    "Your $3,000 total budget allows approximately $1,500 per person, which "
    "should comfortably cover round-trip flights.\n"
)

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print("  [PASS] %s" % label)
    else:
        failed += 1
        print("  [FAIL] %s" % label)


acts = extract_line_items("activities", ACTIVITIES)
costs = [i["cost"] for i in acts]
check("stated budget 3000 is not an activity cost", 3000.0 not in costs)
check("lodging 300/night is not an activity cost", 300.0 not in costs)
check("no bogus items survive from that reply", acts == [])

rest = extract_line_items("restaurants", RESTAURANTS)
rcosts = sorted(i["cost"] for i in rest)
check("real restaurant prices still extracted", rcosts == [10.0, 35.0])
check("per-person still detected", all(i["per"] == "person" for i in rest))

fl = extract_line_items("flights", FLIGHTS_PASSING_MENTION)
check("budget-reasoning line yields no flight cost", fl == [])

brief = build_budget_brief(
    task="Plan 5 nights in Cancun for 2 people from Boston, total budget $3000.",
    replies={"activities": ACTIVITIES, "restaurants": RESTAURANTS},
    is_failure=lambda r: False,
    stated_budget="$3000",
)
check("brief does not contain 3000.0 as a priced input", '"cost": 3000.0' not in brief)
check("brief does not contain 300.0 as a priced input", '"cost": 300.0' not in brief)
check("brief still carries the real 35.0", '"cost": 35.0' in brief)

# The value guard alone, with the sentence guard bypassed.
DIRECT = "Package deal -- $3000 all in for the pair.\n"
items = extract_line_items("activities", DIRECT)
check("value guard: 3000 survives extraction on its own", 3000.0 in [i["cost"] for i in items])
brief2 = build_budget_brief(
    task="t", replies={"activities": DIRECT}, is_failure=lambda r: False,
    stated_budget="$3000",
)
check("value guard: but is dropped from the brief", '"cost": 3000.0' not in brief2)

print()
print("%d/%d passing" % (passed, passed + failed))
sys.exit(1 if failed else 0)
