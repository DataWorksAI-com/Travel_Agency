"""
orchestrator_config.py -- wires each subagent's actual entry point behind
the SubagentClient interface, so orchestrator.py never needs to know how
a given subagent is reached.

Import paths below were verified against main as merged on 23 Aug 2026
(through PR #20). Four of the six slots now point at real, merged code;
the two that don't are called out individually. Remaining TODO markers
correspond to open decisions in ORCHESTRATOR_DESIGN.md -- resolve those,
then update this file, not orchestrator.py.
"""

import os
import sys
from pathlib import Path

from subagent_client import DEFAULT_MAX_TOKENS, LocalFunctionClient

REPO_ROOT = Path(__file__).resolve().parent


def _build_destination_client() -> LocalFunctionClient:
    # Real, merged. destination_agent/__init__.py:20 exports `answer` as an
    # alias of run_destination_agent specifically so the orchestrator can
    # import it under the team-standard name (PRs #15/#16). The
    # destination_recommender vs destination_recommender_alice split that
    # made this uncertain is resolved -- both are merged into main.
    from destination_agent import answer
    return LocalFunctionClient(answer)


def _build_flights_client() -> LocalFunctionClient:
    # STILL A STOPGAP -- the one slot whose contract has not changed.
    # Flights exports a plain dict spec, not a callable, so it goes through
    # LocalFunctionClient.from_dict_spec(). See ORCHESTRATOR_DESIGN.md #2:
    # if the group aligns Flights to expose answer() like every other
    # subagent, switch to the normal pattern below.
    # The model is set HERE, not in Flights' spec. llama-3.3-70b was
    # non-deterministic on this slot's short structured output; gpt-4o-mini is
    # not. But which model a slot runs on depends on this system's budget,
    # latency and determinism needs, not on the agent -- so it is the
    # orchestrator's decision to make and its file to hold it in. Likewise the
    # output ceiling, which from_dict_spec caps for every slot
    # (subagent_client.DEFAULT_MAX_TOKENS) rather than each agent capping
    # itself.
    from flights_agent import flights_subagent
    return LocalFunctionClient.from_dict_spec(
        flights_subagent, model="openrouter:openai/gpt-4o-mini"
    )

    # once aligned:
    # from flights_agent import answer
    # return LocalFunctionClient(answer)


def _build_restaurants_client() -> LocalFunctionClient:
    # Real, merged. restaurant_agent/__init__.py:23 defines answer(task).
    from restaurant_agent import answer
    return LocalFunctionClient(answer)


def _build_activities_client() -> LocalFunctionClient:
    # Real, merged -- and this slot changed the most. Three fixes over what
    # was here before:
    #
    # 1. The import was `from activities_agent import build_agent`, which
    #    could never resolve: the package directory is `activities-agent`
    #    with a HYPHEN, which is not a legal Python module name. Adding the
    #    directory itself to sys.path makes the inner activities_agent.py
    #    importable by its own (legal) name. Same approach used at
    #    sandbox/run_envelope_test.py:29 and app.py:35.
    # 2. PR #20 (merged Limeng + Jainam) exposes `answer(task)` directly, so
    #    the hand-rolled build_agent/ainvoke wrapper is now redundant --
    #    and it skipped the deterministic food-request guard that lives
    #    inside answer(), which was a real behaviour difference.
    # 3. `answer` is a NATIVE COROUTINE. The old wrapper called
    #    asyncio.run() on it, which raises RuntimeError when a loop is
    #    already running -- exactly the case here, since
    #    _run_parallel_subagents() calls this from inside asyncio.gather().
    #    LocalFunctionClient.call now awaits a coroutine function directly
    #    instead of pushing it to a worker thread.
    #
    # NOTE: `activities/` (no hyphen, also in main) is a different, older
    # copy of this agent. `activities-agent/` is the merged one -- do not
    # switch this to the shorter path just because it imports more cleanly.
    activities_dir = REPO_ROOT / "activities-agent"
    if str(activities_dir) not in sys.path:
        sys.path.insert(0, str(activities_dir))

    # Cap the output ceiling from out here rather than in the agent's own
    # default. glm-5.2's default is 65536, and on a free-tier OpenRouter key
    # the affordable max_tokens scales with remaining credit, so that default
    # eventually exceeds it and the slot dies with "requested up to 65536
    # tokens, but can only afford N" -- which looks like a broken agent and is
    # a config cliff. The agent reads DEEP_AGENT_MAX_TOKENS and leaves its
    # behaviour unchanged when it is unset, so running it standalone is
    # unaffected by this line. Set before the import, since MAX_TOKENS is read
    # at module scope.
    #
    # An explicit value already in the environment wins -- this is a default,
    # not an override.
    os.environ.setdefault("DEEP_AGENT_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))

    from activities_agent import answer
    return LocalFunctionClient(answer)


def _build_budget_client() -> LocalFunctionClient:
    # Real, merged (Shashank's, PRs #17/#18). The budget slot is the
    # repo-root RAG cost estimator: vector search over city cost docs ->
    # total estimate -> feasibility check. build_agent() is at
    # budget_agent/agent.py:86 and returns an .invoke()-able agent.
    #
    # This used to be ambiguous: budget_agent_rohan/ shipped a SECOND
    # package also named `budget_agent` (the per-diem envelope proposer),
    # so `import budget_agent` resolved to whichever landed in sys.modules
    # first -- import order, not intent, picked the agent. That package is
    # now `proposed_envelope_agent` and is NOT wired to any slot; it is
    # proposed future work. This name means one thing again.
    #
    # Going live needs three things, not just the import: `langchain` +
    # `deepagents` installed, ANTHROPIC_API_KEY or OPENROUTER_API_KEY set
    # (budget_agent/config.py:29-49 raises RuntimeError with neither), and
    # the Chroma vectorstore built via
    # budget_agent/scripts/build_vectorstore.py (enforced at
    # budget_agent/tools/rag_tools.py:33-37).
    from budget_agent.agent import build_agent

    def _answer(task: str) -> str:
        agent = build_agent()
        result = agent.invoke({"messages": [{"role": "user", "content": task}]})
        return result["messages"][-1].content

    return LocalFunctionClient(_answer)


def _build_money_customs_client() -> LocalFunctionClient:
    # Real on THIS BRANCH, not yet on main. money_customs_agent.py:111
    # defines answer(task) over money_tools.py (which IS on main).
    #
    # The note that used to sit here said exchange_rate_emily's HEAD was a
    # direct ancestor of this branch and that both money files were
    # byte-identical to hers. That was true when written and is no longer:
    # she has since added 93e6d52 ("Money tool fix -- returns the confidence
    # level to Orchestrator"), which puts match_score on every return path.
    #
    # Measured 26 Aug 2026, main is the stale one, not us:
    #
    #   money_tools.py, match_score occurrences
    #     origin/main                  11
    #     origin/exchange_rate_emily   25
    #     this branch                  26
    #
    # So this import points at a SUPERSET of her latest tool layer, and main
    # does not have money_customs_agent.py at all -- only money_tools.py.
    # Do not "resync from main" on the assumption that main is the reference
    # for this slot; that would drop both her match_score contract and the
    # agent itself.
    #
    # The single line where we differ from her is deliberate: found is
    # match_score >= CONFIDENCE_THRESHOLD here, where hers is hardcoded True
    # (see fd9f868).
    #
    # An earlier version of this comment said git would resolve that "in
    # whichever direction the last push runs". That overstated it. The merge
    # base already had True and she never modified that line, so a normal merge
    # keeps the side that DID change it -- ours -- whichever of PR #21 and
    # PR #22 lands first. It only reverts on a force-push, a hand-resolved
    # conflict, or a later deliberate change of hers.
    #
    # Still worth knowing, because there is no conflict marker either way: if
    # this slot ever starts reporting found for a country it holds no data for,
    # look at this line first.
    from money_customs_agent import answer
    return LocalFunctionClient(answer)


# ---------------------------------------------------------------------------
# Built lazily (not at import time) so a missing/unfinished subagent branch
# doesn't crash the whole orchestrator on startup -- only the first call to
# that specific subagent fails, and it fails as a plain-text problem
# description (per SubagentClient.call's contract), not an import error
# that takes down everything else.
# ---------------------------------------------------------------------------

_BUILDERS = {
    "destination": _build_destination_client,
    "flights": _build_flights_client,
    "restaurants": _build_restaurants_client,
    "activities": _build_activities_client,
    "budget": _build_budget_client,
    "money_customs": _build_money_customs_client,
}

_clients_cache = {}


def get_client(name: str) -> LocalFunctionClient:
    """Get (and lazily build) the client for one subagent by name."""
    if name not in _clients_cache:
        try:
            _clients_cache[name] = _BUILDERS[name]()
        except Exception as exc:
            # Wrap the *build* failure the same way SubagentClient.call
            # wraps a *call* failure, so a broken/missing subagent import
            # degrades to one clear error message instead of crashing
            # orchestrator startup.
            #
            # NOTE: `exc` itself can't be referenced inside the closure
            # below -- Python deletes an `except ... as exc:` binding as
            # soon as the except block ends, so capture the message into
            # a plain variable first, which the closure CAN still see.
            error_message = str(exc)

            class _BrokenClient:
                async def call(self, task: str) -> str:
                    return f"[{name} unavailable] {error_message}"

            _clients_cache[name] = _BrokenClient()
    return _clients_cache[name]
