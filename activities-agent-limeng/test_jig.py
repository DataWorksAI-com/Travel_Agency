"""
Test Jig for the Activities Agent (multi-city)
--------------------------------------------------
A "test jig" = a set of prompts paired with expected answers, run
through a scoring loop, so you can tell at a glance whether the agent
is still behaving correctly after a change.

Two levels here:
1. TOOL TESTS (deterministic, no LLM) — call the tier 1/2 tool
   functions directly and assert exact behavior.
2. BLACK-BOX AGENT TESTS (via answer()) — send a task string through
   the full agent and check the final message for expected keywords.
   LLM output varies run to run, so these are keyword-based checks.

Run:
    python test_jig.py
"""

import asyncio
from activities_agent import search_activities_local_exact, search_activities_semantic, answer, _covered_cities


# ---------------------------------------------------------------------
# 1. Tool tests (deterministic)
# ---------------------------------------------------------------------

def run_tool_tests():
    print("=" * 60)
    print("TOOL TESTS (deterministic)")
    print("=" * 60)

    cases = []

    cases.append(("4 cities covered", set(_covered_cities()) == {"Kyoto", "New York", "Paris", "Rome"}))

    r = search_activities_local_exact("Paris", category="art")
    cases.append(("Paris exact filter: art returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    r = search_activities_local_exact("Kyoto", category="outdoor")
    cases.append(("Kyoto exact filter: outdoor returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    r = search_activities_local_exact("Rome", category="food")
    cases.append(("Rome exact filter: food returns error (out of scope)", "error" in r))

    r = search_activities_local_exact("Miami")
    cases.append(("Miami: uncovered city returns error with covered_cities list", "error" in r and "covered_cities" in r))

    r = search_activities_semantic(query="a romantic evening spot", city="Paris")
    cases.append(("semantic search: Paris query returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    r = search_activities_semantic(query="ancient ruins and history")
    cases.append(("semantic search: cross-city query (no city filter) returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

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
        "description": "correctly finds a real free outdoor Kyoto activity",
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

    print(f"\n{passed}/{len(BLACK_BOX_CASES)} black-box tests passing\n")
    return passed, len(BLACK_BOX_CASES)


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
