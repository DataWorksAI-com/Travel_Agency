"""
Test Jig for the merged Activities Agent
--------------------------------------------
A "test jig" = a set of prompts paired with expected answers, run
through a scoring loop, so you can tell at a glance whether the agent
is still behaving correctly after a change.

Two levels here:
1. TOOL TESTS (deterministic, no LLM) — call the tool functions
   directly and assert exact behavior.
2. BLACK-BOX AGENT TESTS (via answer()) — send a task string through
   the full agent and check the final message for expected keywords.
   LLM output varies run to run, so these are keyword-based checks.

Run:
    python test_jig.py
"""

import asyncio
from activities_agent import (
    search_activities_local_exact,
    search_activities_semantic,
    hard_filter_activities,
    list_curated_cities,
    expand_activities_corpus,
    answer,
    ask_activities,
    _covered_cities,
    _is_food_request,
)


# ---------------------------------------------------------------------
# 1. Tool tests (deterministic)
# ---------------------------------------------------------------------

def run_tool_tests():
    print("=" * 60)
    print("TOOL TESTS (deterministic)")
    print("=" * 60)

    cases = []

    # A SUPERSET, not set equality. The original assertion was
    #   set(_covered_cities()) == {the six seed cities}
    # which this agent's own tool breaks: expand_activities_corpus writes a new
    # city file into local_activity_docs/ on a cache miss, and _covered_cities()
    # reads that directory. So any live query for an uncovered city turns this
    # red -- a Cartagena request during a UI run did exactly that. The test was
    # asserting that a feature had never been used.
    #
    # What matters is that the six seed cities are all still there, which is
    # what a regression would remove. Extra cities are the corpus growing as
    # designed.
    SEED_CITIES = {"Kyoto", "New York", "Paris", "Rome", "Boston", "Chicago"}
    covered = set(_covered_cities())
    cases.append((
        f"6 seed cities still covered (4 from Limeng + 2 from Jainam); "
        f"{len(covered)} total",
        SEED_CITIES <= covered,
    ))

    # Deterministic domain-boundary guard
    cases.append(("food-request guard: catches an obvious food request", _is_food_request("Where should I get dinner in Paris?")))
    cases.append(("food-request guard: does not false-positive on an ordinary request", not _is_food_request("Find a free outdoor activity in Kyoto.")))

    # Tier 1 — exact filter, across cities from BOTH original agents
    r = search_activities_local_exact("Paris", category="art")
    cases.append(("Paris (Limeng's data) exact filter: art returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    r = search_activities_local_exact("Boston", category="sightseeing")
    cases.append(("Boston (Jainam's data) exact filter: sightseeing returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    r = search_activities_local_exact("Chicago", category="art")
    cases.append(("Chicago (Jainam's data) exact filter: art returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    r = search_activities_local_exact("Rome", category="food")
    cases.append(("Rome exact filter: food returns error (out of scope)", "error" in r))

    r = search_activities_local_exact("Miami")
    cases.append(("Miami: uncovered city returns error with covered_cities list", "error" in r and "covered_cities" in r))

    # Tier 2 — semantic search
    r = search_activities_semantic(query="a romantic evening spot", city="Paris")
    cases.append(("semantic search: Paris query returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    r = search_activities_semantic(query="historic walking path", city="Boston")
    cases.append(("semantic search: Boston (Jainam's data) query returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    r = search_activities_semantic(query="ancient ruins and history")
    cases.append(("semantic search: cross-city query (no city filter) returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    # Auxiliary tools (from Jainam) — deterministic, no LLM
    exact_result = search_activities_local_exact("Boston")
    filtered = hard_filter_activities(__import__("json").dumps(exact_result), free_only=True)
    filtered_parsed = __import__("json").loads(filtered)
    cases.append(("hard_filter_activities: free_only keeps only free activities", all(a["price_tier"] == "free" for a in filtered_parsed.get("activities", []))))

    cities_report = __import__("json").loads(list_curated_cities())
    # Same reason as the seed-city check above: a hardcoded count of 6 fails as
    # soon as expand_activities_corpus adds anything. What this should verify is
    # that the reported list agrees with what is actually on disk.
    cases.append((
        "list_curated_cities: reports every covered city",
        set(cities_report.get("curated_cities", [])) == covered,
    ))

    # Self-expanding corpus: never raises even without OPENTRIPMAP_API_KEY set
    r = expand_activities_corpus("SomeUncoveredCityForTesting")
    cases.append(("expand_activities_corpus: fails cleanly with no API key (no raise)", "error" in r))

    passed = sum(1 for _, ok in cases if ok)
    for name, ok in cases:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{len(cases)} tool tests passing\n")
    return passed, len(cases)


# ---------------------------------------------------------------------
# 2. Black-box agent tests (via answer())
# ---------------------------------------------------------------------

BLACK_BOX_CASES = [
    {
        "task": "Find a free outdoor activity in Kyoto.",
        "expect_any": ["bamboo", "fushimi", "inari"],
        "description": "correctly finds a real free outdoor Kyoto activity (Limeng's data)",
    },
    {
        "task": "What's a free thing to do in Boston?",
        "expect_any": ["freedom trail", "harborwalk"],
        "description": "correctly finds a real free Boston activity (Jainam's data)",
    },
    {
        "task": "Where should I get dinner in Paris?",
        "expect_any": ["restaurant", "food", "dining"],
        "description": "redirects food questions instead of answering them directly",
    },
    {
        "task": "Find underwater scuba diving in New York.",
        "expect_none": ["moma", "high line", "central park", "top of the rock", "ellis island", "broadway"],
        "description": "true negative — does not fabricate a real NY activity as a scuba answer",
    },
    {
        "task": "What can I do in Rome for culture?",
        "expect_any": ["colosseum", "forum", "vatican", "trastevere"],
        "description": "correctly finds real Rome cultural activities",
    },
]


async def run_black_box_tests():
    print("=" * 60)
    print("BLACK-BOX AGENT TESTS (via answer(), LLM in the loop)")
    print("=" * 60)

    passed = 0
    for case in BLACK_BOX_CASES:
        response = await answer(case["task"])
        response_lower = response.lower()

        if "expect_any" in case:
            ok = any(kw in response_lower for kw in case["expect_any"])
        else:
            ok = not any(kw in response_lower for kw in case["expect_none"])

        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {case['description']}")
        print(f"         task: {case['task']}")
        if not ok:
            print(f"         got: {response[:200]}...")

    # Backward-compatibility check: Jainam's original entry point still works
    result = await ask_activities("Chicago", interests="free outdoor")
    ok = "message" in result and isinstance(result["message"], str) and len(result["message"]) > 0
    passed += ok
    print(f"  [{'PASS' if ok else 'FAIL'}] ask_activities() backward-compatible wrapper still works")

    total = len(BLACK_BOX_CASES) + 1
    print(f"\n{passed}/{total} black-box tests passing\n")
    return passed, total


async def main():
    tool_passed, tool_total = run_tool_tests()
    bb_passed, bb_total = await run_black_box_tests()

    total_passed = tool_passed + bb_passed
    total = tool_total + bb_total
    print("=" * 60)
    print(f"TOTAL: {total_passed}/{total} passing")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
