"""
Numeric feasibility-check tool for the Budget Agent.

Cost data itself now comes from the RAG retrieval tool
(rag_tools.retrieve_cost_info), which pulls relevant text from the
vector store of city cost documents. This tool just does the final
arithmetic check once the agent has reasoned an estimated total cost
out of that retrieved text.
"""

from langchain_core.tools import tool


@tool
def check_feasibility(estimated_total_cost: float, budget: float) -> dict:
    """Check whether an estimated trip cost fits within the user's budget.

    Args:
        estimated_total_cost: The trip cost estimate, derived by
            reasoning over retrieved cost information (from
            retrieve_cost_info) for the relevant destination and trip
            length.
        budget: The user's stated total budget in USD.

    Returns:
        A dict with the difference (positive = under budget, negative
        = over budget) and a feasibility status.
    """
    difference = round(budget - estimated_total_cost, 2)
    status = "feasible" if difference >= 0 else "not_feasible"

    return {
        "estimated_total_cost": round(estimated_total_cost, 2),
        "budget": round(budget, 2),
        "difference": difference,
        "status": status,
    }


ALL_TOOLS = [check_feasibility]
