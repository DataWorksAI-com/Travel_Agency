"""
Money & Customs Agent -- built with Deep Agents (LangChain) + Cerebras.

Combines three tools (money_tools.py) into one agent that gives a traveller:
  - the live exchange rate between their currency and the destination's
  - money customs for the destination (tipping/haggling, per service)
  - rough income context, so they have a sense of local price scale

Follows the group's shared sub-agent contract: one task string in, one
self-contained message out. Never asks a follow-up question -- if
something is missing or ambiguous, it states an assumption and answers
anyway (same policy as Budget and Restaurants).
"""

import os

# ---------------------------------------------------------------------------
# API KEY -- set directly here for local testing.
# Do NOT share this file or upload it anywhere with your real key still in it.
# For shared/repo use, prefer setting this via a real .env file instead
# (see .env.example) and python-dotenv, rather than hardcoding it here.
# ---------------------------------------------------------------------------
os.environ.setdefault("CEREBRAS_API_KEY", "your-actual-cerebras-key-here")

from langchain_cerebras import ChatCerebras
from deepagents import create_deep_agent

from money_tools import get_exchange_rate, get_money_customs, get_income_context


MODEL = os.environ.get("MONEY_AGENT_MODEL", "gpt-oss-120b")

SYSTEM_PROMPT = (
    "You are the Money & Customs agent in a multi-agent travel-planning "
    "system. An orchestrator sends you one task in plain words and uses "
    "your reply directly in a customer itinerary.\n"
    "\n"
    "You are an expert in currency exchange, tipping/haggling customs, and "
    "rough local price scale for destinations worldwide.\n"
    "\n"
    "RULES YOU MUST FOLLOW:\n"
    "1. For currency conversion, use get_exchange_rate.\n"
    "2. For tipping/haggling norms, use get_money_customs. Pass a specific "
    "'service' (restaurants, taxis, hotel_housekeeping, tour_guides) if the "
    "traveller asked about one in particular; otherwise call it without a "
    "service for the full breakdown.\n"
    "3. For a sense of local price scale, use get_income_context. Always "
    "state clearly that this is a national AVERAGE (GNI per capita), not a "
    "city-level median, and frame it as rough context, never a precise "
    "benchmark.\n"
    "4. Only report what the tools return. Never invent an exchange rate, "
    "custom, or income figure.\n"
    "5. NEVER ask a follow-up question and never request clarification. You "
    "get exactly one turn. If something is missing or ambiguous (e.g. no "
    "origin currency given), make one reasonable assumption, state it in a "
    "line beginning 'Assumption:', and answer anyway.\n"
    "6. If a tool returns found=False, say plainly that the information "
    "isn't available for that country/service rather than guessing.\n"
    "7. Reply with ONE self-contained message covering everything the task "
    "asked for. No follow-up questions, no filler.\n"
)

_AGENT = None


def build_agent():
    """Construct and return the Money & Customs deep agent, ready to invoke."""
    global _AGENT
    if _AGENT is None:
        llm = ChatCerebras(model=MODEL)
        _AGENT = create_deep_agent(
            model=llm,
            tools=[get_exchange_rate, get_money_customs, get_income_context],
            system_prompt=SYSTEM_PROMPT,
        )
    return _AGENT


def answer(task: str) -> str:
    """Answer one orchestrator task and return one self-contained message.

    Args:
        task: everything this agent needs, in one plain-language string --
            e.g. origin and destination, and what the traveller wants to
            know (exchange rate, customs, price scale, or all three).

    Returns:
        A single itinerary-ready message with no follow-up questions.
    """
    if not task or not task.strip():
        return ("No task text was received, so no money/customs lookup "
                 "could be run. Send the request as one string including "
                 "the origin and destination, e.g. 'Traveling from the US "
                 "to Japan -- exchange rate, tipping customs, and price scale'.")

    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": task.strip()}]})
    message = result["messages"][-1]
    content = getattr(message, "content", message)
    return content if isinstance(content, str) else str(content)


if __name__ == "__main__":
    print("--- Hello world ---")
    print(answer("Just say hello world so I know you're running."))

    print("\n--- Full scenario ---")
    print(answer(
        "I'm traveling from the USA to France. What's the current exchange "
        "rate, should I tip at restaurants and hotels, and what's the "
        "general price scale like there?"
    ))
