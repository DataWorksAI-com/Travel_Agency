"""Money & Customs agent package.

`answer` is the team-standard entry point the orchestrator imports
(travel_orchestrator/subagents.py, SLOT 3).

money_customs_agent.py imports `money_tools` by its plain name, so this
folder is added to the import path first. Appended, not inserted: Chainlit
removes sys.path[0] after loading app.py.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)

from .money_customs_agent import answer, answer_with_trace  # noqa: E402

__all__ = ["answer", "answer_with_trace"]
