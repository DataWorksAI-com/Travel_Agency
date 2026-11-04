"""
fakes.py -- deterministic stand-ins for the agents that need an API key or a
live REST endpoint.

HONESTY NOTE. These are NOT the real agents. Each returns a fixed string
modelled on what that agent's own code/README says it returns (cited below).
They exist so the ORCHESTRATOR'S WIRING can be exercised end to end without
API keys. They validate plumbing, not model behaviour.

Because each reply is fixed, a fake CANNOT react to anything in its task
string.

Sources for each fake's shape:
  Destination  destination_agent/destination_agent.py:460 run_destination_agent
               -> result["messages"][-1].content, i.e. prose
  Flights      flights_agent.py:166 flights_subagent["system_prompt"] --
               "at most 3 options, one per line", "no headers", data-only
  Money/Cust.  money_customs_agent.py:111 answer() -> prose
"""

DESTINATION = (
    "Recommended destination: Bridgetown, Barbados. Best months to visit are "
    "December through April, when rainfall is lowest and the trade winds keep "
    "humidity down. No major public holidays fall in that window."
)

FLIGHTS = (
    "B6: $538, 5h10m, direct, arrives BGI\n"
    "AA: $602, 8h45m, 1 stop, arrives BGI\n"
    "DL: $671, 9h20m, 1 stop, arrives BGI\n"
    "Cheapest is B6 at $538. Prices are cached Travelpayouts data, not live."
)

MONEY_CUSTOMS = (
    "1 USD = 2.00 BBD (the Barbadian dollar is pegged to the US dollar). "
    "USD is widely accepted. Tipping: 10-15% is customary where service is "
    "not already included; many restaurants add a 10% service charge."
)

REPLIES = {
    "destination": DESTINATION,
    "flights": FLIGHTS,
    "money_customs": MONEY_CUSTOMS,
}
