"""
Builds the Budget Agent.

This agent runs standalone -- same pattern as Destination, Flights,
Activities, and Restaurants -- and does NOT depend on any other
sub-agent's output. Given a destination + the user's stated budget
(+ optional trip length), it reasons about feasibility using its own
knowledge source: typical per-destination cost ranges for flights,
lodging, food, and activities.

Per the orchestrator/sub-agent contract: this agent takes ONE
self-contained task string from the orchestrator and returns ONE
self-contained final message -- no follow-up questions.
"""

from langchain.chat_models import init_chat_model

from deepagents import create_deep_agent

from .config import load_settings
from .tools import ALL_TOOLS

SYSTEM_PROMPT = """You are the Budget Agent in a multi-agent travel \
planning system.

You receive a single task string from the orchestrator containing a \
destination, the user's stated budget, and optionally a trip length \
in days. You do NOT wait on or depend on any other sub-agent's \
output -- reason entirely from your own tools.

Your job:
1. Use get_cost_estimate to look up typical costs for the destination.
2. Use check_feasibility to estimate the total trip cost and compare \
it against the stated budget.

Always finish with ONE clear, self-contained message stating:
- The estimated total cost and its breakdown (flight, lodging, food, \
activities)
- Whether the budget is feasible for this trip, and by how much it's \
over or under

Do not ask the orchestrator or user any follow-up questions. If trip \
length isn't given, assume a reasonable default (e.g. 3 days) and \
state that assumption clearly in your final message.
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
