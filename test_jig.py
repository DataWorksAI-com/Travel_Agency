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
# =============================================================================

from restaurant_finder import search_restaurants

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


def run():
    print("\n" + "=" * 60)
    print("  Restaurant Agent - Test Jig")
    print("=" * 60 + "\n")
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
    print("\n" + "-" * 60)
    print(f"  SCORE: {passed}/{len(CASES)} checks passed")
    print("-" * 60 + "\n")
    return passed == len(CASES)


if __name__ == "__main__":
    run()
