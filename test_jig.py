# =============================================================================
# ALY 6980 CAPSTONE - WEEK 2
# Test jig for the restaurant agent (black-box scoring loop)
#
# What this is, in plain terms:
# A tiny automatic checker. Each case is a request plus what a CORRECT answer
# must be true about (right city, within budget, all vegan, etc.). The jig runs
# every case through the search engine and prints PASS or FAIL, then a score.
# If a future change ever breaks a filter, this catches it instantly.
#
# It checks the deterministic core - the hard filters and retrieval - so it is
# reliable and needs no LLM. Run it with:   python test_jig.py
#
# Section A checks retrieval and the five hard filters.
# Section B checks the orchestrator contract: the task-string parser and the
# itinerary-ready message format. Contract checks matter because the
# orchestrator drops this agent's reply straight into a customer itinerary.
# =============================================================================

from restaurant_finder import search_restaurants, parse_task, format_for_itinerary

# Each case: a description, the search arguments, and a check(results) -> bool
CASES = [
    {
        "desc": "Vegan + gluten-free dinner in Aruba under $30",
        "args": {"query": "vegan gluten-free dinner", "city": "Aruba",
                 "max_price": 30, "dietary": ["vegan", "gluten-free"]},
        "check": lambda r: len(r) > 0 and all(
            x["city"] == "Aruba" and x["price"] <= 30 and x["vegan"] and x["gluten_free"] for x in r),
    },
    {
        "desc": "Cheap food under $15 (any city)",
        "args": {"query": "cheap casual food", "max_price": 15},
        "check": lambda r: len(r) > 0 and all(x["price"] <= 15 for x in r),
    },
    {
        "desc": "4.5+ rated Mexican in Cancun",
        "args": {"query": "mexican food", "city": "Cancun",
                 "cuisine": "Mexican", "min_rating": 4.5},
        "check": lambda r: len(r) > 0 and all(
            x["city"] == "Cancun" and x["cuisine"] == "Mexican" and x["rating"] >= 4.5 for x in r),
    },
    {
        "desc": "Vegan-cuisine spots only",
        "args": {"query": "plant based", "cuisine": "Vegan"},
        "check": lambda r: len(r) > 0 and all(x["cuisine"] == "Vegan" for x in r),
    },
    {
        "desc": "Steakhouse in San Juan",
        "args": {"query": "steak dinner", "city": "San Juan", "cuisine": "Steakhouse"},
        "check": lambda r: len(r) > 0 and all(
            x["city"] == "San Juan" and x["cuisine"] == "Steakhouse" for x in r),
    },
    {
        "desc": "Only highly rated places (4.7+)",
        "args": {"query": "best restaurants", "min_rating": 4.7},
        "check": lambda r: len(r) > 0 and all(x["rating"] >= 4.7 for x in r),
    },
    {
        "desc": "Honolulu city filter is respected",
        "args": {"query": "somewhere to eat", "city": "Honolulu"},
        "check": lambda r: len(r) > 0 and all(x["city"] == "Honolulu" for x in r),
    },
    {
        "desc": "Impossible combo returns nothing (vegan steakhouse)",
        "args": {"query": "steak", "cuisine": "Steakhouse", "dietary": ["vegan"]},
        "check": lambda r: len(r) == 0,
    },
]


# -----------------------------------------------------------------------------
# SECTION B - ORCHESTRATOR CONTRACT CHECKS
# -----------------------------------------------------------------------------
# These need no vector database and no LLM. Each case is a description plus a
# check() that returns True when the contract holds.

_SAMPLE = [
    {"name": "Sunset Vegan Kitchen", "city": "Aruba", "cuisine": "Vegan",
     "price": 26, "rating": 4.8, "vegetarian": True, "vegan": True,
     "gluten_free": True, "description": "Fully plant-based with ocean views."},
    {"name": "Palma Verde", "city": "Aruba", "cuisine": "Mediterranean",
     "price": 28, "rating": 4.6, "vegetarian": True, "vegan": True,
     "gluten_free": True, "description": "Beachfront patio, plenty of plants."},
    {"name": "Mango Street Tacos", "city": "Aruba", "cuisine": "Mexican",
     "price": 14, "rating": 4.3, "vegetarian": True, "vegan": True,
     "gluten_free": True, "description": "Casual cheap taco stand."},
]


def _parsed(task):
    return parse_task(task)


CONTRACT_CASES = [
    {
        "desc": "Task string: city, budget and diet are all read out",
        "check": lambda: (
            _parsed("Recommend a vegan dinner in Aruba under $30")["city"] == "Aruba"
            and _parsed("Recommend a vegan dinner in Aruba under $30")["max_price"] == 30
            and "vegan" in _parsed("Recommend a vegan dinner in Aruba under $30")["dietary"]
        ),
    },
    {
        "desc": "Task string: '40 dollars per person' is read as a budget",
        "check": lambda: _parsed("seafood in San Juan, 40 dollars per person")["max_price"] == 40,
    },
    {
        "desc": "Task string: 'highly rated' becomes a 4.5 rating floor",
        "check": lambda: _parsed("highly rated dinner in Honolulu")["min_rating"] == 4.5,
    },
    {
        "desc": "Missing city is flagged as a stated assumption, not a question",
        "check": lambda: (
            len(_parsed("somewhere good for dinner")["assumptions"]) > 0
            and "?" not in " ".join(_parsed("somewhere good for dinner")["assumptions"])
        ),
    },
    {
        "desc": "Message commits to ONE top pick, not a vague list",
        "check": lambda: (
            format_for_itinerary(_SAMPLE).startswith("Recommended restaurant: Sunset Vegan Kitchen")
            and "here are some options" not in format_for_itinerary(_SAMPLE).lower()
        ),
    },
    {
        "desc": "Every named restaurant carries cuisine, city, price and rating",
        "check": lambda: all(
            s in format_for_itinerary(_SAMPLE)
            for s in ("Vegan, Aruba", "$26 per person", "rated 4.8/5",
                      "Mediterranean, Aruba", "$28 per person", "rated 4.6/5")
        ),
    },
    {
        "desc": "At most two alternatives are offered",
        "check": lambda: format_for_itinerary(_SAMPLE + _SAMPLE).count("\n- ") <= 2,
    },
    {
        "desc": "Final message never asks the orchestrator a question",
        "check": lambda: (
            "?" not in format_for_itinerary(_SAMPLE)
            and "?" not in format_for_itinerary([])
        ),
    },
    {
        "desc": "Empty result set states the gap plainly and invents nothing",
        "check": lambda: (
            "No restaurant" in format_for_itinerary([])
            and "invented" in format_for_itinerary([])
        ),
    },
]


def run():
    print("\n" + "=" * 60)
    print("  Restaurant Agent - Test Jig")
    print("=" * 60 + "\n")
    print("SECTION A - retrieval and hard filters\n")
    passed = 0
    for c in CASES:
        try:
            results = search_restaurants(**c["args"], top_k=10)
            ok = c["check"](results)
            n = len(results)
        except Exception as error:
            ok, n = False, "error"
            print("   (error:", error, ")")
        print(f"[{'PASS' if ok else 'FAIL'}]  {c['desc']}  ({n} results)")
        if ok:
            passed += 1

    print("\nSECTION B - orchestrator contract\n")
    for c in CONTRACT_CASES:
        try:
            ok = bool(c["check"]())
        except Exception as error:
            ok = False
            print("   (error:", error, ")")
        print(f"[{'PASS' if ok else 'FAIL'}]  {c['desc']}")
        if ok:
            passed += 1

    total = len(CASES) + len(CONTRACT_CASES)
    print("\n" + "-" * 60)
    print(f"  SCORE: {passed}/{total} checks passed")
    print("-" * 60 + "\n")
    return passed == total


if __name__ == "__main__":
    run()
