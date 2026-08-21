# Flights Sub-Agent

Handles flight search, routes, and budget comparisons. Designed to be
called by an orchestrator as a sub-agent, not used standalone in production.

## Scope

**In scope:** flight search, route options, budget/date filtering.
**Out of scope:** booking, hotels, activities, destination recommendations.

## Requirements

Install dependencies:
```
pip install -r requirements.txt
```

## Setup

1. Get a free API token:
   - Sign up at [travelpayouts.com](https://www.travelpayouts.com)
   - Go to Profile → API token
2. Create a `.env` file in this folder (never commit this file):
   ```
   TRAVELPAYOUTS_TOKEN=your_token_here
   OPENROUTER_API_KEY=your_openrouter_key_here
   ```

## Tools

| Tool | What it does |
|---|---|
| `get_airport_code(city)` | Resolves a city name to an IATA airport/city code. |
| `search_flights(origin_code, destination_code, date_str=None, max_price=None)` | Searches flight prices between two codes. Falls back to a full-month search if the exact date returns no results. |

## Data notes

Prices are real but cached (not live/real-time availability). Coverage
varies by route — less common routes may return no results even after
widening the date range.

## How to test

Run the file directly:
```
python flights_agent.py
```
This runs one built-in test query and prints the full message trace
(tool calls, intermediate steps, final answer).

To test with your own query, edit the `content` field in the
`if __name__ == "__main__":` block at the bottom of the file:
```python
result = agent.invoke({
    "messages": [
        {"role": "user", "content": "Find me a flight from Boston to Paris under $700."}
    ]
})
```

## Using it in an orchestrator

```python
from flights_agent import flights_subagent

orchestrator = create_deep_agent(
    model="openrouter:anthropic/claude-sonnet-4.5",
    subagents=[flights_subagent, ...],
    system_prompt="...",
)
```

Pass city names, not airport codes, in the task description — this agent
resolves codes internally.
