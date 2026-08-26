"""Tests for orchestrator_costs -- the prose-to-line-items bridge.

The replies below are copied from the 26 Aug live run, so this exercises the
actual failure: Flights reported no prices, Activities did not run, and Budget
produced "$850 (estimated)" for flights, "$200" for activities and "$400"
lodging, then headlined "Total $2,310 -- comfortably feasible".

Run: python test_orchestrator_costs.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator_costs import (
    build_budget_brief, extract_line_items, absences, held_no_data,
)

cases = []


def check(name, cond):
    cases.append((name, bool(cond)))


def is_failure(reply):
    return not reply or reply.startswith("Not connected")


# --- verbatim from the live run -------------------------------------------
LIVE_FLIGHTS = "No flight prices found for the requested route and dates."
LIVE_ACTS = ("Not connected -- the Activities agent did not run, so there is no "
             "real data for this section.")
LIVE_REST = (
    "Villa Toscana - Italian; approx. $44 per person, rated 4.4/5. A romantic "
    "trattoria noted for handmade pasta.\n"
    "Taco Loco - Mexican; approx. $10 per person, rated 4.2/5.\n"
    "Maya Jungle Kitchen - Mexican; approx. $27 per person, rated 4.6/5."
)
GOOD_FLIGHTS = "Boston to Cancun, 12 Sep: $312 round trip per person."

# --- 1. extraction ---------------------------------------------------------
items = extract_line_items("restaurants", LIVE_REST)
check("restaurants: extracts 3 line items", len(items) == 3)
check("restaurants: costs are right", sorted(i["cost"] for i in items) == [10.0, 27.0, 44.0])
check("restaurants: names come from the line", "Villa Toscana" in [i["name"] for i in items])
check("restaurants: per-person carried", all(i["per"] == "person" for i in items))
check("restaurants: category mapped to food", all(i["category"] == "food" for i in items))
check("restaurants: rating 4.4/5 NOT read as a cost",
      not any(i["cost"] in (4.4, 4.2, 4.6, 5.0) for i in items))

check("flights: a good reply extracts", len(extract_line_items("flights", GOOD_FLIGHTS)) == 1)
check("flights: 'no prices found' yields nothing", extract_line_items("flights", LIVE_FLIGHTS) == [])
check("activities: a failure yields nothing", extract_line_items("activities", LIVE_ACTS) == [])

# --- 2. never invents: unverifiable figures are dropped --------------------
check("destination is not a priced slot at all",
      extract_line_items("destination", "Beaches are lovely, hotels from $80.") == [])
check("money_customs is not a priced slot",
      extract_line_items("money_customs", "1 USD = 16.9309 MXN.") == [])
check("bare numbers are not costs",
      extract_line_items("activities", "Open 9 to 5, 2 hours long, 25 people max.") == [])
check("zero and negative are ignored",
      extract_line_items("activities", "Entry $0 today.") == [])

# --- 3. absences: the half that stops invention ----------------------------
live = {"flights": LIVE_FLIGHTS, "restaurants": LIVE_REST, "activities": LIVE_ACTS}
miss = absences(live, is_failure)
reasons = {m["source"]: m["reason"] for m in miss}
check("absence: flights recorded", "flights" in reasons)
check("absence: flights reason is 'holds no data'", "holds no data" in reasons["flights"])
check("absence: activities recorded", "activities" in reasons)
check("absence: activities reason is 'did not run'", "did not run" in reasons["activities"])
check("absence: restaurants NOT listed (it priced)", "restaurants" not in reasons)

check("absence: an uncalled slot is named as uncalled",
      any("was not called" in m["reason"] for m in absences({"restaurants": LIVE_REST}, is_failure)))
check("absence: answered-but-unpriced is distinguished",
      any("published no prices" in m["reason"]
          for m in absences({**live, "activities": "Try the Old Town walking route."}, is_failure)))

# --- 4. the brief itself ---------------------------------------------------
brief = build_budget_brief(
    task="5 nights in Cancun for 2 from Boston, budget $3000",
    replies=live, is_failure=is_failure, stated_budget="$3000",
)
check("brief: contains PRICED INPUTS", "PRICED INPUTS" in brief)
check("brief: contains the absence block", "NO FIGURE AVAILABLE" in brief)
check("brief: forbids lodging", "Do not price lodging" in brief)
check("brief: forbids benchmarking", "benchmark" in brief)
check("brief: allows refusing to total", "instead of\nproducing a total" in brief
      or "instead of producing a total" in brief)
check("brief: carries the traveller's request", "5 nights in Cancun" in brief)

# THE KEY PROPERTY: no other agent's prose is relayed into Budget's task.
check("brief: does NOT relay the restaurants reply verbatim",
      "A romantic trattoria noted for handmade pasta" not in brief)
check("brief: does NOT relay the flights reply verbatim", LIVE_FLIGHTS not in brief)
check("brief: does NOT relay the activities failure verbatim", LIVE_ACTS not in brief)
# The line items Budget sees carry the decision, not the source sentence. The
# quote survives on the extracted item for the orchestrator's own audit, and is
# stripped before the brief -- otherwise it smuggles prose through.
_sent = json.loads(brief.split("system.\n")[1].split("\n\nNO FIGURE")[0])
check("brief: line items carry no 'quote' field", all("quote" not in i for i in _sent))
check("brief: line items still carry the decision",
      all({"source", "category", "name", "cost", "currency", "per"} <= set(i) for i in _sent))
check("extraction still keeps quote for our own audit",
      all("quote" in i for i in extract_line_items("restaurants", LIVE_REST)))

# --- 5. no-data phrase detection ------------------------------------------
check("held_no_data: live flights reply", held_no_data(LIVE_FLIGHTS))
check("held_no_data: Colombia/Belize reply",
      held_no_data("I hold no data for Colombia. The nearest country I hold is Belize."))
check("held_no_data: false on a healthy reply", not held_no_data(GOOD_FLIGHTS))
check("held_no_data: safe on empty", not held_no_data(""))

passed = sum(1 for _, ok in cases if ok)
for name, ok in cases:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"\n{passed}/{len(cases)} passing")
sys.exit(0 if passed == len(cases) else 1)
