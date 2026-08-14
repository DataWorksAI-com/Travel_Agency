"""
Tools for the Budget Cost Aggregator Agent.

Unlike the other sub-agents in the system (Destination, Flights,
Activities, Restaurants), this agent does not call any external API or
knowledge source. Its "knowledge" is purely the priced line items it
receives from the other sub-agents inside its task string. Its logic
is pure computation:

  1. aggregate_costs   -- sum line items into a total
  2. check_budget      -- compare total against the stated budget
  3. suggest_adjustment -- if over budget, recommend which item(s) to
                            cut or swap to close the gap

This keeps the agent fully deterministic and cheap to run -- it never
needs a vector DB, REST API, or MCP server, which is worth calling out
for the "classic vs agentic RAG" comparison in the blog: not every
agent in a multi-agent system needs a retrieval or external-data layer.
"""

from langchain_core.tools import tool


@tool
def aggregate_costs(line_items: list[dict]) -> dict:
    """Sum a list of priced line items into a total trip cost.

    Args:
        line_items: A list of dicts, each with at least:
            - "category": e.g. "flights", "restaurants", "activities"
            - "name": short description, e.g. "JetBlue B6 204"
            - "cost": numeric cost in USD

    Returns:
        A dict with the total cost and a breakdown by category.
    """
    total = 0.0
    by_category: dict[str, float] = {}

    for item in line_items:
        cost = float(item.get("cost", 0))
        category = item.get("category", "uncategorized")
        total += cost
        by_category[category] = by_category.get(category, 0.0) + cost

    return {
        "total_cost": round(total, 2),
        "by_category": {k: round(v, 2) for k, v in by_category.items()},
        "item_count": len(line_items),
    }


@tool
def check_budget(total_cost: float, budget: float) -> dict:
    """Compare a total trip cost against the user's stated budget.

    Args:
        total_cost: The aggregated total cost of the trip so far.
        budget: The user's stated maximum budget.

    Returns:
        A dict describing whether the trip is within budget, and by
        how much it is over or under.
    """
    difference = round(budget - total_cost, 2)

    if difference >= 0:
        status = "within_budget"
    else:
        status = "over_budget"

    return {
        "status": status,
        "total_cost": round(total_cost, 2),
        "budget": round(budget, 2),
        "difference": difference,  # positive = under budget, negative = over
    }


@tool
def suggest_adjustment(line_items: list[dict], overage: float) -> list[dict]:
    """Suggest which line item(s) to cut or downgrade to close a budget gap.

    Uses a simple greedy strategy: sorts non-essential-looking items
    (anything not categorized as "flights", since flights are usually
    fixed once booked) by cost descending, and proposes dropping/
    downgrading the smallest number of items needed to cover the
    overage.

    Args:
        line_items: The same list of priced line items used in
            aggregate_costs.
        overage: The positive dollar amount the trip is over budget by.

    Returns:
        A list of suggested items to cut or downgrade, cheapest set
        that covers the overage, most impactful first.
    """
    if overage <= 0:
        return []

    # Treat flights as fixed/non-adjustable; everything else is a candidate.
    adjustable = [item for item in line_items if item.get("category") != "flights"]
    adjustable_sorted = sorted(adjustable, key=lambda i: float(i.get("cost", 0)), reverse=True)

    suggestions = []
    covered = 0.0
    for item in adjustable_sorted:
        if covered >= overage:
            break
        suggestions.append(
            {
                "name": item.get("name", "unknown item"),
                "category": item.get("category", "uncategorized"),
                "cost": item.get("cost", 0),
                "action": "cut_or_downgrade",
            }
        )
        covered += float(item.get("cost", 0))

    return suggestions


ALL_TOOLS = [aggregate_costs, check_budget, suggest_adjustment]
