"""
orchestrator.py -- routes, sequences, and assembles the three subagents into
one itinerary response.

This is a SKELETON. It runs today against LocalFunctionClient stand-ins
(see orchestrator_config.py) and is deliberately structured so real
subagent code -- and later, a real SLIM transport -- can be dropped in
without changing the logic below. See ORCHESTRATOR_DESIGN.md for the
open decisions this file currently makes a provisional call on.

Sequencing, per the actual dependencies found while reviewing each
subagent's code (not a guess):
  1. Destination runs first -- Flights needs a resolved city; Destination
     is the only subagent that can produce one from either a named city or
     vague preferences.
  2. Flights runs next.

Money & Customs is NOT its own pipeline stage (see ORCHESTRATOR_DESIGN.md,
decision #3) -- it's called once here, by the orchestrator itself, and its
facts are folded into the task strings sent to the subagents that need
them, rather than every subagent importing it independently.
"""

import asyncio
import sys
import os

from orchestrator_config import get_client

# The only slot names that may reach get_client. Worth a guard now that a model
# picks them: orchestrator_config.get_client swallows its own KeyError, so an
# unknown name returns "[typo unavailable] 'typo'", and agent_seam falls back to
# modes.get(name, DUMMY) -- sample data. A hallucinated slot would come back as
# plausible prose instead of an error.
SLOTS = ("destination", "flights", "money_customs")


async def ask_slot(slot: str, task: str) -> str:
    """Call one subagent by slot name.

    `get_client` is looked up as a module global on purpose: ui/agent_seam.py
    rebinds `orchestrator.get_client` as its single intervention, and that only
    works if the name resolves here at call time. Importing get_client into
    another module, or caching a client at construction time, silently disables
    real/dummy mode, failure detection, timing and every per-agent UI step.
    """
    if slot not in SLOTS:
        raise ValueError(f"unknown slot {slot!r}; expected one of {SLOTS}")
    return await get_client(slot).call(task)


async def _call_money_customs_context(origin_country: str, destination_country: str) -> str:
    """Call Money & Customs once, return a short context blurb to prepend
    to other subagents' task strings.

    TODO (ORCHESTRATOR_DESIGN.md, decision #3): confirm this is really the
    right place for this call. Alternative: only call it for the subagents
    that actually need it, rather than one blurb prepended everywhere.
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
    """Run Flights, which depends only on Destination having already
    resolved a city (assumed already folded into `task` by the caller).

    TODO (ORCHESTRATOR_DESIGN.md, decision #4): this currently has no
    uniform failure policy. If Flights comes back with an error-shaped
    message, what should happen to final assembly -- omit that section and
    say so, retry once, or something else? Decide this before relying on
    the placeholder behavior below (currently: pass whatever came back
    straight through, error message or not).
    """
    flights_task = f"{money_context}\n\n{task}" if money_context else task

    flights_client = get_client("flights")

    flights_result = await flights_client.call(flights_task)
    # qwen3:8b sometimes hands back the Money & Customs text it was given as
    # its own answer, or nothing at all; neither may appear as the Flights section.
    if not flights_result.strip() or (money_context and money_context.strip()[:80] in flights_result):
        flights_result = "The Flights agent didn't return results."

    return {
        "flights": flights_result,
    }


def _assemble_itinerary(destination: str, parallel: dict, money_context: str = "") -> str:
    """Combine every subagent's reply into one itinerary.

    TODO (ORCHESTRATOR_DESIGN.md, decision #1): once every subagent
    agrees on a single ask-vs-assume policy, this is also where any
    'Assumption:' lines from subagents should probably be surfaced
    together, rather than buried inline per section as they are now.
    """
    itinerary = (
        "=== Destination ===\n"
        f"{destination}\n\n"
        "=== Flights ===\n"
        f"{parallel['flights']}\n"
    )
    if money_context:
        itinerary += f"\n=== Money & Customs ===\n{money_context}\n"
    return itinerary


async def plan_trip(
    task: str,
    origin_country: str = "",
    destination_country: str = "",
    stated_budget: str = "",
) -> str:
    """Top-level entry point: one user request in, one assembled itinerary out.

    Dispatches to one of two orchestrators, selected by TRAVEL_UI_ORCHESTRATOR:

      deterministic (default) -- the fixed pipeline below. No model, so it stays
                                 reproducible, offline-testable and free.
      agent                   -- orchestrator_agent.plan_trip_agentic, a deep
                                 agent that decides who to call and with what.

    Both are kept: the deterministic path is the control condition the agent is
    measured against, not merely a fallback.
    """
    if os.getenv("TRAVEL_UI_ORCHESTRATOR", "deterministic").strip().lower() == "agent":
        # Deferred so the deterministic path never imports deepagents or a model
        # client -- that is what keeps it offline, keyless and free to test.
        # The path insert is required because Chainlit pops sys.path[0] after
        # loading app.py, so the repo root is not importable by the time this
        # runs (ui/agent_seam.py re-runs _ensure_paths every call for the same
        # reason).
        root = os.path.dirname(os.path.abspath(__file__))
        if root not in sys.path:
            sys.path.insert(0, root)
        from orchestrator_agent import plan_trip_agentic

        return await plan_trip_agentic(task, origin_country, destination_country, stated_budget)
    return await _plan_trip_fixed(task, origin_country, destination_country, stated_budget)


async def _plan_trip_fixed(
    task: str,
    origin_country: str = "",
    destination_country: str = "",
    stated_budget: str = "",
) -> str:
    """The original fixed pipeline: Money & Customs, Destination, then
    Flights."""
    money_context = ""
    if origin_country and destination_country:
        money_context = await _call_money_customs_context(origin_country, destination_country)
        print(f"\n[DEBUG] Money & Customs said: {money_context}\n")


    destination_result = await _run_destination(task)

    # Same condition as Money & Customs: without both, the Flights model
    # invented an origin or answered the question itself.
    if origin_country and destination_country:
        parallel_results = await _run_parallel_subagents(task, money_context)
    else:
        parallel_results = {"flights": "No flight search made: a departure city and a destination are both needed."}

    return _assemble_itinerary(destination_result, parallel_results, money_context)


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
