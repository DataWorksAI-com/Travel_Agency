"""
Builds the Budget Agent.

This agent runs standalone -- same pattern as Destination, Flights,
Activities, and Restaurants -- and does NOT depend on any other
sub-agent's output. Given a destination + the user's stated budget
(+ optional trip length), it:

  1. Retrieves relevant cost information via semantic (vector) search
     over a knowledge base of city cost documents (retrieve_cost_info)
     -- this is the actual RAG step: it doesn't do an exact dict
     lookup, it embeds the query and finds the most relevant chunks.
  2. Retrieves a SECOND time with a rephrased/narrower query as a
     verification pass, to cross-check the numbers before finalizing
     (per mentor feedback: confirm prices with a second call rather
     than trusting a single retrieval).
  3. Reasons over the retrieved text to estimate a total trip cost,
     reconciling the two retrieval passes if they disagree.
  4. Checks that estimate against the stated budget (check_feasibility).

Supports two usage modes:
  - Single-shot: one self-contained task string from the orchestrator,
    one self-contained final message back (per the sub-agent contract).
  - Conversational: run via `scripts/run_agent.py --chat`, where the
    user can ask a follow-up question (e.g. change the destination or
    days) and the agent reuses budget/context established earlier in
    the same conversation rather than requiring it to be repeated.
"""

from langchain.chat_models import init_chat_model

from deepagents import create_deep_agent

from .config import load_settings
from .tools import ALL_TOOLS

SYSTEM_PROMPT = """You are the Budget Agent in a multi-agent travel \
planning system.

You can be used in two ways:
1. As a sub-agent: you receive a single task string from the \
orchestrator containing a destination, the user's stated budget, and \
optionally a trip length in days. You do NOT wait on or depend on any \
other sub-agent's output -- reason entirely from your own tools.
2. As a conversational agent: the user may ask a follow-up question \
after their first message (e.g. "what about Bali instead?" or "what \
if my budget is $900?"). When that happens, reuse any budget, trip \
length, or other details already established earlier in the \
conversation instead of asking the user to repeat them. Only ask a \
clarifying question if something essential (like the destination) has \
never been stated at all.

Your job, each time you're asked about a destination/budget:
1. Use retrieve_cost_info to pull relevant cost information for the \
destination from the knowledge base (semantic search, not an exact \
lookup -- pass a natural-language query describing what you need).
2. VERIFICATION PASS (do this before finalizing any number): call \
retrieve_cost_info a second time with a rephrased or narrower query \
(e.g. focus specifically on flight cost, or lodging cost, or query \
the destination name plus "cost" a different way) to confirm the \
figures from step 1. If the two retrievals agree, proceed with \
confidence. If they disagree or the second pass surfaces a different \
number, reconcile the difference and note in your final message which \
figure you used and why.
3. Reason over the retrieved (and verified) text to estimate a total \
trip cost for the given (or assumed) trip length -- scale per-day \
costs (lodging, food, activities) by the number of days, and add the \
round-trip flight cost once.
4. Use check_feasibility with your estimated total and the stated \
budget to confirm whether it's feasible.

Always finish with ONE clear, self-contained message stating:
- The estimated total cost and a rough breakdown (flight, lodging, \
food, activities)
- Whether the budget is feasible for this trip, and by how much it's \
over or under

If trip length isn't given, assume a reasonable default (e.g. 3 days) \
and state that assumption clearly in your final message. If the \
destination isn't in the knowledge base, say so clearly rather than \
guessing costs. In sub-agent mode, do not ask the orchestrator any \
follow-up questions.
"""


def build_agent(max_tokens: int = 3000):
    """Construct and return the Budget Deep Agent, ready to `.invoke(...)`.

    Args:
        max_tokens: Caps the response length per model call. Raised
            from 2000 to 3000 to comfortably fit the extra
            verification retrieval pass plus reasoning.
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
