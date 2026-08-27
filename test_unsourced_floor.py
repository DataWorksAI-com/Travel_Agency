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
#
# These two checks used to assert "no note at all" on a healthy run. That was
# right about slot naming and wrong about lodging, and run 6 of 27 Aug 2026
# proved it: all six slots green, so the note was suppressed, so the
# orchestrator's own "$376 per night available for accommodation ... comfortably
# covers mid-range to nice hotels" shipped with no caveat. No agent prices
# lodging on ANY run, healthy or not. The false-positive worry this case was
# written for is naming a slot that answered -- still guarded below.
all_ok = {
    "destination": [OK_DEST], "money_customs": [OK_MONEY], "flights": [OK_FLIGHTS],
    "restaurants": [OK_REST], "activities": [OK_ACTS], "budget": [OK_BUDGET],
}
healthy = _unsourced_figures_note(OK_BUDGET, all_ok)
check("all slots answered: no slot is named as unsourced",
      not any(l.startswith("- ") for l in healthy.splitlines()))
check("all slots answered: no 'treat those numbers' slot paragraph",
      "categories listed" not in healthy)
check("all slots answered: the lodging caveat still fires", "lodging" in healthy.lower())
check("all slots answered: _floor adds no Agent status",
      "=== Agent status ===" not in _floor(OK_BUDGET, all_ok))

# 3b -- the run 6 sentence itself, verbatim, on a fully green ledger
RUN6 = (
    "After flights and food you have approximately $376 per night available for "
    "accommodation for both travelers ($188 per person/night), which comfortably "
    "covers mid-range to nice hotels in Cancun's hotel zone."
)
check("run 6: a green run still caveats the invented per-night figure",
      "lodging" in _floor(RUN6, all_ok).lower())
check("run 6: the caveat also disowns the 'comfortably covers' claim",
      "will or will not cover" in _floor(RUN6, all_ok))

# 3c -- run 8 of 27 Aug 2026: the phrase list missed, absences() must not.
# Activities answered in gpt-4o-mini's own words, which match no NO_DATA_PHRASE.
# The seam only ever sees the model's paraphrase of the tool's error string, so
# phrase matching alone cannot hold here; extract_line_items finding nothing is
# what does. Every other slot is healthy, so this is the ONLY name in the block.
RUN8_ACTS = (
    "I encountered an issue while trying to retrieve activities for Cancun, which "
    "currently lacks the necessary details in the local data. I recommend "
    "considering some general activities typically found in Cancun:\n\n"
    "1. **Visit the Cancun Underwater Museum**\n   - **Price Tier:** Unknown\n"
)
check("run 8: the phrase list alone does NOT catch it", not _held_no_data(RUN8_ACTS))
run8 = _unsourced_figures_note("Total $1,858", {**all_ok, "activities": [RUN8_ACTS]})
check("run 8: Activities is named anyway", "Activities" in run8)
check("run 8: and no healthy slot is dragged in with it",
      len([l for l in run8.splitlines() if l.startswith("- ")]) == 1)

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
