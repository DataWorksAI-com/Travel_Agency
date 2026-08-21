"""Budget & Cost domain-expert agent.

Orchestrator entry point:

    from budget_agent import answer
    reply = answer("4 nights in Barbados for 2 people, budget 2000")

One task string in, one self-contained message out. Matches the entry point
every other subagent exposes.

The tools underneath have no model dependency and can be imported directly
if the orchestrator would rather skip the LLM layer:

    from budget_agent.tools import allocate_budget, verify_plan
"""


def answer(task: str) -> str:
    """One task string in, one self-contained message out.

    Imported lazily so that `import budget_agent` does not pull in
    deepagents or a model client — the tools alone stay importable with no
    API key and no LLM installed.
    """
    from .agent import answer as _answer
    return _answer(task)
