"""
Money & Customs Agent -- built with Deep Agents (LangChain) + OpenRouter
(free tier). The key and model come from the shared .env file:
OPENROUTER_API_KEY, and OPENROUTER_MODEL (or MONEY_AGENT_MODEL to override
just this agent).

Combines five tools (money_tools.py) into one agent that gives a traveller:
  - the live exchange rate between their currency and the destination's
  - money customs for the destination (tipping/haggling, per service)
  - rough income context, so they have a sense of local price scale
  - one retry via city/region-to-country resolution if a lookup fails
    because the traveller named a city rather than a country (see Rule 9)
  - an interpreted country, always disclosed, when the traveller describes
    a place instead of naming it (see Rule 10)

Follows the group's shared sub-agent contract: one task string in, one
self-contained message out. Never asks a follow-up question -- if
something is missing or ambiguous, it states an assumption and answers
anyway (same policy as Budget and Restaurants).
"""

import os
import re

from dotenv import load_dotenv

# OPENROUTER_API_KEY and OPENROUTER_MODEL come from the shared .env file.
# No key is ever written in this file.
load_dotenv()

from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent

from money_tools import get_exchange_rate, search_money_customs, get_income_context, get_comparative_context, resolve_location_country


# Full "provider:model" string. MONEY_AGENT_MODEL overrides this agent only;
# otherwise every agent shares OPENROUTER_MODEL from .env. Blank counts as unset.
MODEL = (
    os.environ.get("MONEY_AGENT_MODEL")
    or "openrouter:" + (os.environ.get("OPENROUTER_MODEL") or "nvidia/nemotron-3-ultra-550b-a55b:free")
)

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
    "own sense of the current date is not. If the task does not state the "
    "traveller's home currency, you must still choose one to convert from: "
    "use USD, and your reply MUST include the line 'Assumption: using USD "
    "as your home currency, since none was given.'\n"
    "2. For tipping/haggling norms, use search_money_customs. Pass a specific "
    "'service' (restaurants, taxis, hotel_housekeeping, tour_guides) if the "
    "traveller asked about one in particular; otherwise call it without a "
    "service for the full breakdown. This tool tries an exact match first, "
    "then a typo correction, then a semantic search over the same data if "
    "the country name is misspelled or phrased loosely. If nothing matches "
    "closely enough, it returns found=False (see Rules 7 and 9). CHECK THE "
    "'adjusted' FIELD "
    "ON EVERY CALL. If it is non-null, your reply MUST begin with a line "
    "stating the correction verbatim before anything else -- for example: "
    "'Note: I interpreted \"<input>\" as <country>.' -- copying the country "
    "name straight from the tool's 'country' field. Do not summarize, "
    "paraphrase away, or silently omit this line. Only after that line may "
    "you continue with the customs details. If 'adjusted' is null, skip "
    "this line entirely -- do not invent a correction that didn't happen. "
    "If the tool has no data for the requested service (by_service is "
    "empty), say there is no service-specific data, then give only the "
    "general note -- do not extend it to that service with your own "
    "reasoning (e.g. 'this likely applies to spas too').\n"
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
    "isn't available for that country/service rather than guessing -- "
    "UNLESS Rule 9 applies first (a city/region name may need one retry "
    "before you fall back to this rule).\n"
    "8. Reply with ONE self-contained message covering everything the task "
    "asked for. No follow-up questions, no filler.\n"
    "9. If search_money_customs (directly, or via get_comparative_context's "
    "destination side) returns found=False for a place NAME (a city, island "
    "or region, e.g. 'Marrakech'), call resolve_location_country "
    "with the same input before concluding the data is unavailable. Read "
    "its result: if 'ambiguous' is true, or 'resolved' is false, do NOT "
    "guess -- proceed to Rule 7 as normal. If 'resolved' is true, retry "
    "search_money_customs (or get_comparative_context) ONCE using the "
    "'country' field from resolve_location_country's result -- never with a "
    "country you inferred yourself, even when the tool's error names a "
    "'closest entry'; a closest entry below the threshold is not an answer. "
    "If that retry "
    "succeeds (search_money_customs actually returned found=True for that "
    "country), your reply MUST begin with a line stating this before "
    "anything else: 'Note: no data was found for \"<original input>\" "
    "directly; retried as <country>.' -- copying <original input> and "
    "<country> from the actual values involved. Do not omit this line, "
    "and do not treat the retried country as if it had been the original "
    "input. If the retry also returns found=False, proceed to Rule 7. "
    "This rule takes priority over Rule 7 only for this one retry "
    "attempt; Rule 7 governs once a retry has been tried, ruled out for "
    "ambiguity, or resolve_location_country itself found nothing.\n"
    "10. If the traveller DESCRIBES a place instead of naming one (e.g. "
    "'south of the US border', 'the land of the rising sun'), you may "
    "translate the description into a country yourself -- but only when it "
    "clearly points to exactly ONE country. Read it the way most people "
    "would in everyday speech: idioms and common nicknames count as clear "
    "(e.g. 'down under' = Australia, 'the land of the rising sun' = Japan), "
    "even if a strict literal reading could stretch further. Then call the "
    "tools with that "
    "country, and your reply MUST begin with this line before anything "
    "else: 'Note: I interpreted \"<description>\" as <country>.' -- copying "
    "the traveller's words and the country you used. If the description "
    "could mean several countries (e.g. 'the Caribbean', 'Southeast Asia'), "
    "do not pick one: say plainly that this data is held per country and "
    "name no country's customs -- and, per Rule 6, do not ask the traveller "
    "which country they mean. Never use this rule for a place name -- "
    "names go through Rule 9 -- and never pass a description to "
    "resolve_location_country.\n"
    "11. End every reply that reports any tool data with ONE final line "
    "naming where each kind of fact came from, starting with 'Sources:'. "
    "For customs, copy the tool's 'source' field as given -- it states how "
    "reliable that entry is (e.g. 'General knowledge, not independently "
    "verified'), and the traveller needs to see that. For an exchange "
    "rate, write 'Frankfurter (European Central Bank data)'; for price "
    "scale, write 'World Bank GNI per capita'. List only sources whose data "
    "actually appears in the reply. If the tools found no data at all, "
    "write no Sources line.\n"
)

_AGENT = None


_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def _local_base_url() -> str:
    """The local model server's address, checked to be on this computer.

    Same rule as the team's desktop/local_llm.py (PR #25): prompts in local
    mode must never leave the machine. Rejects remote hosts, look-alikes
    such as localhost.example.org, embedded passwords, query strings and
    paths other than /v1.
    """
    from urllib.parse import urlsplit

    url = os.environ.get("TRAVEL_LOCAL_BASE_URL") or "http://localhost:1234/v1"
    parts = urlsplit(url)
    if (parts.scheme not in ("http", "https")
            or parts.hostname not in _LOOPBACK_HOSTS
            or parts.username or parts.password
            or parts.query or parts.fragment
            or parts.path.rstrip("/") != "/v1"):
        raise ValueError(
            f"TRAVEL_LOCAL_BASE_URL must point to a model server on this "
            f"computer, e.g. http://localhost:1234/v1 -- got {url!r}."
        )
    return url


def _build_llm():
    """The chat model: OpenRouter by default, or a local model served by
    LM Studio when LLM_BACKEND=local is set in .env."""
    if (os.environ.get("LLM_BACKEND") or "").strip().lower() == "local":
        from langchain_openai import ChatOpenAI

        # LM Studio's server speaks the OpenAI API on localhost.
        # It ignores the API key, but the client requires one to be set.
        # Setting names match the team's desktop/local_llm.py (PR #25).
        return ChatOpenAI(
            model=os.environ.get("TRAVEL_LOCAL_MODEL") or "local-model",
            base_url=_local_base_url(),
            api_key="lm-studio",
            temperature=0,
        )
    return init_chat_model(MODEL)


def build_agent():
    """Construct and return the Money & Customs deep agent, ready to invoke."""
    global _AGENT
    if _AGENT is None:
        llm = _build_llm()
        _AGENT = create_deep_agent(
            model=llm,
            tools=[get_exchange_rate, search_money_customs, get_income_context, get_comparative_context, resolve_location_country],
            system_prompt=SYSTEM_PROMPT,
        )
    return _AGENT


# Waits (seconds) before retrying a transient model failure. Free models time
# out or get rate-limited per minute at busy times; one bad response should not
# fail the whole request. The free-model DAILY cap is not retried -- waiting
# seconds cannot fix it.
RETRY_WAITS = (5, 15)
_TRANSIENT = ("timeout", "timed out", "overloaded", "temporarily", "429",
              "too many requests", "per-min", "response validation failed")


def _is_transient(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return "per-day" not in text and any(t in text for t in _TRANSIENT)


def _invoke(task: str):
    """Shared invocation path for answer() and answer_with_trace(). Returns
    the raw agent.invoke() result so callers can extract what they need
    without a second, duplicate call to the model. Retries transient model
    failures (timeouts, per-minute limits) up to len(RETRY_WAITS) times."""
    import time

    agent = build_agent()
    payload = {"messages": [{"role": "user", "content": task.strip()}]}
    for attempt, wait in enumerate((*RETRY_WAITS, None)):
        try:
            result = agent.invoke(payload)
            # Free models occasionally return an empty final message with no
            # tool calls. That is a failed response, not an answer.
            if wait is not None and not str(getattr(result["messages"][-1], "content", "")).strip():
                print(f"[money_customs_agent] empty model reply, retry {attempt + 1} in {wait}s")
                time.sleep(wait)
                continue
            return result
        except Exception as exc:
            if wait is None or not _is_transient(exc):
                raise
            print(f"[money_customs_agent] transient model error, retry "
                  f"{attempt + 1} in {wait}s: {type(exc).__name__}")
            time.sleep(wait)


_EMPTY_SOURCES_LINE = re.compile(r"\n*\s*sources?:\s*$", re.IGNORECASE)
_TRAILING_SOURCES_LINE = re.compile(r"\n*[ \t*_]*sources?:[^\n]*\s*$", re.IGNORECASE)
_FOUND_TRUE = re.compile(r"[\"']found[\"']\s*:\s*true", re.IGNORECASE)
_CLAIMS_A_LOOKUP = re.compile(r"retried as|interpreted\s+\S.*\s+as\s", re.IGNORECASE)


def _any_data_found(result) -> bool:
    """True if at least one tool call returned found=True (customs, rate,
    income, or either side of a comparison)."""
    return any(_FOUND_TRUE.search(str(step.get("output", "")))
               for step in _extract_tool_steps(result))


_ASSUMPTION_WORD = re.compile(r"\bassum", re.IGNORECASE)


def _exchange_from_currencies(result) -> list[str]:
    """Currencies get_exchange_rate converted FROM, in call order."""
    out = []
    for step in _extract_tool_steps(result):
        if step.get("tool") == "get_exchange_rate" and isinstance(step.get("input"), dict):
            code = str(step["input"].get("from_currency", "")).upper()
            if code and code not in out:
                out.append(code)
    return out


def _ensure_currency_assumption(text: str, task: str, result) -> str:
    """Rule 6 safety net. If an exchange rate was converted from a currency
    the traveller never named, and the reply states no assumption, add one.
    Observed: 'What's the exchange rate in Japan?' came back as USD -> JPY
    with no Assumption line, which a non-US traveller could easily misread."""
    if _ASSUMPTION_WORD.search(text):
        return text
    unstated = [c for c in _exchange_from_currencies(result)
                if not re.search(rf"\b{c}\b", task, re.IGNORECASE)]
    if not unstated:
        return text
    return (f"Assumption: exchange rate shown from {', '.join(unstated)}, "
            f"taken as your home currency.\n\n{text}")


def _as_dict(output) -> dict:
    """A tool's output as a dict (tools return JSON text through the agent)."""
    if isinstance(output, dict):
        return output
    try:
        import json

        value = json.loads(str(output))
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def _ensure_retry_note(text: str, result) -> str:
    """Rule 9 safety net. If a city lookup resolved to a country, and a
    later customs lookup for that country found data, the reply must say
    so. Observed on a small local model: the Marrakech -> Morocco retry
    worked, but the reply left out the 'retried as' line."""
    if re.search(r"retried as", text, re.IGNORECASE):
        return text
    steps = _extract_tool_steps(result)
    for i, step in enumerate(steps):
        if step.get("tool") != "resolve_location_country":
            continue
        resolved = _as_dict(step.get("output"))
        country = resolved.get("country")
        if not resolved.get("resolved") or not country:
            continue
        for later in steps[i + 1:]:
            if later.get("tool") not in ("search_money_customs", "get_comparative_context"):
                continue
            asked = later.get("input") or {}
            asked_place = asked.get("country") or asked.get("destination_country") or ""
            found = _FOUND_TRUE.search(str(later.get("output", "")))
            if found and asked_place.strip().lower() == country.strip().lower():
                original = resolved.get("input") or (step.get("input") or {}).get("name", "")
                return (f'Note: no data was found for "{original}" directly; '
                        f"retried as {country}.\n\n{text}")
    return text


def _final_text(result) -> str:
    message = result["messages"][-1]
    content = getattr(message, "content", message)
    text = content if isinstance(content, str) else str(content)
    # Rule 11: no Sources line when nothing was found. The model keeps
    # writing one anyway ("Sources:", "Sources: (no data found for Kenya)"),
    # so this is decided from the tool results, not left to the model.
    if not _any_data_found(result):
        # No tool returned data, so any "retried as" / "interpreted as"
        # disclosure is describing a lookup that did not succeed, and any
        # figures came from the model itself. Observed: after both lookups
        # for "Marrakech" failed, the reply claimed "retried as Morocco" and
        # listed tipping amounts. Replace the whole reply with the truth.
        if _CLAIMS_A_LOOKUP.search(text):
            return ("Money-customs data isn't available for that destination: "
                    "it isn't in the data, and it could not be matched to a "
                    "country that is.")
        text = _TRAILING_SOURCES_LINE.sub("", text)
    return _EMPTY_SOURCES_LINE.sub("", text).rstrip()


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
    text = _ensure_currency_assumption(_final_text(result), task, result)
    # The retry note is added last, so it ends up as the first line.
    return _ensure_retry_note(text, result)


# ---------------------------------------------------------------------------
# TOOL-CALL VISIBILITY -- not used by the Orchestrator (which only consumes
# answer()'s plain string). Surfaces which tools were called and what they
# returned -- crucially: match_score and adjusted. Useful for testing and
# debugging directly (see test_suite.py's Section B) -- no UI or tracing
# setup required to use it.
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
    """Same lookup as answer(), but also returns the tool-call trace --
    which country/service was actually queried, and each tool's
    match_score/adjusted/found fields.

    Returns:
        {"message": str, "steps": [{"tool", "input", "output"}, ...]}
    """
    if not task or not task.strip():
        return {"message": answer(task), "steps": []}

    result = _invoke(task)
    message = _ensure_currency_assumption(_final_text(result), task, result)
    message = _ensure_retry_note(message, result)
    return {"message": message, "steps": _extract_tool_steps(result)}


if __name__ == "__main__":
    print("--- Hello world ---")
    print(answer("Just say hello world so I know you're running."))

    print("\n--- Full scenario ---")
    print(answer(
        "I'm traveling from the USA to France. What's the current exchange "
        "rate, should I tip at restaurants and hotels, and what's the "
        "general price scale like there?"
    ))
