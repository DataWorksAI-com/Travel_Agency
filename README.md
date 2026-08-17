# Money & Customs Agent

## What it does
Gives a traveller three things in one answer: the live exchange rate between
their home currency and the destination's, money-related customs for the
destination (tipping and haggling norms, broken down per service where
relevant), and a rough sense of local price scale via national income
context. Built to plug into the group's multi-agent travel-planning system
as a shared, cross-cutting knowledge source.

## Contract
- **Input:** one plain-language task string from the orchestrator (e.g.
  origin + destination + what the traveller wants to know).
- **Output:** one self-contained message, itinerary-ready.
- **Ask-vs-assume policy:** never asks a follow-up question. If something
  is missing or ambiguous, it states one reasonable assumption (prefixed
  `Assumption:`) and answers anyway -- same policy as the Budget and
  Restaurants agents.

## Knowledge sources
| Tool | Source | Type |
|---|---|---|
| `get_exchange_rate` | Frankfurter API (ECB-backed) | Live, free, no key |
| `get_money_customs` | Static, curated per-country/per-service data | Static |
| `get_income_context` | World Bank Open Data API (GNI per capita) | Live, free, no key |

**Country coverage today:** France, India, USA, Japan, Mexico, Morocco,
Germany. Add more by extending `MONEY_CUSTOMS_FACTS` and `COUNTRY_ISO3` in
`money_tools.py` (both use the same country-name keys, kept in sync
intentionally).

**Honesty note on `get_income_context`:** this reports GNI per capita, a
national *average*, not a city-level *median* -- true free, real-time median
income data isn't reliably available across countries. The tool's own
output says this explicitly so it's never presented as more precise than
it is.

## Setup
```
pip install -r requirements.txt
cp .env.example .env   # then fill in your real CEREBRAS_API_KEY
python agent.py
```

## Known limitations
- **Ambiguous requests with no country/city mentioned** (e.g. "Do I tip for
  room service?") may return an error rather than the agent stating an
  assumption and picking a reasonable default, even though the system
  prompt's rule 5 calls for the latter. Not yet fixed -- worth revisiting
  the prompt wording if this agent gets picked back up.
- **Exchange rate dates may lag a few days on weekends/holidays** -- this
  reflects the European Central Bank's actual publishing schedule via
  Frankfurter, not stale or broken data.
- **Untested:** malformed currency codes, live API failures (Frankfurter or
  World Bank being down/slow), and service names outside the four defined
  in `by_service` (restaurants, taxis, hotel_housekeeping, tour_guides).

## Example
```python
from agent import answer

answer(
    "I'm traveling from the USA to France. What's the current exchange "
    "rate, should I tip at restaurants and hotels, and what's the general "
    "price scale like there?"
)
```

Running `python agent.py` directly executes a hello-world check followed by
this exact scenario, so you can confirm the whole pipeline works end to end
without writing any extra code.

## Reusing just the tools (no agent needed)
`money_tools.py` has no dependency on deepagents, Cerebras, or any agent
framework -- it's three plain Python functions with type hints and
docstrings. Any teammate's agent, in any framework, can do:

```python
from money_tools import get_exchange_rate, get_money_customs, get_income_context
```

and register them as tools directly, without needing this repo's agent,
model choice, or system prompt at all.
