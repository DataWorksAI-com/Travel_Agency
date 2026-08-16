"""
Tools for the standalone Budget Agent.

Unlike an aggregator that depends on other agents' outputs, this
agent runs independently -- same as Destination, Flights, Activities,
and Restaurants. Given just a destination + stated budget (+ optional
trip length), it reasons about feasibility using its OWN knowledge
source: typical cost ranges per destination (flights, lodging, food,
activities). It never waits on or reads what other agents booked.

Tools:
  1. get_cost_estimate  -- look up typical per-day cost ranges for a
                            destination from the knowledge base
  2. check_feasibility  -- estimate a total trip cost from those
                            ranges and compare against the user's
                            stated budget
"""

from langchain_core.tools import tool

# Mock "knowledge base" of typical costs per destination (USD).
# In place of Numbeo/cost-of-living API or a maintained dataset for now.
_COST_ESTIMATES = {
    "cancun": {
        "flight_roundtrip": 450,
        "lodging_per_day": 90,
        "food_per_day": 40,
        "activities_per_day": 35,
    },
    "maui": {
        "flight_roundtrip": 750,
        "lodging_per_day": 220,
        "food_per_day": 65,
        "activities_per_day": 60,
    },
    "phuket": {
        "flight_roundtrip": 1100,
        "lodging_per_day": 50,
        "food_per_day": 20,
        "activities_per_day": 25,
    },
}


@tool
def get_cost_estimate(destination: str) -> dict:
    """Look up typical per-day cost ranges for a tropical destination.

    Args:
        destination: Name of the destination, e.g. "Cancun", "Maui", "Phuket".

    Returns:
        A dict with round-trip flight estimate and per-day lodging,
        food, and activities costs, or an error if unknown.
    """
    key = destination.strip().lower()
    if key not in _COST_ESTIMATES:
        return {"error": f"No cost data for '{destination}'. Known: {list(_COST_ESTIMATES.keys())}"}
    return {"destination": destination, **_COST_ESTIMATES[key]}


@tool
def check_feasibility(destination: str, budget: float, days: int = 3) -> dict:
    """Estimate total trip cost for a destination and check it against budget.

    Args:
        destination: Name of the destination, e.g. "Cancun", "Maui", "Phuket".
        budget: The user's stated total budget in USD.
        days: Number of days for the trip (defaults to 3).

    Returns:
        A dict with the estimated total cost, a cost breakdown, and
        whether the trip is feasible within budget.
    """
    key = destination.strip().lower()
    if key not in _COST_ESTIMATES:
        return {"error": f"No cost data for '{destination}'. Known: {list(_COST_ESTIMATES.keys())}"}

    rates = _COST_ESTIMATES[key]
    lodging = rates["lodging_per_day"] * days
    food = rates["food_per_day"] * days
    activities = rates["activities_per_day"] * days
    flight = rates["flight_roundtrip"]
    total = flight + lodging + food + activities

    difference = round(budget - total, 2)
    status = "feasible" if difference >= 0 else "not_feasible"

    return {
        "destination": destination,
        "days": days,
        "estimated_total": round(total, 2),
        "breakdown": {
            "flight_roundtrip": flight,
            "lodging": round(lodging, 2),
            "food": round(food, 2),
            "activities": round(activities, 2),
        },
        "budget": round(budget, 2),
        "difference": difference,  # positive = under budget, negative = over
        "status": status,
    }


ALL_TOOLS = [get_cost_estimate, check_feasibility]
