"""
orchestrator.py -- routes, sequences, and assembles the five subagents into
one itinerary response.

This is a SKELETON. It runs today against LocalFunctionClient stand-ins
(see orchestrator_config.py) and is deliberately structured so real
subagent code -- and later, a real SLIM transport -- can be dropped in
without changing the logic below. See ORCHESTRATOR_DESIGN.md for the
open decisions this file currently makes a provisional call on.
"""

import asyncio

from orchestrator_config import get_client


async def _call_money_customs_context(origin_country: str, destination_country: str) -> str:
    client = get_client("money_customs")
    task = (
        f"Traveler is going from {origin_country} to {destination_country}. "
        f"Give the exchange rate and money customs (tipping/haggling) for "
        f"{destination_country}."
    )
    return await client.call(task)


async def _run_destination(task: str) -> str:
    client = get_client("destination")
    return await client.call(task)


async def _run_parallel_subagents(task: str, money_context: str) -> dict:
    flights_task = f"{money_context}\n\n{task}" if money_context else task
    restaurants_task = f"{money_context}\n\n{task}" if money_context else task
    activities_task = task

    flights_client = get_client("flights")
    restaurants_client = get_client("restaurants")
    activities_client = get_client("activities")

    flights_result, restaurants_result, activities_result = await asyncio.gather(
        flights_client.call(flights_task),
        restaurants_client.call(restaurants_task),
        activities_client.call(activities_task),
    )

    return {
        "flights": flights_result,
        "restaurants": restaurants_result,
        "activities": activities_result,
    }


def _build_budget_task(destination_result: str, parallel_results: dict, stated_budget: str) -> str:
    return (
        f"Budget: {stated_budget}\n\n"
        f"Destination info: {destination_result}\n\n"
        f"Flights: {parallel_results['flights']}\n\n"
        f"Restaurants: {parallel_results['restaurants']}\n\n"
        f"Activities: {parallel_results['activities']}\n\n"
        f"(NOTE: this is unstructured text, not the line-item dicts "
        f"Budget's tools expect -- see _build_budget_task's docstring.)"
    )


async def _run_budget(budget_task: str) -> str:
    client = get_client("budget")
    return await client.call(budget_task)


def _assemble_itinerary(destination: str, parallel: dict, budget: str) -> str:
    return (
        "=== Destination ===\n"
        f"{destination}\n\n"
        "=== Flights ===\n"
        f"{parallel['flights']}\n\n"
        "=== Restaurants ===\n"
        f"{parallel['restaurants']}\n\n"
        "=== Activities ===\n"
        f"{parallel['activities']}\n\n"
        "=== Budget ===\n"
        f"{budget}\n"
    )


async def plan_trip(
    task: str,
    origin_country: str = "",
    destination_country: str = "",
    stated_budget: str = "",
) -> str:
    """Top-level entry point: one user request in, one assembled itinerary out."""
    money_context = ""
    if origin_country and destination_country:
        money_context = await _call_money_customs_context(origin_country, destination_country)
        print(f"\n[DEBUG] Money & Customs said: {money_context}\n")

    destination_result = await _run_destination(task)

    parallel_results = await _run_parallel_subagents(task, money_context)

    budget_task = _build_budget_task(destination_result, parallel_results, stated_budget)
    budget_result = await _run_budget(budget_task)

    return _assemble_itinerary(destination_result, parallel_results, budget_result)


if __name__ == "__main__":
    # Hello-world check: runs even before any real subagent code exists,
    # since orchestrator_config.get_client() degrades a missing/broken
    # subagent to a plain error message instead of crashing.
    result = asyncio.run(
        plan_trip(
            task="Plan a week in Cancun for someone who likes snorkeling and seafood.",
            origin_country="USA",
            destination_country="Mexico",
            stated_budget="$2000",
        )
    )
    print(result)
