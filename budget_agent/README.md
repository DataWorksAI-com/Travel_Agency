# Budget Agent (RAG-based)

A standalone **Deep Agent** (built on LangGraph via `deepagents`) that
estimates trip costs and checks budget feasibility using **real RAG**
(Retrieval-Augmented Generation) — semantic search over a vector store
of city cost documents, not a dict lookup.

Runs independently, same pattern as Destination, Flights, Activities,
and Restaurants — does not depend on any other sub-agent's output.

## How the RAG pipeline works

1. **Source of truth:** `src/budget_agent/data/city_cost_docs.py` —
   15 short unstructured write-ups (one per city) covering flights,
   lodging, food, and activity costs.
2. **Embedding + indexing:** `scripts/build_vectorstore.py` chunks
   these documents, embeds them with a local `sentence-transformers`
   model, and persists them to a Chroma vector store (`./chroma_db`).
3. **Retrieval:** `retrieve_cost_info` (in `tools/rag_tools.py`) embeds
   the agent's query and does a similarity search over that vector
   store — so it retrieves relevant info even for fuzzy queries (e.g.
   "cheap tropical beach trip"), not just exact city-name matches.
4. **Reasoning + math:** the agent reasons over the retrieved text to
   estimate a total cost, then calls `check_feasibility` to compare
   against the user's budget.

## Cities currently in the knowledge base

Cancun, Maui, Phuket, Bali, Punta Cana, Costa Rica (San Jose), Fiji,
Seychelles, Maldives, Barbados, Montego Bay, Phu Quoc, Krabi, Tulum,
Oahu.

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
│       ├── config.py
│       ├── agent.py
│       ├── data/
│       │   ├── __init__.py
│       │   └── city_cost_docs.py     # source-of-truth documents
│       └── tools/
│           ├── __init__.py
│           ├── rag_tools.py           # retrieve_cost_info (real RAG)
│           └── budget_tools.py        # check_feasibility (math only)
├── scripts/
│   ├── build_vectorstore.py           # run once to embed + index docs
│   └── run_agent.py                   # CLI entry point
├── chroma_db/                          # persisted vector store (gitignored)
└── tests/
    └── test_tools.py
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your key (Anthropic preferred, OpenRouter as fallback):
```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
```

## Build the vector store (do this first, before running the agent)

```bash
python scripts/build_vectorstore.py
```

This downloads a small embedding model (~80MB) on first run, so it
needs internet access once. After that, `chroma_db/` is persisted
locally and queries don't need internet for retrieval (only the LLM
call itself does).

## Run it

```bash
python scripts/run_agent.py
```

Or interactively:
```bash
python scripts/run_agent.py --chat
```

Try queries like:
- "Is $700 enough for a 4-day trip to Cancun?"
- "What's a cheap tropical beach destination under $1,500?"
- "How much would a 5-day trip to Fiji cost?"

## Run tests

```bash
pytest
```
(RAG-specific tests are skipped automatically if `chroma_db/` hasn't
been built yet.)

## Adding more cities

Just add another entry to `CITY_COST_DOCS` in
`src/budget_agent/data/city_cost_docs.py`, then rerun
`python scripts/build_vectorstore.py` to re-embed and re-index.

## Why this is genuinely RAG (and not just a lookup)

The earlier version of this agent used a hardcoded Python dict keyed
by exact city name — that's a lookup, not retrieval. This version
embeds the query and does similarity search, so it can surface
relevant cost info even when the query doesn't name a city exactly,
and it demonstrates the actual retrieve → augment → generate pattern
the rest of the team's agents (Destination, Restaurants) are also
moving toward with their own vector DBs.
