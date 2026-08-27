"""An agent's self-disclaimed figures must not reach Budget as verified.

Regression for the 27 Aug 2026 live run: Activities said its prices were "my own
compilation ... at typical market pricing, not database-verified entries", and
all four reached Budget under "PRICED INPUTS ... the orchestrator verified that
every figure appears verbatim".

The asymmetry that drives the design: a false positive costs caution (Budget
declines to total something it could have totalled). A false negative costs
credibility (an invented number presented as verified). So the guard is allowed
to over-flag, but the numeric hedging every agent uses to write a REAL price
must never trip it.
"""
import sys

sys.path.insert(0, ".")
from orchestrator_costs import (
    extract_line_items,
    build_budget_brief,
    disclaims_own_figures,
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


# ---- the exact shape from the live run -------------------------------------
ACTIVITIES = (
    "Coverage caveat: my local Cancun database was limited. The list below is "
    "my own compilation of popular regional activities at typical market "
    "pricing, not database-verified entries.\n"
    "Tulum -- guided full-day $80 per person.\n"
    "Chichen Itza -- full-day tour $120 per person.\n"
)

check("disclaimer detected", disclaims_own_figures(ACTIVITIES) is True)

items = extract_line_items("activities", ACTIVITIES)
check("figures still extracted (so they can be reported)", len(items) == 2)
check("every one flagged unverified", all(i["unverified"] for i in items))

brief = build_budget_brief(
    task="Plan 5 nights in Cancun for 2, total budget $3000.",
    replies={"activities": ACTIVITIES},
    is_failure=lambda r: False,
    stated_budget="$3000",
)
priced = brief.split("PRICED INPUTS")[1].split("FIGURES THE SOURCE AGENT")[0]
check("80 absent from PRICED INPUTS", '"cost": 80.0' not in priced)
check("120 absent from PRICED INPUTS", '"cost": 120.0' not in priced)
# Match the section OPENER, not the bare heading: rule 6 names the heading too,
# so a bare substring check is true in every brief and would never fail.
SECTION = "FIGURES THE SOURCE AGENT DISCLAIMED. These came from"
check("disclaimed section present", SECTION in brief)
check("disclaimed section carries them", '"cost": 80.0' in brief)
check("rule 6 present", "Keep it out of every total" in brief)
check("no internal flag leaks to Budget", '"unverified"' not in brief)

# ---- genuine prices must survive -------------------------------------------
REST = (
    "Recommended restaurant: El Muelle Seafood -- Seafood, Cancun. "
    "About $35 per person, rated 4.5/5.\n"
    "Alternative: Taco Loco -- Mexican. Approximately $10 per person.\n"
    "Alternative: Villa Toscana -- Italian, ~$44 per person.\n"
)
check("hedged-but-real prices are NOT disclaimed", disclaims_own_figures(REST) is False)
rest_items = extract_line_items("restaurants", REST)
check("all three real prices kept", sorted(i["cost"] for i in rest_items) == [10.0, 35.0, 44.0])
check("none flagged", not any(i["unverified"] for i in rest_items))

rbrief = build_budget_brief(
    task="t", replies={"restaurants": REST}, is_failure=lambda r: False, stated_budget="$3000"
)
check("real prices reach PRICED INPUTS", '"cost": 35.0' in rbrief)
check("no disclaimed section when nothing is disclaimed", SECTION not in rbrief)
check("rule 6 is still stated even with nothing disclaimed",
      "Keep it out of every total" in rbrief)

# ---- individual phrasings ---------------------------------------------------
for phrase, want in [
    ("these are typical prices for the region", True),
    ("figures are unverified", True),
    ("from my knowledge base, not a lookup", True),
    ("ballpark numbers only", True),
    ("for reference only", True),
    ("rough estimate of costs", True),
    ("illustrative pricing", True),
    ("about $35 per person", False),
    ("approximately $80 each", False),
    ("~$44 per person, rated 4.4/5", False),
    ("the tool returned three verified records", False),
]:
    check("%-46r -> %s" % (phrase, want), disclaims_own_figures(phrase) is want)

# ---- interaction with the earlier guards ------------------------------------
MIXED = (
    "With $3,000 total budget you have about $300/night for accommodation.\n"
    "These are typical market prices.\n"
    "Reef tour $60 per person.\n"
)
mi = extract_line_items("activities", MIXED)
check("budget/lodging line still dropped entirely",
      3000.0 not in [i["cost"] for i in mi] and 300.0 not in [i["cost"] for i in mi])
check("surviving figure flagged by the disclaimer", all(i["unverified"] for i in mi))

print()
print("%d/%d passing" % (passed, passed + failed))
sys.exit(1 if failed else 0)
