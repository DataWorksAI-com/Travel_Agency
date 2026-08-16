# =============================================================================
# ALY 6980 CAPSTONE - WEEK 2
# Restaurant Finder Deep Agent  --  FREE / LOCAL VERSION (Agentic RAG)
#
# Vrushti Shah, Northeastern University, August 2026
# Sponsor: DataWorksAI - Rapid Agentic RAG Development (AI Travel Agency)
#
# WHAT THIS IS
# ------------
# This is my Week 2 domain-expert agent: a restaurant finder for the travel
# bot. It is built the same way as my Hello World weather agent, with ONE big
# upgrade - the tool does real retrieval ("RAG"):
#
#   * every restaurant is stored in a local vector database (Chroma)
#   * a question is matched by MEANING (semantic search), not exact keywords
#   * hard filters then enforce city, price, and dietary needs
#
# It runs locally on Ollama - no API key, no cost - exactly the setup the
# mentors recommended for a narrow expert agent. The data is mock this week,
# but shaped like a real restaurant API so it can be swapped in later.
#
# ORCHESTRATOR CONTRACT
# ---------------------
# This agent implements the team's sub-agent contract: the orchestrator sends
# ONE task string and gets back ONE self-contained, itinerary-ready message.
# No follow-up questions, no agent-to-agent messaging, no shared context.
#
#     from restaurant_agent_ollama import answer
#     message = answer("Recommend a vegan dinner in Aruba under $30")
#
# See answer() in STEP 4b below.
#
# BEFORE YOU RUN THIS
# -------------------
#   1. The Ollama application must be installed and running.
#   2. You must have the model:  ollama pull lfm2.5
#   3. Install the libraries:  pip install langchain-ollama chromadb
# =============================================================================


# -----------------------------------------------------------------------------
# STEP 1 - BRING IN CODE
# -----------------------------------------------------------------------------
import logging
import os
from contextvars import ContextVar

# Every other agent in the team repo loads a .env file. This one did not, which
# meant an orchestrator that set RESTAURANT_AGENT_MODEL in .env - the normal
# place - would have been silently ignored and this agent would have dropped to
# the local model on its own.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # optional; the agent still runs on real environment vars
    pass

from deepagents import create_deep_agent
try:  # works when imported as part of the restaurant_agent package
    from .restaurant_finder import (
        search_with_reflection,
        warm_up,
        parse_task,
        format_for_itinerary,
    )
except ImportError:  # works when this file is run directly from its folder
    from restaurant_finder import (
        search_with_reflection,
        warm_up,
        parse_task,
        format_for_itinerary,
    )


# -----------------------------------------------------------------------------
# STEP 2 - CHOOSE WHICH MODEL THINKS
# -----------------------------------------------------------------------------
# Same as the weather agent. "provider:model-name". Must match your Ollama
# model name exactly. If the agent ignores the tool, swap to the fallback line.

# The default is the free local model. The orchestrator, or anyone running the
# whole travel-agency system, can override it WITHOUT editing this file:
#
#     export RESTAURANT_AGENT_MODEL="openrouter:anthropic/claude-sonnet-4.5"
#
# This matters for integration. Every other agent in the team repo runs a large
# hosted model (Claude Sonnet, Claude Haiku, GLM). If this file hard-coded a
# small local model, the orchestrator would silently run one agent on a weaker
# model than the rest of the system - and on any machine without Ollama
# installed, this agent would fall back to retrieval-only on every request.
# One environment variable removes that mismatch and still costs nothing by
# default.
MODEL = os.environ.get("RESTAURANT_AGENT_MODEL", "ollama:lfm2.5")

# Local alternatives, if the default is too heavy for the machine:
#   ollama:granite4.1:3b


# -----------------------------------------------------------------------------
# STEP 3 - WRITE THE TOOL
# -----------------------------------------------------------------------------
# This is the agent's one tool. It hands the request to the RAG engine in
# restaurant_finder.py and formats the answer as readable text.
#
# The type labels (str, int, bool) and the docstring are how Deep Agents tells
# the model what this tool does and how to call it. Keep them accurate.

# The orchestrator's original task string, remembered while a request is being
# answered. The tool needs it because the model paraphrases the request before
# passing it on, and a paraphrase can quietly lose a dietary word.
#
# This is a ContextVar and NOT a plain module variable, and the distinction is a
# safety one. A plain global is shared by every caller in the process. If the
# orchestrator ever answers two travellers at once - two threads, or two async
# tasks, which is the normal shape of a multi-agent system - one traveller's
# task string would overwrite the other's, and a vegan diner could be served the
# safety net built from somebody else's request. A ContextVar gives each thread
# and each async task its own value, so that cannot happen. This is the same bug
# class the dietary safety net exists to prevent, so it would have been a poor
# place to leave a shared global.
_CURRENT_TASK: ContextVar = ContextVar("restaurant_agent_current_task", default="")


def find_restaurants(
    query: str,
    city: str = "",
    cuisine: str = "",
    max_price: int = 0,
    min_rating: float = 0,
    vegetarian: bool = False,
    vegan: bool = False,
    gluten_free: bool = False,
) -> str:
    """Find restaurants that match a diner's request, using meaning-based
    search over a restaurant database plus hard filters.

    Args:
        query: what the person wants, in plain words, e.g.
               'romantic seafood dinner' or 'cheap casual tacos'.
        city: limit to one city such as 'Aruba', 'San Juan', 'Honolulu',
              'Cancun', 'Nassau', or 'Montego Bay'. Leave empty for any city.
        cuisine: limit to one cuisine such as 'Mexican', 'Seafood', 'Vegan',
                 'Italian', 'Thai', 'Steakhouse'. Leave empty for any cuisine.
        max_price: the most they want to spend per person, in US dollars.
                   Use 0 for no price limit.
        min_rating: only return places rated at least this (0 to 5). Use 0 for no limit.
        vegetarian: set True only if the diner needs vegetarian options.
        vegan: set True only if the diner needs vegan options.
        gluten_free: set True only if the diner needs gluten-free options.

    Returns:
        An itinerary-ready recommendation: one top pick with a reason, plus up
        to two alternatives, each with name, cuisine, city, price per person and
        rating. Or a plain statement that nothing matched.
    """
    # -------------------------------------------------------------------
    # HARD CONSTRAINTS ARE NOT LEFT TO THE LANGUAGE MODEL
    # -------------------------------------------------------------------
    # Measured on 15 Aug 2026: asked for "highly rated vegan dinner in
    # Nassau", the local model called this tool with cuisine='Vegan' and
    # left vegan=False. That turns a dietary REQUIREMENT into a cuisine
    # PREFERENCE - and preferences are exactly what the reflection step is
    # allowed to relax. The result offered a vegan diner two restaurants
    # that are not vegan.
    #
    # The lesson is not "use a bigger model". It is that a safety-relevant
    # constraint must not depend on a model choosing the right argument. So
    # the dietary needs are also read deterministically from the request
    # text, and the two sources are combined. The model can only ever ADD a
    # dietary requirement, never drop one.
    # -------------------------------------------------------------------
    # Refuse an uncovered destination before searching, whether it arrived in
    # the orchestrator's task string or in the model's city argument.
    uncovered = parse_task(_CURRENT_TASK.get() or "")["city_uncovered"]
    if uncovered:
        return format_for_itinerary([], city_uncovered=uncovered)

    cuisine_clean = (cuisine or "").strip().lower()
    if cuisine_clean == "vegan":
        vegan, cuisine = True, ""
    elif cuisine_clean == "vegetarian":
        vegetarian, cuisine = True, ""

    dietary = set()
    if vegetarian:
        dietary.add("vegetarian")
    if vegan:
        dietary.add("vegan")
    if gluten_free:
        dietary.add("gluten_free")

    # The safety net: re-read the diet from the words of the request itself.
    for source in (_CURRENT_TASK.get(), query):
        if source:
            dietary.update(parse_task(source)["dietary"])

    dietary = sorted(dietary)

    # search_with_reflection, not the plain search: if the literal request
    # returns nothing, it loosens ONE constraint at a time (rating, then
    # cuisine, then budget - never the dietary needs, never the city), looks
    # again, and reports exactly what it changed.
    results, relaxations = search_with_reflection(
        query,
        city=city or None,
        cuisine=cuisine or None,
        max_price=max_price or None,
        min_rating=min_rating or None,
        dietary=dietary or None,
        top_k=5,
    )

    # One shared formatter (in restaurant_finder.py) writes the itinerary-ready
    # block, so the tool output, the agent answer and the fallback path all look
    # identical to the orchestrator.
    return format_for_itinerary(results, relaxations=relaxations)


# -----------------------------------------------------------------------------
# STEP 4 - BUILD THE AGENT
# -----------------------------------------------------------------------------
# The system prompt encodes the team's orchestrator contract: one task string
# in, one self-contained itinerary-ready message out, no questions back.

SYSTEM_PROMPT = (
    "You are the restaurant sub-agent inside a travel-planning system. An "
    "orchestrator sends you one task in plain words and uses your reply "
    "directly in a customer itinerary.\n"
    "\n"
    "RULES YOU MUST FOLLOW:\n"
    "1. For ANY request about where to eat, food, dining, or restaurants, you "
    "MUST call the find_restaurants tool. Never invent restaurants.\n"
    "2. Read the request and pass the right arguments: put their wish into "
    "'query'; if a city is named, set 'city'; if a cuisine is named, set "
    "'cuisine'; if a budget is given, set 'max_price'; if they ask for highly "
    "rated, set 'min_rating' (e.g. 4.5); if they say vegetarian, vegan, or "
    "gluten-free, set that flag to True.\n"
    "3. Only recommend restaurants the tool returned. Do not add your own. If "
    "the tool returns none, say so plainly.\n"
    "4. NEVER ask a follow-up question and never request clarification. You get "
    "exactly one turn. If something is missing, make one reasonable assumption, "
    "state it in a line beginning 'Assumption:', and answer anyway. If you truly "
    "cannot proceed, state exactly what is missing in your final message.\n"
    "5. Reply with ONE self-contained message. Commit to a single top "
    "recommendation, give a one-line reason, then list at most two "
    "alternatives. Every restaurant you name must carry its cuisine, city, "
    "price per person and rating, so it can be dropped straight into an "
    "itinerary. Never write vague filler such as 'here are some options'.\n"
    "6. Give advice only. Never attempt to book anything, and never address "
    "another agent - only the orchestrator reads your reply.\n"
    "7. If the tool output contains any line beginning 'Adjusted:', the tool "
    "could not meet the request as written and loosened a requirement to find "
    "anything at all. You MUST carry that line through into your reply, in your "
    "own words if you prefer, so the traveller sees what changed. Never present "
    "an adjusted result as though it met the original request.\n"
)


_LOG = logging.getLogger(__name__)

_AGENT = None


def get_agent():
    """Build the deep agent once, on first use.

    Built lazily so that importing this module (which the orchestrator does to
    reach answer()) never requires a running model. The model is only contacted
    when an answer is actually requested.
    """
    global _AGENT
    if _AGENT is None:
        _AGENT = create_deep_agent(
            model=MODEL,
            tools=[find_restaurants],
            system_prompt=SYSTEM_PROMPT,
        )
    return _AGENT


# -----------------------------------------------------------------------------
# STEP 4b - THE ORCHESTRATOR ENTRY POINT
# -----------------------------------------------------------------------------
# This is the single function the orchestrator calls:
#
#     from restaurant_agent_ollama import answer
#     message = answer("Recommend a vegan dinner in Aruba under $30")
#
# One task string in, one itinerary-ready string out. It never asks a question
# back, never raises, and never returns an empty reply.

def _message_text(message):
    """Pull plain text out of a model message, whatever shape it arrives in."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some providers return a list of blocks
        parts = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ]
        return "".join(parts)
    return str(content)


def _retrieval_only_answer(task, reason=None):
    """Deterministic fallback used when the language model is unavailable.

    The retrieval half of this agent (vector search plus hard filters) needs no
    model at all. So if Ollama is not running, we still return a real, useful,
    itinerary-ready recommendation instead of failing the whole itinerary. The
    filters are read from the task string by parse_task.
    """
    try:
        parsed = parse_task(task)
        results, relaxations = search_with_reflection(
            parsed["query"],
            city=parsed["city"],
            cuisine=parsed["cuisine"],
            max_price=parsed["max_price"],
            min_rating=parsed["min_rating"],
            dietary=parsed["dietary"] or None,
            top_k=5,
        )
        notes = list(parsed["assumptions"])
        message = format_for_itinerary(results, assumptions=notes,
                                       relaxations=relaxations,
                                       city_uncovered=parsed["city_uncovered"])
        if reason:
            # The traveller must never be shown a stack trace or a pip command,
            # and a technical failure is not an "Assumption" about their trip.
            # The detail goes to the log; the itinerary gets one plain sentence.
            _LOG.warning("restaurant agent fell back to retrieval-only: %s", reason)
            message = ("Note: answered directly from the restaurant database "
                       "without the language model, which was unavailable. The "
                       "recommendation below is still drawn from real records.\n"
                       + message)
        return message
    except Exception as error:  # retrieval itself failed - stay inside the contract
        return ("The restaurant agent could not complete this task. Retrieval "
                "failed with: " + str(error) + ". No restaurant has been invented. "
                "Treat the restaurant section of the itinerary as unavailable.")


def answer(task: str) -> str:
    """Answer one orchestrator task and return one self-contained message.

    Args:
        task: everything this agent needs, in one plain-language string,
              including the destination city. Sub-agents share no context, so
              anything not in this string is unknown to the agent.

    Returns:
        A single itinerary-ready message. Contains no questions back to the
        orchestrator, and states any assumption it had to make.
    """
    # Coerce first, and inside the guard. The contract says this function never
    # raises; before this, a dict, a list or an int reached .strip() and threw
    # AttributeError before the try block was even entered.
    try:
        task = task if isinstance(task, str) else ("" if task is None else str(task))
    except Exception:
        task = ""

    if not task.strip():
        return ("No task text was received, so no restaurant search could be "
                "run. Send the request as one string including the destination "
                "city, for example: 'dinner in San Juan, seafood, under $40'.")

    token = _CURRENT_TASK.set(task.strip())
    try:
        result = get_agent().invoke(
            {"messages": [{"role": "user", "content": task.strip()}]}
        )
        text = _message_text(result["messages"][-1]).strip()
        if not text:
            raise ValueError("the model returned an empty message")
        return text
    except Exception as error:
        return _retrieval_only_answer(task, reason=str(error)[:160])
    finally:
        _CURRENT_TASK.reset(token)


# -----------------------------------------------------------------------------
# STEP 5 - RUN IT
# -----------------------------------------------------------------------------
if __name__ == "__main__":

    print("\n" + "=" * 62)
    print("  ALY 6980 - Week 2 - Restaurant Finder Deep Agent (RAG)")
    print("  Model: " + MODEL)
    print("=" * 62)
    print("\nLoading the restaurant database...")
    print("(The very first run downloads a small search model, about a minute.)")
    try:
        n = warm_up()
        print(f"Ready. {n} restaurants loaded into the vector database.\n")
    except Exception as error:
        print("\nCould not load the database yet:")
        print(error)
        print("Most likely: run  pip install chromadb  inside your .venv.\n")

    print("If Ollama is not running, the agent still answers from the vector")
    print("database directly (retrieval-only mode) and says so in its reply.\n")
    print("Ask for a restaurant. Examples you can try:")
    print("  - vegan gluten-free dinner in Aruba under 30 dollars")
    print("  - cheap casual tacos in Cancun")
    print("  - romantic seafood dinner in San Juan")
    print("Type  quit  and press Enter to stop.\n")

    while True:
        question = input("You: ").strip()

        if question.lower() in ("quit", "exit", "q"):
            print("\nStopped.\n")
            break
        if not question:
            continue

        # Uses the same answer() the orchestrator calls, so what you see here is
        # exactly what the orchestrator would receive.
        print("\nAgent:", answer(question), "\n")
