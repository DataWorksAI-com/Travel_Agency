"""Restaurant finder domain-expert agent.

ALY 6980 Capstone / DataWorksAI AI Travel Agency / Vrushti Shah

This file makes the folder a proper Python package, so the orchestrator can do:

    from restaurant_agent import answer
    message = answer("vegan gluten-free dinner in Aruba under $30")

without needing to know which module inside the folder holds the entry point,
and without having to change its working directory first.

`answer` is imported lazily below rather than at module load, because importing
the agent pulls in chromadb and deepagents. An orchestrator that merely imports
this package - to inspect it, or because it imports every agent up front -
should not crash if one optional dependency is missing on that machine. The
cost is only paid on the first real call.
"""

__all__ = ["answer"]


def answer(task: str) -> str:
    """The orchestrator entry point. One task string in, one message out.

    See restaurant_agent_ollama.answer for the full contract.
    """
    from .restaurant_agent_ollama import answer as _answer
    return _answer(task)
