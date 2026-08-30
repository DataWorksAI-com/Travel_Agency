"""
Money & Customs Agent -- built with Deep Agents (LangChain) + OpenRouter
(free tier -- meta-llama/llama-3.3-70b-instruct:free by default).

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
os.environ.setdefault("COHERE_API_KEY", "REALKEYGOESHERE")

from langchain_cohere import ChatCohere
from deepagents import create_deep_agent

from money_tools import get_exchange_rate, search_money_customs, get_income_context, get_comparative_context


MODEL = os.environ.get("MONEY_AGENT_MODEL", "command-r-plus-08-2024")

SYSTEM_PROMPT = (
    "You are the Money & Customs agent in a multi-agent travel-planning "
    "system. An orchestrator sends you one task in plain words and uses "
    "your reply directly in a customer itinerary.\n"
    "\n"
    "You are an expert in currency exchange, tipping/haggling customs, and "
    "rough local price scale for destinations worldwide.\n"
    "\n"
    "RULES YOU MUST FOLLOW:\n"
    "1. For currency conversion, use get_exchange_rate. Report the 'rate' "
    "and 'date' fields EXACTLY as the tool returns them -- verbatim, "
    "character for character. Never substitute, reformat, guess, or "
    "'correct' the date based on what you expect today's date to be. The "
    "tool's date field is always the true, current source of truth; your "
    "own sense of the current date is not.\n"
    "2. For tipping/haggling norms, use search_money_customs. Pass a specific "
    "'service' (restaurants, taxis, hotel_housekeeping, tour_guides) if the "
    "traveller asked about one in particular; otherwise call it without a "
    "service for the full breakdown. This tool tries an exact match first, "
    "then a typo correction, then a semantic search over the same data if "
    "the country name is misspelled or phrased loosely -- it will still "
    "return the closest match rather than fail. CHECK THE 'adjusted' FIELD "
    "ON EVERY CALL. If it is non-null, your reply MUST begin with a line "
    "stating the correction verbatim before anything else -- for example: "
    "'Note: I interpreted \"<input>\" as <country>.' -- copying the country "
    "name straight from the tool's 'country' field. Do not summarize, "
    "paraphrase away, or silently omit this line. Only after that line may "
    "you continue with the customs details. If 'adjusted' is null, skip "
    "this line entirely -- do not invent a correction that didn't happen.\n"
    "3. For a sense of local price scale, use get_income_context. Always "
    "state clearly that this is a national AVERAGE (GNI per capita), not a "
    "city-level median, and frame it as rough context, never a precise "
    "benchmark.\n"
    "4. If the traveller's own currency is given AND it unambiguously "
    "implies one home country (the tool decides this, not you), use "
    "get_comparative_context for the CUSTOMS and PRICE SCALE comparison -- "
    "it's more useful to say 'tipping is expected here, unlike at home' "
    "than to state destination facts in isolation. If the tool's "
    "'assumption' field is non-null, state it plainly (e.g. 'Assumption: "
    "assuming home country is USA based on currency USD.'). If "
    "'home_country' comes back None (e.g. the currency was EUR, which "
    "matches multiple countries in this data), do NOT guess a home country "
    "-- just report the destination's customs and price scale on their "
    "own, with no comparison. IMPORTANT: get_comparative_context does NOT "
    "include the exchange rate. If the traveller asked for the exchange "
    "rate at all, you MUST ALSO call get_exchange_rate separately -- never "
    "skip it just because you already called get_comparative_context, and "
    "never say the rate is unavailable without having actually called "
    "get_exchange_rate yourself.\n"
    "5. Only report what the tools return. Never invent an exchange rate, "
    "custom, or income figure.\n"
    "6. NEVER ask a follow-up question and never request clarification. You "
    "get exactly one turn. If something is missing or ambiguous (e.g. no "
    "origin currency given), make one reasonable assumption, state it in a "
    "line beginning 'Assumption:', and answer anyway.\n"
    "7. If a tool returns found=False, say plainly that the information "
    "isn't available for that country/service rather than guessing.\n"
    "8. Reply with ONE self-contained message covering everything the task "
    "asked for. No follow-up questions, no filler.\n"
)

_AGENT = None


def build_agent():
    """Construct and return the Money & Customs deep agent, ready to invoke."""
    global _AGENT
    if _AGENT is None:
        llm = ChatCohere(model=MODEL)
        _AGENT = create_deep_agent(
            model=llm,
            tools=[get_exchange_rate, search_money_customs, get_income_context, get_comparative_context],
            system_prompt=SYSTEM_PROMPT,
        )
    return _AGENT


def _invoke(task: str):
    """Shared invocation path for answer() and answer_with_trace(). Returns
    the raw agent.invoke() result so callers can extract what they need
    without a second, duplicate call to the model."""
    agent = build_agent()
    return agent.invoke({"messages": [{"role": "user", "content": task.strip()}]})


def _final_text(result) -> str:
    message = result["messages"][-1]
    content = getattr(message, "content", message)
    return content if isinstance(content, str) else str(content)


def answer(task: str) -> str:
    """Answer one orchestrator task and return one self-contained message.

    Args:
        task: everything this agent needs, in one plain-language string --
            e.g. origin and destination, and what the traveller wants to
            know (exchange rate, customs, price scale, or all three).

    Returns:
        A single itinerary-ready message with no follow-up questions.
        UNCHANGED CONTRACT -- the Orchestrator depends on this being a
        plain string. Use answer_with_trace() below if you need visibility
        into which tools were called; do not modify this function's
        return type to add it.
    """
    if not task or not task.strip():
        return ("No task text was received, so no money/customs lookup "
                 "could be run. Send the request as one string including "
                 "the origin and destination, e.g. 'Traveling from the US "
                 "to Japan -- exchange rate, tipping customs, and price scale'.")

    result = _invoke(task)
    return _final_text(result)


# ---------------------------------------------------------------------------
# UI / OBSERVABILITY SUPPORT -- for the Chainlit app (chainlit_app.py), not
# the Orchestrator. Surfaces which tools were called and what they
# returned (crucially: match_score and adjusted, which the Orchestrator
# currently has no way to see at all -- see money_tools.py's confidence
# fields and tonight's write-up). LangSmith captures this same information
# server-side once tracing is configured above; this function additionally
# puts it directly in the chat UI, with no LangSmith account required.
# ---------------------------------------------------------------------------

def _extract_tool_steps(result) -> list:
    """Walk agent.invoke()'s message list and pull out each tool call's
    name, input, and returned dict, in call order.

    Best-effort: deepagents/langgraph message shapes can vary slightly by
    version, so this reads attributes defensively rather than assuming one
    exact structure. If your installed version's messages don't match,
    check what result["messages"] actually contains and adjust the
    attribute names below -- this couldn't be verified against a live
    deepagents install in the environment this was written in.
    """
    steps = []
    pending_calls = {}  # tool_call_id -> {"tool": name, "input": args}

    for msg in result.get("messages", []):
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for call in tool_calls:
                call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
                args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
                pending_calls[call_id] = {"tool": name, "input": args}
            continue

        # ToolMessage: has both a tool_call_id (linking back to the request
        # above) and a name; content is the tool's return value, usually
        # stringified by the framework.
        tool_call_id = getattr(msg, "tool_call_id", None)
        if tool_call_id is not None:
            call_info = pending_calls.get(tool_call_id, {})
            steps.append({
                "tool": call_info.get("tool") or getattr(msg, "name", "unknown_tool"),
                "input": call_info.get("input"),
                "output": getattr(msg, "content", msg),
            })

    return steps


def answer_with_trace(task: str) -> dict:
    """Same lookup as answer(), but also returns the tool-call trace for
    display in the Chainlit UI -- which country/service was actually
    queried, and each tool's match_score/adjusted/found fields.

    Returns:
        {"message": str, "steps": [{"tool", "input", "output"}, ...]}
    """
    if not task or not task.strip():
        return {"message": answer(task), "steps": []}

    result = _invoke(task)
    return {"message": _final_text(result), "steps": _extract_tool_steps(result)}


if __name__ == "__main__":
    print("--- Hello world ---")
    print(answer("Just say hello world so I know you're running."))

    print("\n--- Full scenario ---")
    print(answer(
        "I'm traveling from the USA to France. What's the current exchange "
        "rate, should I tip at restaurants and hotels, and what's the "
        "general price scale like there?"
    ))
