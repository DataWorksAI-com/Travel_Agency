"""Destination Agent package.

Re-exports the agent entry point under both names:

  run_destination_agent  - the real name, used by app.py and the local tests
  answer                 - the alias the orchestrator imports
                           (orchestrator_config._build_destination_client does
                           `from destination_agent import answer`, matching the
                           convention the other subagents follow)

Both are the same function object: answer(user_query: str) -> str.

Note: importing this package imports destination_agent.destination_agent, which
constructs ChatAnthropic and the deep agent at module level. That needs
ANTHROPIC_API_KEY in destination_agent/.env, but makes no network call on its
own - the first request happens only when the function is actually called.
"""

from destination_agent.destination_agent import run_destination_agent
from destination_agent.destination_agent import run_destination_agent as answer

__all__ = ["answer", "run_destination_agent"]
