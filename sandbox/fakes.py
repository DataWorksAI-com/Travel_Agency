"""
fakes.py -- deterministic stand-ins for the agents that need an API key or a
live REST endpoint.

HONESTY NOTE. These are NOT the real agents. Each returns a fixed string
modelled on what that agent's own code/README says it returns (cited below).
They exist so the ORCHESTRATOR'S WIRING can be exercised end to end without
six API keys. They validate plumbing, not model behaviour.

Because each reply is fixed, a fake CANNOT react to anything in its task
string. That is the structural reason the envelope A/B cannot run here --
see run_envelope_test.py.

Sources for each fake's shape:
  Destination  destination_agent/destination_agent.py:460 run_destination_agent
               -> result["messages"][-1].content, i.e. prose
  Flights      flights_agent.py:166 flights_subagent["system_prompt"] --
               "at most 3 options, one per line", "no headers", data-only
  Restaurants  restaurant_agent/__init__.py answer() -> prose, itinerary-ready
  Activities   activities-agent-limeng/activities_agent.py:249 answer()
               -- may report price tier "unknown"
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

RESTAURANTS = (
    "Champers -- seafood, waterfront, around $95 for two. "
    "Cuz's Fish Shack -- casual fish cutters, around $20 for two. "
    "Oistins Fish Fry -- Friday night, around $30 for two."
)

ACTIVITIES = (
    "Catamaran snorkel cruise -- outdoor, around $110 per person. "
    "Harrison's Cave tram tour -- cultural, around $60 per person. "
    "Carlisle Bay shipwreck snorkel -- outdoor, price tier unknown."
)

MONEY_CUSTOMS = (
    "1 USD = 2.00 BBD (the Barbadian dollar is pegged to the US dollar). "
    "USD is widely accepted. Tipping: 10-15% is customary where service is "
    "not already included; many restaurants add a 10% service charge."
)

REPLIES = {
    "destination": DESTINATION,
    "flights": FLIGHTS,
    "restaurants": RESTAURANTS,
    "activities": ACTIVITIES,
    "money_customs": MONEY_CUSTOMS,
}
