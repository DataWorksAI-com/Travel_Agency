"""
budget_agent
============
Budget Cost Aggregator Agent for the DataWorksAI Travel Agency
multi-agent RAG project.

Unlike the Destination, Flights, Activities, and Restaurants agents,
this agent does NOT run in parallel off the orchestrator. It runs
downstream, after Flights/Restaurants/Activities have each returned
their priced results. Its job is to:
  1. Aggregate the individual costs into a total trip cost.
  2. Compare that total against the user's stated budget.
  3. If over budget, suggest which item(s) could be swapped/dropped
     to bring the trip back within range.

Per the orchestrator/sub-agent contract: this agent takes ONE
self-contained task string (which includes the itemized costs and the
budget), and returns ONE self-contained final message -- no follow-up
questions back to the orchestrator.
"""

__version__ = "0.1.0"
