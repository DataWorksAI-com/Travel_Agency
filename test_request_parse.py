"""Tests for ui/request_parse, the deterministic pre-parse.

WHY THIS MATTERS MORE THAN IT LOOKS. This module's output does not stay in the
UI. orchestrator_agent.ask_agent prepends it to EVERY subagent task as
"Trip details:", so a parsed value arrives at six agents as a stated fact. A
wrong value is therefore not a weak guess -- it is a confident lie the model
then has to notice and override. Silence is strictly better than a wrong guess
here, and several cases below assert exactly that.

Cases 1-4 are the four defects a live tester query exposed on 27 Aug 2026.
Cases 5-6 are the working demo lines, which must not regress.

Run: python test_request_parse.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui.request_parse import parse_request

cases = []


def check(name, condition):
    cases.append((name, bool(condition)))


def parsed(text):
    return parse_request(text)


# 1 -- "we are in boston": the origin was read as the DESTINATION.
#
# Verbatim from the live run. The parser returned destination_country='USA',
# so every agent was told the destination was the USA for a request whose
# whole point was that the destination was unknown. It survived only because
# the destination agent happened to answer Honolulu; the same itinerary lists
# Cartagena as an alternative considered, and had it picked that, Money &
# Customs would have been handed "destination country: USA" for Colombia and
# answered confidently about the wrong country.
MESSY = ("me and my girlfriend are in boston and want somewhere warm and "
         "cheap for a week in september, maybe 2 grand?")
m = parsed(MESSY)
check("messy: boston is the ORIGIN", m["origin_country"] == "USA")
check("messy: no destination is claimed", m["destination_country"] == "")
check("messy: '2 grand' is $2000", m["stated_budget"] == "$2000")

# 2 -- a month is not a place
mo = parsed("somewhere warm for a week in september, flying from boston")
check("month: september is not a destination", mo["destination_country"] == "")
check("month: origin still found", mo["origin_country"] == "USA")
check("month: a real place after a month still wins",
      parsed("a week in september to Cancun")["destination_country"] == "Mexico")

# 3 -- informal amounts. "under 2 grand" used to parse as $2: the labelled
# pattern stops at the digits and never sees the multiplier.
check("informal: 'under 2 grand' is $2000",
      parsed("plan a trip under 2 grand")["stated_budget"] == "$2000")
check("informal: 'budget maybe 2k' is $2000",
      parsed("budget maybe 2k")["stated_budget"] == "$2000")
check("informal: '2,500 grand' is not silently truncated",
      parsed("under 2,500 grand")["stated_budget"] == "$2500000")

# 4 -- other ways of saying where you are
for phrase in ("we're in boston", "i'm in boston", "i am in boston",
               "we live in boston", "based in boston", "staying in boston"):
    p = parsed(f"{phrase} and want somewhere warm")
    check(f"origin phrasing: {phrase!r}",
          p["origin_country"] == "USA" and p["destination_country"] == "")

# 5 -- REGRESSION: the two demo lines must parse exactly as before
cancun = parsed("Plan 5 nights in Cancun for 2 people from Boston in "
                "September, total budget $3000")
check("demo 1: destination Mexico", cancun["destination_country"] == "Mexico")
check("demo 1: origin USA", cancun["origin_country"] == "USA")
check("demo 1: budget $3000", cancun["stated_budget"] == "$3000")

honolulu = parsed("Plan 5 nights in Honolulu for 2 people from Boston in "
                  "September, total budget $3000")
check("demo 2: destination USA", honolulu["destination_country"] == "USA")
check("demo 2: origin USA", honolulu["origin_country"] == "USA")
check("demo 2: budget $3000", honolulu["stated_budget"] == "$3000")

# 6 -- the accented spelling still folds to the same country
check("accents: Cancún resolves like Cancun",
      parsed("5 nights in Cancún")["destination_country"] == "Mexico")

# 7 -- unambiguous destination markers are untouched by the origin masking
check("unambiguous: 'to Cancun' still wins",
      parsed("flying from Boston to Cancun")["destination_country"] == "Mexico")
check("unambiguous: 'visiting Tokyo'",
      parsed("visiting Tokyo")["destination_country"] == "Japan")

# 8 -- empty and junk input never raises
for junk in ("", "   ", "hello", "?????"):
    try:
        parse_request(junk)
        check(f"junk is safe: {junk!r}", True)
    except Exception as exc:                                  # pragma: no cover
        check(f"junk is safe: {junk!r} -- raised {exc}", False)

passed = sum(1 for _, ok in cases if ok)
for name, ok in cases:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"\n{passed}/{len(cases)} passing")
sys.exit(0 if passed == len(cases) else 1)
