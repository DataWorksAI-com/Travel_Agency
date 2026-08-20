"""
orchestrator_config.py -- wires each subagent's actual entry point behind
the SubagentClient interface, so orchestrator.py never needs to know how
a given subagent is reached.

TODO markers below correspond directly to ORCHESTRATOR_DESIGN.md's open
decisions -- resolve those, then update this file, not orchestrator.py.
"""

from subagent_client import LocalFunctionClient

# ---------------------------------------------------------------------------
# Each entry: import the subagent's real callable and wrap it.
#
# TODO: these import paths are PLACEHOLDERS. Fill in the real module path
# once each subagent's branch is merged and its actual package layout is
# known (e.g. `from budget_agent.agent import answer` once that branch
# is merged into main, matching the "src/budget_agent" layout seen when
# reviewing Shashank's branch).
# ---------------------------------------------------------------------------

def _build_destination_client() -> LocalFunctionClient:
    # TODO: confirm this once destination_recommender vs
    # destination_recommender_alice is resolved to a single branch, and
    # once Destination's agent-assembly file (not yet reviewed) is found.
    from destination_agent import answer  # placeholder import path
    return LocalFunctionClient(answer)


def _build_flights_client() -> LocalFunctionClient:
    # TODO: Flights currently exports a plain dict spec, not a callable --
    # see subagent_client.LocalFunctionClient.from_dict_spec(). This is a
    # stopgap. If the group aligns Flights to expose build_agent()/answer()
    # like every other subagent, switch this to the normal pattern below
    # (commented out) instead.
    from flights_agent import flights_subagent  # placeholder import path
    return LocalFunctionClient.from_dict_spec(flights_subagent)

    # once aligned:
    # from flights_agent import answer
    # return LocalFunctionClient(answer)


def _build_restaurants_client() -> LocalFunctionClient:
    from restaurant_agent import answer  # package layout after PR #6
    return LocalFunctionClient(answer)


def _build_activities_client() -> LocalFunctionClient:
    # TODO: Activities' build_agent() is async and still an explicit stub
    # per its own docstring -- confirm it's feature-complete before relying
    # on this in integration testing.
    from activities_agent import build_agent
    import asyncio

    async def _answer(task: str) -> str:
        agent = await build_agent()
        result = await agent.ainvoke({"messages": [{"role": "user", "content": task}]})
        return result["messages"][-1].content

    def _sync_answer(task: str) -> str:
        return asyncio.run(_answer(task))

    return LocalFunctionClient(_sync_answer)


def _build_budget_client() -> LocalFunctionClient:
    from budget_agent.agent import build_agent  # placeholder import path

    def _answer(task: str) -> str:
        agent = build_agent()
        result = agent.invoke({"messages": [{"role": "user", "content": task}]})
        return result["messages"][-1].content

    return LocalFunctionClient(_answer)


def _build_money_customs_client() -> LocalFunctionClient:
    from money_customs_agent import answer  # placeholder import path
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
