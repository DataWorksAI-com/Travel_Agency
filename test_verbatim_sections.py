"""Agent sections are the agent's own words; the model only gets the summary.

28 Aug 2026: Budget crashed, returned nothing but "Not connected -- the Budget
agent did not run", and the === Budget === section still reported "$1,076" and
"approximately $385 per night for lodging". Every figure invented, under a
heading naming an agent that produced none of them.
"""
import sys

sys.path.insert(0, ".")
from orchestrator_agent import _itinerary, _SUMMARY_HEADING

passed = failed = 0


def check(label, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print("  [PASS] %s" % label)
    else:
        failed += 1
        print("  [FAIL] %s\n         got %r, want %r" % (label, got, want))


LEDGER = {
    "destination": ["Destination: Bridgetown. Best months are December to April."],
    "flights": ["B6: $538, direct, arrives BGI"],
    "budget": ["Not connected -- the Budget agent did not run, so there is no real "
               "data for this section."],
}
FABRICATED = (
    "The Budget agent did not run.\n\n"
    "Quick Budget Estimate: Flights $1,076 for 2, leaving approximately "
    "$385 per night for lodging."
)

out = _itinerary(FABRICATED, LEDGER)

check("the model's text is kept, under its own heading",
      _SUMMARY_HEADING in out and "The Budget agent did not run." in out, True)
check("but its invented per-night lodging figure is not",
      "$385 per night" in out, False)
check("the Budget section is the agent's own words",
      "=== Budget ===\nNot connected -- the Budget agent did not run" in out, True)
check("the invented per-night figure is not in the Budget section",
      "$385" in out.split("=== Budget ===")[1], False)
check("a real reply survives verbatim",
      "=== Flights ===\nB6: $538, direct, arrives BGI" in out, True)
check("an uncalled agent gets no section",
      "=== Restaurants ===" in out, False)
check("sections follow SLOTS order, not ledger insertion order",
      out.index("=== Destination ===") < out.index("=== Flights ===")
      < out.index("=== Budget ==="), True)

# An empty reply is not a section -- it would render a bare heading that reads
# like the agent answered with nothing to say.
check("an empty reply gets no section",
      "=== Activities ===" in _itinerary("s", {**LEDGER, "activities": ["  "]}), False)

# No agent prices lodging, so a lodging price in the summary came from the model.
# Every one of these was produced live on 28 Aug 2026.
for line in ("This leaves approximately $385 per night for lodging.",
             "Lodging (~$300-400/night for 5 nights would consume most of it)",
             "Guesthouses run $70-120/night.",
             "Accommodation not included - expect $350-$1,500 for 5 nights."):
    out = _itinerary(f"Trip looks workable.\n{line}", LEDGER)
    check("lodging price dropped: %s" % line[:38], line in out, False)
    check("  ...and the removal is disclosed", "was removed from this summary" in out, True)

# Live, 28 Aug 2026: an invented nightly range rode through the old allowance
# exemption on the word "leaving", inside a one-paragraph summary.
_live = (
    "Your $3000 budget is feasible but tight. The JetBlue flight at $538 per "
    "person ($1,076 total) is the best value, leaving you $1,924 for the rest. "
    "You'll need to allocate roughly $350-600 for budget-friendly guesthouses, "
    "leaving $1,300-1,575 for meals and activities. The destination is ideal "
    "December through April."
)
_out = _itinerary(_live, LEDGER)
check("the invented guesthouse range is gone", "$350-600" in _out, False)
check("the rest of the paragraph survives", "JetBlue flight at $538" in _out, True)
check("...including the sentence after it", "December through April" in _out, True)

# Rule 5 says the model must not write sections. Live, 28 Aug 2026, it wrote
# them anyway, restating every agent above the real ones. Truncated in code.
_with_sections = (
    "## Summary\n\nBridgetown is workable on $3,000.\n\n"
    "=== destination ===\nRecommended destination: Bridgetown, Barbados.\n\n"
    "=== flights ===\nB6: $538, direct.\n"
)
_t = _itinerary(_with_sections, LEDGER)
check("the summary keeps the model's prose",
      "Bridgetown is workable on $3,000." in _t, True)
check("the model's own headings are cut",
      "=== destination ===" in _t, False)
check("...and so is everything after them",
      "Recommended destination: Bridgetown, Barbados." in _t.split("The sections below")[0], False)
check("the real section still follows", "=== Flights ===\nB6: $538, direct, arrives BGI" in _t, True)

# A lodging mention with no figure is fine -- naming the gap is the honest move.
_gap = "No agent priced lodging, so budget for accommodation separately."
check("a lodging gap with no figure survives", _gap in _itinerary(_gap, LEDGER), True)

print()
print("%d/%d passing" % (passed, passed + failed))
sys.exit(1 if failed else 0)
