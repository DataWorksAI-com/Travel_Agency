"""
orchestrator.py -- routes, sequences, and assembles the five subagents into
one itinerary response.

This is a SKELETON. It runs today against LocalFunctionClient stand-ins
(see orchestrator_config.py) and is deliberately structured so real
subagent code -- and later, a real SLIM transport -- can be dropped in
without changing the logic below. See ORCHESTRATOR_DESIGN.md for the
open decisions this file currently makes a provisional call on.

Sequencing, per the actual dependencies found while reviewing each
subagent's code (not a guess):
  1. Destination runs first -- Flights/Restaurants/Activities all need a
     resolved city; Destination is the only subagent that can produce one
     from either a named city or vague preferences.
  2. Flights, Restaurants, Activities run in parallel -- none of the three
     depends on either of the other two's output.
  3. Budget runs last -- its own docstring states its knowledge is "purely
     the priced line items it receives from the other sub-agents," so it
     cannot run before they have.

Money & Customs is NOT its own pipeline stage (see ORCHESTRATOR_DESIGN.md,
decision #3) -- it's called once here, by the orchestrator itself, and its
facts are folded into the task strings sent to the subagents that need
them, rather than every subagent importing it independently.
"""

import asyncio

from orchestrator_config import get_client


async def _call_money_customs_context(origin_country: str, destination_country: str) -> str:
    """Call Money & Customs once, return a short context blurb to prepend
    to other subagents' task strings.

    TODO (ORCHESTRATOR_DESIGN.md, decision #3): confirm this is really the
    right place for this call. Alternative: only call it for the subagents
    that actually need it (e.g. Restaurants for tipping, not Activities),
    rather than one blurb prepended everywhere.
    """
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
    """Run Flights, Restaurants, Activities together -- none depends on
    the others' output, only on Destination having already resolved a
    city (assumed already folded into `task` by the caller).

    TODO (ORCHESTRATOR_DESIGN.md, decision #4): this currently has no
    uniform failure policy. If one of the three comes back with an
    error-shaped message, what should happen to final assembly -- omit
    that section and say so, retry once, or something else? Decide this
    before relying on the placeholder behavior below (currently: pass
    whatever came back straight through, error message or not).
    """
    flights_task = f"{money_context}\n\n{task}" if money_context else task
    restaurants_task = f"{money_context}\n\n{task}" if money_context else task
    activities_task = task  # money/customs likely irrelevant here -- confirm

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
    """Turn the other subagents' free-text replies into the line-item
    format Budget's tools actually expect (aggregate_costs wants a list
    of {"category", "name", "cost"} dicts).

    TODO: this is the biggest unresolved gap in the whole skeleton. Every
    other subagent returns natural-language text (per the shared
    itinerary-ready contract), but Budget's tools need structured dicts.
    Something has to parse dollar amounts and categories out of
    Flights/Restaurants/Activities' text replies before Budget can run at
    all. Options worth deciding between:
      (a) an LLM call here in the orchestrator that extracts structured
          line items from the three free-text replies
      (b) asking Flights/Restaurants/Activities to ALSO return a small
          structured block alongside their prose (breaking their current
          "reply with ONE self-contained message" contract)
      (c) something else
    Neither is implemented below -- this is a placeholder pass-through.
    """
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
    """Combine every subagent's reply into one itinerary.

    TODO (ORCHESTRATOR_DESIGN.md, decision #1): once every subagent
    agrees on a single ask-vs-assume policy, this is also where any
    'Assumption:' lines from subagents should probably be surfaced
    together, rather than buried inline per section as they are now.
    """
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
    """Top-level entry point: one user request in, one assembled itinerary out.

    This is intentionally the ONLY function meant to be called from outside
    this file. Everything above is internal sequencing.
    """
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
