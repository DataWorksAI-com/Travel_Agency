"""
Test Jig for the Activities Agent
------------------------------------
A "test jig" = a set of prompts paired with expected answers, run
through a scoring loop, so you can tell at a glance whether the agent
is still behaving correctly after a change — instead of eyeballing
the output every time.

Two levels here:

1. TOOL TESTS (deterministic, no LLM) — call search_activities_local_exact
   and search_activities_semantic directly and assert exact behavior.
   Fast, free, 100% reproducible. Good for catching a broken filter
   or a broken vector DB connection.

2. BLACK-BOX AGENT TESTS (via answer()) — send a task string through
   the full agent (LLM + tool-calling) and check the final message
   for expected keywords/patterns. This is what a teammate can run
   against your agent without reading your code — hence "black box."
   LLM output varies run to run, so these are keyword-based checks,
   not exact-match — some flakiness is expected and normal.

Run:
    python test_jig.py
"""

import asyncio
from activities_agent import search_activities_local_exact, search_activities_semantic, answer


# ---------------------------------------------------------------------
# 1. Tool tests (deterministic)
# ---------------------------------------------------------------------

def run_tool_tests():
    print("=" * 60)
    print("TOOL TESTS (deterministic)")
    print("=" * 60)

    cases = []

    # Exact filter returns results for a known category
    r = search_activities_local_exact(category="outdoor")
    cases.append(("exact filter: outdoor returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

    # Exact filter with a category that doesn't exist -> error dict, not a crash
    r = search_activities_local_exact(category="skydiving")
    cases.append(("exact filter: unknown category returns error dict", "error" in r))

    # Exact filter never returns food/dining (out of scope for this agent)
    r = search_activities_local_exact(category="food")
    cases.append(("exact filter: food category returns error (out of scope)", "error" in r))

    # Semantic search finds something for a vague query
    r = search_activities_semantic(query="a place with a great view")
    cases.append(("semantic search: vague query returns >=1 result", "error" not in r and len(r["activities"]) >= 1))

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
        "task": "Find a free outdoor activity in New York.",
        "expect_any": ["high line", "central park"],  # the only two free/outdoor NY entries
        "description": "correctly finds a real free outdoor NY activity",
    },
    {
        "task": "Where should I get dinner in New York?",
        "expect_any": ["restaurant", "food", "dining"],
        "description": "redirects food questions instead of answering them directly",
    },
    {
        "task": "Find underwater scuba diving in New York.",
        "expect_none": ["moma", "high line", "central park", "top of the rock", "ellis island", "broadway"],
        "description": "true negative — does not fabricate a real NY activity as a scuba answer",
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
        else:  # expect_none
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
