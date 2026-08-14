"""
Builds the Budget Cost Aggregator Agent.

This agent follows the orchestrator/sub-agent contract used across the
project:
  - Input: ONE task string from the orchestrator, containing the
    itemized costs already returned by Flights, Restaurants, and
    Activities, plus the user's stated budget.
  - Output: ONE self-contained final message -- total cost, whether
    it's within budget, and (if over) concrete suggestions for what
    to cut or downgrade. No follow-up questions back to the
    orchestrator; if something is ambiguous, it states an assumption
    and moves on.

Unlike the other sub-agents, this one does not run in parallel off the
orchestrator -- it only runs after Flights/Restaurants/Activities have
already produced priced results, and it needs no external API, MCP
server, or vector DB. Its tools are pure computation over the numbers
it's given.
"""

from langchain.chat_models import init_chat_model

from deepagents import create_deep_agent

from .config import load_settings
from .tools import ALL_TOOLS

SYSTEM_PROMPT = """You are the Budget Cost Aggregator agent in a \
multi-agent travel planning system.

You receive a single task string from the orchestrator. It will \
contain a list of priced line items (from Flights, Restaurants, and \
Activities sub-agents) and the user's stated budget.

Your job, in order:
1. Use the aggregate_costs tool to total the line items and break \
them down by category.
2. Use the check_budget tool to compare the total against the budget.
3. If over budget, use the suggest_adjustment tool to propose \
specific items to cut or downgrade, covering the overage with as few \
changes as possible. Never touch flights unless nothing else can \
cover the overage.

Always finish with ONE clear, self-contained message stating:
- The total cost and budget
- Whether the trip is within budget or over, and by how much
- If over budget, the specific suggested changes (name + cost of \
each item to cut/downgrade)

Do not ask the orchestrator or user any follow-up questions. If a \
line item is missing a category or cost, make a reasonable assumption \
and state it clearly in your final message.
"""


def build_agent(max_tokens: int = 2000):
    """Construct and return the Budget Deep Agent, ready to `.invoke(...)`.

    Args:
        max_tokens: Caps the response length per model call to keep
            costs low for this lightweight, computation-only agent.
    """
    settings = load_settings()

    model = init_chat_model(
        settings.model_string,  # e.g. "anthropic:claude-sonnet-4-6" or "openrouter:..."
        max_tokens=max_tokens,
    )

    agent = create_deep_agent(
        model=model,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )
    return agent
