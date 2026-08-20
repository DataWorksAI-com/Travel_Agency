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

from restaurant_finder import (
    search_restaurants,
    search_with_reflection,
    parse_task,
    format_for_itinerary,
    RELAXATION_ORDER,
    MAX_ATTEMPTS,
)
from restaurant_agent_ollama import (find_restaurants, _enforce_tool_result,
                                     _record_tool_output, _TOOL_OUTPUTS,
                                     _cuisine_claims_are_faithful)

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


# -----------------------------------------------------------------------------
# SECTION C - THE REFLECTION STEP (the second look)
# -----------------------------------------------------------------------------
# These check that the agent re-queries when the literal request fails, that it
# relaxes the RIGHT things in the RIGHT order, that it never relaxes a dietary
# need or the destination city, that it stops, and that it always says what it
# changed. Each case runs the real vector search, so they also prove the loop
# works end to end rather than only in theory.

REFLECTION_CASES = [
    {
        "desc": "Impossible budget triggers a second look and recovers a real pick",
        # No vegan gluten-free option in Honolulu under $15; the cheapest is $18.
        "check": lambda: (
            lambda r, x: len(r) > 0 and len(x) > 0 and "budget was widened" in " ".join(x)
        )(*search_with_reflection("vegan gluten-free lunch", city="Honolulu",
                                  max_price=15, dietary=["vegan", "gluten-free"],
                                  top_k=10)),
    },
    {
        "desc": "A request that is satisfiable as written reports NO adjustments",
        "check": lambda: (
            lambda r, x: len(r) > 0 and x == []
        )(*search_with_reflection("vegan dinner", city="Aruba", max_price=30,
                                  dietary=["vegan"], top_k=10)),
    },
    {
        "desc": "An unmeetable rating floor is dropped before the budget is touched",
        # Nassau's only vegan option is rated 4.4, so the 4.5 floor must give way.
        "check": lambda: (
            lambda r, x: len(r) > 0 and "rating" in " ".join(x).lower()
            and "budget" not in " ".join(x).lower()
        )(*search_with_reflection("highly rated vegan dinner", city="Nassau",
                                  min_rating=4.5, dietary=["vegan"], top_k=10)),
    },
    {
        "desc": "An unavailable cuisine is dropped, and the diet is still honoured",
        "check": lambda: (
            lambda r, x: len(r) > 0 and "cuisine" in " ".join(x).lower()
            and all(item["vegan"] for item in r)
        )(*search_with_reflection("vegan bahamian dinner", city="Aruba",
                                  cuisine="Bahamian", dietary=["vegan"], top_k=10)),
    },
    {
        "desc": "Dietary needs are NEVER relaxed - a vegan steakhouse yields vegan food, not steak",
        # No steakhouse is vegan. The correct behaviour is to drop the CUISINE
        # (a preference) and keep 'vegan' (a hard requirement), so every result
        # is still vegan and no adjustment ever mentions the diet.
        "check": lambda: (
            lambda r, x: all(item["vegan"] for item in r)
            and not any(word in " ".join(x).lower()
                        for word in ("vegan", "vegetarian", "gluten", "diet"))
        )(*search_with_reflection("steak dinner", cuisine="Steakhouse",
                                  dietary=["vegan"], top_k=10)),
    },
    {
        "desc": "A truly impossible request returns nothing rather than a wrong answer",
        # Gluten-free steakhouse in Montego Bay: the city has no steakhouse at
        # all, and after cuisine is dropped nothing gluten-free remains either.
        "check": lambda: (
            lambda r, x: len(r) == 0 or all(item["gluten_free"] for item in r)
        )(*search_with_reflection("steak", city="Montego Bay",
                                  cuisine="Steakhouse", dietary=["gluten_free"],
                                  top_k=10)),
    },
    {
        "desc": "The destination city is NEVER relaxed",
        "check": lambda: (
            lambda r, x: all(item["city"] == "Nassau" for item in r)
            and "city" not in " ".join(x).lower()
        )(*search_with_reflection("highly rated vegan dinner", city="Nassau",
                                  min_rating=4.9, dietary=["vegan"], top_k=10)),
    },
    {
        "desc": "The loop stops - never more than two adjustments",
        "check": lambda: (
            lambda r, x: len(x) <= MAX_ATTEMPTS - 1
        )(*search_with_reflection("highly rated vegan bahamian meal", city="Nassau",
                                  cuisine="Bahamian", max_price=5, min_rating=4.9,
                                  dietary=["vegan"], top_k=10)),
    },
    {
        "desc": "A diet passed as a CUISINE is converted to a dietary requirement",
        # Measured defect: the local model called the tool with cuisine='Vegan'
        # and vegan=False, which demoted a requirement into a relaxable
        # preference and returned non-vegan places to a vegan diner.
        # The invariant: no non-vegan Nassau restaurant may appear, no matter
        # how the constraint arrived or what the loop had to relax.
        "check": lambda: not any(
            name in find_restaurants(query="vegan dinner", city="Nassau",
                                     cuisine="Vegan", min_rating=4.5)
            for name in ("Graycliff Dining", "Bamboo Shack", "Conch Corner")
        ),
    },
    {
        "desc": "A dietary word in the request survives even if the model omits the flag",
        "check": lambda: all(
            item["vegan"] for item in search_restaurants(
                "vegan dinner", city="Nassau",
                dietary=parse_task("highly rated vegan dinner in Nassau")["dietary"],
                top_k=10)
        ),
    },
    {
        "desc": "A city outside coverage is REFUSED, not answered with the wrong country",
        # Joel's destination layer on main carries 47 cities and shares one with
        # this agent. The orchestrator will name cities this agent has never
        # heard of, and answering anyway would put a Caribbean restaurant into a
        # Tokyo itinerary.
        "check": lambda: (
            "Coverage limit" in format_for_itinerary(
                [], city_uncovered=parse_task("seafood dinner in Tokyo under $40")["city_uncovered"])
            and parse_task("seafood dinner in Tokyo under $40")["city_uncovered"] == "Tokyo"
        ),
    },
    {
        "desc": "A covered city is NOT mistaken for an uncovered one, accents included",
        "check": lambda: (
            parse_task("dinner in Cancun")["city"] == "Cancun"
            and parse_task("dinner in Canc\u00fan")["city"] == "Cancun"
            and parse_task("dinner in San Juan")["city_uncovered"] is None
        ),
    },
    {
        "desc": "No city named at all still yields a stated assumption, not a refusal",
        "check": lambda: (
            parse_task("somewhere good for dinner")["city_uncovered"] is None
            and len(parse_task("somewhere good for dinner")["assumptions"]) > 0
        ),
    },
    {
        "desc": "The dietary safety net is per-request, not shared between callers",
        # It is a ContextVar, so two travellers answered at once cannot inherit
        # each other's dietary requirements.
        "check": lambda: (
            __import__("restaurant_agent_ollama")._CURRENT_TASK.__class__.__name__ == "ContextVar"
        ),
    },
    {
        "desc": "Relaxation order is published and puts price last",
        "check": lambda: (
            RELAXATION_ORDER == ("min_rating", "cuisine", "max_price")
        ),
    },
    {
        "desc": "Every adjustment is stated in the final message, never silent",
        "check": lambda: (
            lambda r, x: "Adjusted:" in format_for_itinerary(r, relaxations=x)
        )(*search_with_reflection("vegan gluten-free lunch", city="Honolulu",
                                  max_price=15, dietary=["vegan", "gluten-free"],
                                  top_k=10)),
    },
    {
        "desc": "An adjusted message still asks the orchestrator no questions",
        "check": lambda: (
            lambda r, x: "?" not in format_for_itinerary(r, relaxations=x)
        )(*search_with_reflection("vegan gluten-free lunch", city="Honolulu",
                                  max_price=15, dietary=["vegan", "gluten-free"],
                                  top_k=10)),
    },
]


# -----------------------------------------------------------------------------
# SECTION D - the model does not get the last word
# -----------------------------------------------------------------------------
# Measured 20 Aug 2026 through the group's orchestrator shell: the tool found
# Pan y Cafe at $12 and wrote an "Adjusted:" line; the model replied "no
# restaurant was found". These lock the deterministic override that stops a
# successful search being reported as a failure. No LLM required - the guard is
# a pure function over two strings.

_TOOL_HIT = (
    "Adjusted: No Seafood option matched the other requirements, so the "
    "cuisine preference was dropped for this search.\n"
    "Recommended restaurant: Pan y Cafe - Cafe, San Juan. About $12 per "
    "person, rated 4.2/5. Dietary: vegetarian.\n"
    "Why: Budget breakfast and coffee spot."
)
_TOOL_CLEAN = (
    "Recommended restaurant: Sunset Vegan Kitchen - Vegan, Aruba. About $26 "
    "per person, rated 4.8/5. Dietary: vegetarian, vegan, gluten-free."
)
_TOOL_REFUSAL = (
    "Coverage limit: this restaurant agent holds records for Aruba, Cancun, "
    "Honolulu, Montego Bay, Nassau, San Juan only. Tokyo is outside that "
    "coverage, so no restaurant has been recommended and nothing has been "
    "invented."
)

def _child_context_capture_works():
    """Reproduce the 20 Aug bug directly.

    The agent framework runs each tool call in a child context. The first
    version of this guard stored the tool output in a ContextVar set inside the
    tool, and a value set in a child context never reaches the parent - so
    answer() always saw nothing and the guard never fired. The list is installed
    by the caller now, so the tool appends through a reference that does travel.
    """
    import contextvars
    token = _TOOL_OUTPUTS.set([])
    try:
        contextvars.copy_context().run(_record_tool_output, _TOOL_HIT)
        captured = _TOOL_OUTPUTS.get()
        return len(captured) == 1 and "Pan y Cafe" in captured[0]
    finally:
        _TOOL_OUTPUTS.reset(token)


# A tool reply carrying three restaurants, used by the cuisine-fidelity checks.
_TOOL_SAN_JUAN = (
    "Recommended restaurant: La Marea Grill - Seafood, San Juan. "
    "About $40 per person, rated 4.5/5. Dietary: gluten-free.\n"
    "\n"
    "Alternatives:\n"
    "- Casa Boricua - Puerto Rican, San Juan. About $24 per person, rated 4.6/5.\n"
    "- El Fuego Steak - Steakhouse, San Juan. About $58 per person, rated 4.4/5."
)


GUARD_CASES = [
    {
        "desc": "A model that discards the tool's pick is overruled, not trusted",
        "check": lambda: "Pan y Cafe" in _enforce_tool_result(
            "No cheap local seafood restaurant in San Juan was found within a "
            "$15 per person budget.", _TOOL_HIT),
    },
    {
        "desc": "Overruling carries the Adjusted line, so the swap is never silent",
        "check": lambda: _enforce_tool_result(
            "No restaurant was found.", _TOOL_HIT).startswith("Adjusted:"),
    },
    {
        "desc": "A model that reports the pick faithfully is left alone",
        "check": lambda: _enforce_tool_result(
            "Adjusted: cuisine dropped. Recommended restaurant: Pan y Cafe - "
            "Cafe, San Juan.", _TOOL_HIT).startswith("Adjusted: cuisine dropped"),
    },
    {
        "desc": "A model that keeps the pick but hides the adjustment has it restored",
        "check": lambda: _enforce_tool_result(
            "Recommended restaurant: Pan y Cafe - Cafe, San Juan.",
            _TOOL_HIT).startswith("Adjusted:"),
    },
    {
        "desc": "A clean hit with no adjustment is passed through untouched",
        "check": lambda: _enforce_tool_result(
            "Recommended restaurant: Sunset Vegan Kitchen - Vegan, Aruba.",
            _TOOL_CLEAN) == "Recommended restaurant: Sunset Vegan Kitchen - Vegan, Aruba.",
    },
    {
        "desc": "A coverage refusal is never overridden into a recommendation",
        "check": lambda: _enforce_tool_result(
            "No restaurants were found in Tokyo because it is outside our "
            "coverage area.", _TOOL_REFUSAL
        ) == ("No restaurants were found in Tokyo because it is outside our "
              "coverage area."),
    },
    {
        "desc": "Tool output recorded in a CHILD context still reaches answer() (the 20 Aug bug)",
        "check": _child_context_capture_works,
    },
    {
        "desc": "A later empty tool call does not erase an earlier real recommendation",
        "check": lambda: "Pan y Cafe" in _enforce_tool_result(
            "No restaurant was found.",
            [_TOOL_HIT, "No restaurant matched that request."]),
    },
    {
        "desc": "No tool call at all leaves the model's reply untouched",
        "check": lambda: _enforce_tool_result("Anything at all.", []) == "Anything at all.",
    },
    {
        "desc": "A cuisine the tool never said is caught (El Fuego Steak was a Steakhouse, not Seafood)",
        "check": lambda: not _cuisine_claims_are_faithful(
            "La Marea Grill - Seafood, San Juan. Alternatives: "
            "El Fuego Steak - Seafood, San Juan, about $58 per person.",
            _TOOL_SAN_JUAN),
    },
    {
        "desc": "An em dash does not let a wrong cuisine through",
        "check": lambda: not _cuisine_claims_are_faithful(
            "El Fuego Steak \u2014 Seafood, San Juan", _TOOL_SAN_JUAN),
    },
    {
        "desc": "Correct cuisines are left alone, in both dash and bracket styles",
        "check": lambda: _cuisine_claims_are_faithful(
            "La Marea Grill - Seafood, San Juan. El Fuego Steak (Steakhouse, $58).",
            _TOOL_SAN_JUAN),
    },
    {
        "desc": "Prose about a restaurant is not mistaken for a cuisine claim",
        "check": lambda: _cuisine_claims_are_faithful(
            "La Marea Grill serves great seafood, and El Fuego Steak is worth a look.",
            _TOOL_SAN_JUAN),
    },
    {
        "desc": "A mislabelled cuisine makes the tool's own wording win",
        "check": lambda: "Steakhouse" in _enforce_tool_result(
            "El Fuego Steak - Seafood, San Juan.", [_TOOL_SAN_JUAN]),
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

    print("\nSECTION C - the reflection step (second look)\n")
    for c in REFLECTION_CASES:
        try:
            ok = bool(c["check"]())
        except Exception as error:
            ok = False
            print("   (error:", error, ")")
        print(f"[{'PASS' if ok else 'FAIL'}]  {c['desc']}")
        if ok:
            passed += 1

    print("\nSECTION D - the model does not get the last word\n")
    for c in GUARD_CASES:
        try:
            ok = bool(c["check"]())
        except Exception as error:
            ok = False
            print("   (error:", error, ")")
        print(f"[{'PASS' if ok else 'FAIL'}]  {c['desc']}")
        if ok:
            passed += 1

    total = (len(CASES) + len(CONTRACT_CASES) + len(REFLECTION_CASES)
             + len(GUARD_CASES))
    print("\n" + "-" * 60)
    print(f"  SCORE: {passed}/{total} checks passed")
    print("-" * 60 + "\n")
    return passed == total


if __name__ == "__main__":
    # Exit non-zero on failure, so the suite can actually gate something. A bare
    # run() always exited 0, which meant thirty passing checks could not block a
    # broken commit.
    raise SystemExit(0 if run() else 1)
