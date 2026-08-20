"""
orchestrator_config.py -- wires each subagent's actual entry point behind
the SubagentClient interface, so orchestrator.py never needs to know how
a given subagent is reached.

TODO markers below correspond directly to ORCHESTRATOR_DESIGN.md's open
decisions -- resolve those, then update this file, not orchestrator.py.
"""

from subagent_client import LocalFunctionClient


def _build_destination_client() -> LocalFunctionClient:
    from destination_agent import answer  # placeholder import path
    return LocalFunctionClient(answer)


def _build_flights_client() -> LocalFunctionClient:
    from flights_agent import flights_subagent  # placeholder import path
    return LocalFunctionClient.from_dict_spec(flights_subagent)

    # once aligned:
    # from flights_agent import answer
    # return LocalFunctionClient(answer)


def _build_restaurants_client() -> LocalFunctionClient:
    from restaurant_agent import answer  # package layout after PR #6
    return LocalFunctionClient(answer)


def _build_activities_client() -> LocalFunctionClient:
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
    from budget_agent.agent import build_agent  # matches Shashank's flattened layout

    def _answer(task: str) -> str:
        agent = build_agent()
        result = agent.invoke({"messages": [{"role": "user", "content": task}]})
        return result["messages"][-1].content

    return LocalFunctionClient(_answer)


def _build_money_customs_client() -> LocalFunctionClient:
    from money_customs_agent import answer  # placeholder import path
    return LocalFunctionClient(answer)


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
            error_message = str(exc)

            class _BrokenClient:
                async def call(self, task: str) -> str:
                    return f"[{name} unavailable] {error_message}"

            _clients_cache[name] = _BrokenClient()
    return _clients_cache[name]
