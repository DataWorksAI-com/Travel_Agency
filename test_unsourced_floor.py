"""Tests for the unsourced-figures floor in orchestrator_agent.

Cases 1-2 are the live failure from the 26 Aug run, replayed from the actual
replies. Cases 3-6 are the false positives that would make this worse than
nothing: a caveat attached to a fully-sourced itinerary trains people to skip
the caveats.

Run: python test_unsourced_floor.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator_agent import _floor, _held_no_data, _unsourced_figures_note

OK_FLIGHTS = "Boston to Cancun, 12 Sep, $312 round trip per person."
OK_ACTS = "Zona Arqueologica San Miguelito -- historic, around $5 per person."
OK_REST = "Villa Toscana - Italian; approx. $44 per person, rated 4.4/5."
OK_DEST = "Recommended destination: Cancun, Mexico. Best months are February to May."
OK_MONEY = "1 USD = 16.93 MXN. Tipping around 10-15% is expected in restaurants."
OK_BUDGET = "Flights $624, meals $600. Total $1,224 -- feasible."

# Verbatim from the 26 Aug live run.
LIVE_NO_FLIGHTS = "No flight prices found for the requested route and dates."
LIVE_ACTS_FAILED = (
    "Not connected -- the Activities agent did not run, so there is no real "
    "data for this section."
)
LIVE_FINAL = (
    "=== Budget === Estimated Cost Breakdown\n"
    "Flights $850 (estimated)\nLodging $400\nFood & Dining $860\n"
    "Activities $200 (estimated)\nTotal Estimated Cost $2,310\n"
    "Feasibility Verdict: comfortably feasible, leaving $690 under budget."
)

cases = []


def check(name, condition):
    cases.append((name, bool(condition)))


# 1 -- the live case: Flights held no data, Activities failed, Budget billed both
led = {
    "destination": [OK_DEST], "money_customs": [OK_MONEY],
    "flights": [LIVE_NO_FLIGHTS], "restaurants": [OK_REST],
    "activities": [LIVE_ACTS_FAILED], "budget": [OK_BUDGET],
}
note = _unsourced_figures_note(LIVE_FINAL, led)
check("live case: note is emitted", note)
check("live case: names Flights", "Flights" in note)
check("live case: names Activities", "Activities" in note)
check("live case: does NOT name Budget as unsourced",
      not any(l.startswith("- Budget") for l in note.splitlines()))
check("live case: names Restaurants nowhere (it answered)", "Restaurants" not in note)
check("live case: flags lodging, which has no agent at all", "lodging" in note.lower())

# 2 -- reaches the caller through _floor, and after Agent status
full = _floor(LIVE_FINAL, led)
check("_floor: emits Agent status for the failed slot", "=== Agent status ===" in full)
check("_floor: emits the unsourced block too", "=== Unsourced figures ===" in full)
check("_floor: unsourced block comes last",
      full.index("=== Unsourced figures ===") > full.index("=== Agent status ==="))

# 3 -- FALSE POSITIVE GUARD: every slot answered, figures are sourced
all_ok = {
    "destination": [OK_DEST], "money_customs": [OK_MONEY], "flights": [OK_FLIGHTS],
    "restaurants": [OK_REST], "activities": [OK_ACTS], "budget": [OK_BUDGET],
}
check("all slots answered: no note", _unsourced_figures_note(OK_BUDGET, all_ok) == "")
check("all slots answered: _floor adds nothing", _floor(OK_BUDGET, all_ok) == OK_BUDGET)

# 4 -- FALSE POSITIVE GUARD: a slot held no data, but the itinerary quotes no money
prose = "=== Flights === No flight prices found for the requested route."
check("no currency in output: no note", _unsourced_figures_note(prose, led) == "")

# 5 -- currency detection is narrow enough not to fire on plain numbers
check("bare numbers are not prices",
      _unsourced_figures_note("5 nights for 2 travellers, 3 activities.", led) == "")
check("recognises $850", _unsourced_figures_note("Flights $850", led))
check("recognises 1,400 USD", _unsourced_figures_note("Lodging 1,400 USD", led))
check("recognises MXN", _unsourced_figures_note("about 300 MXN", led))

# 6 -- no-data phrase detection against real sentences
check("detects: no flight prices found", _held_no_data(LIVE_NO_FLIGHTS))
check("detects: hold no data for Colombia",
      _held_no_data("I hold no data for Colombia. The nearest country I hold is Belize."))
check("detects: not covered by local data",
      _held_no_data("'Miami' is not covered by local data."))
check("detects: no activity close enough in corpus",
      _held_no_data("No activity in the corpus is a close enough match for that."))
check("does NOT fire on a healthy reply", not _held_no_data(OK_FLIGHTS))
check("does NOT fire on a healthy restaurants reply", not _held_no_data(OK_REST))

passed = sum(1 for _, ok in cases if ok)
for name, ok in cases:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"\n{passed}/{len(cases)} passing")
sys.exit(0 if passed == len(cases) else 1)
