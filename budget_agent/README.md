# Budget Cost Aggregator Agent

A **Deep Agent** (built on LangGraph via `deepagents`) that sits
downstream of the Flights, Restaurants, and Activities sub-agents in
the DataWorksAI Travel Agency multi-agent system. It aggregates their
priced outputs, checks the total against the user's stated budget, and
suggests specific cuts/downgrades if the trip runs over.

## Why this agent is different

Unlike Destination, Flights, Activities, and Restaurants, this agent:
- **Does not run in parallel** off the orchestrator — it only runs
  once the other three have returned priced results.
- **Needs no external API, MCP server, or vector DB.** Its "knowledge"
  is just the line items it's given; its logic is pure computation
  (sum, compare, suggest).

This makes it a useful contrast case for the "classic vs agentic RAG"
comparison: not every agent in a multi-agent system needs a retrieval
or external-data layer to be useful.

## Folder structure

```
budget_agent/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── src/
│   └── budget_agent/
│       ├── __init__.py
│       ├── config.py       # loads ANTHROPIC_API_KEY / model from env
│       ├── agent.py        # builds the Deep Agent
│       └── tools/
│           ├── __init__.py
│           └── budget_tools.py   # aggregate_costs, check_budget, suggest_adjustment
├── scripts/
│   └── run_agent.py        # CLI entry point — hello-world + chat mode
└── tests/
    └── test_tools.py       # unit tests for the tools (no API key needed)
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your real key under **one** of the two options:
```
# Option A: direct Anthropic key
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6

# Option B: OpenRouter (only used if ANTHROPIC_API_KEY is not set)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=anthropic/claude-sonnet-4.5
```
If `ANTHROPIC_API_KEY` is set, it's used automatically — no other
changes needed.

## Run it

**Hello World check** (simulates a task string from the orchestrator):
```bash
python scripts/run_agent.py
```

**Interactive chat** (paste your own task string):
```bash
python scripts/run_agent.py --chat
```

## Run tests

Tool logic is tested independently of the LLM (no API key required):
```bash
pytest
```

## Contract compliance (per team's orchestrator/sub-agent contract)

- **Input:** one task string from the orchestrator containing priced
  line items (category, name, cost) and the user's budget.
- **Output:** one self-contained final message: total cost, budget
  status (within/over), and — if over — specific items to cut or
  downgrade. No follow-up questions back to the orchestrator.
- **Assumptions:** if a line item is missing a category or cost, the
  agent makes a reasonable assumption and states it in the final
  message rather than asking for clarification.

## Next steps

- Wire into the orchestrator's routing so it's called automatically
  after Flights/Restaurants/Activities return.
- Consider a currency conversion tool if trips go international.
- Decide whether "essential" vs "optional" line items should be
  tagged explicitly (e.g. by the Activities/Restaurants agents) rather
  than inferred by category alone.
