#!/usr/bin/env python3
"""
Isolated integration test: calls your Budget Agent through the EXACT
same path the orchestrator uses (orchestrator_config.get_client("budget")
-> LocalFunctionClient.call()), without needing Destination/Flights/
Restaurants/Activities/Money&Customs to exist yet.

This proves your agent is correctly wired for orchestration, since it
goes through the real orchestrator_config.py / subagent_client.py code,
not a hand-rolled call to build_agent() directly.

Run with:
    python test_budget_integration.py
"""

import asyncio

from orchestrator_config import get_client


async def main():
    client = get_client("budget")

    # Simulates roughly what orchestrator.py's _build_budget_task() sends:
    # unstructured text bundling destination/flights/restaurants/activities
    # info plus the stated budget -- NOT a clean "Destination: X" string.
    task = (
        "Budget: $2000\n\n"
        "Destination info: Recommended destination: Cancun, Mexico. "
        "Known for beaches and snorkeling, a 7-day trip is typical.\n\n"
        "Flights: JetBlue direct flight, Boston to Cancun, approximately "
        "$430 round trip.\n\n"
        "Restaurants: Several seafood restaurants near the hotel zone, "
        "average $20-35 per meal.\n\n"
        "Activities: Snorkeling tours and a Chichen Itza day trip "
        "recommended, roughly $270 total.\n\n"
        "(NOTE: this is unstructured text, not structured line-item dicts.)"
    )

    print("Calling Budget Agent through orchestrator_config.get_client('budget')...")
    print(f"\nTask sent:\n{task}\n")

    result = await client.call(task)

    print("=" * 60)
    print("Budget Agent response:")
    print("=" * 60)
    print(result)

    if result.startswith("[budget unavailable]") or result.startswith("[subagent error]"):
        print("\n⚠️  Something went wrong -- check the error message above.")
        print("Common causes:")
        print("  - budget_agent/ isn't sitting next to this script (or on sys.path)")
        print("  - .env is missing your API key")
        print("  - chroma_db/ hasn't been built yet (run scripts/build_vectorstore.py)")
    else:
        print("\n✅ Budget Agent responded successfully through the orchestrator's client interface.")


if __name__ == "__main__":
    asyncio.run(main())
