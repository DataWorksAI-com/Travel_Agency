# Restaurant Finder — Domain-Expert Agent (Agentic RAG)

**ALY 6980 Capstone · DataWorksAI AI Travel Agency · Vrushti Shah**

## What this is
A restaurant-finder domain-expert agent for the travel bot. Built with Deep
Agents and running locally on Ollama (no API key, no cost). The agent's single
tool does real retrieval (RAG): restaurants live in a local Chroma vector
database and are matched by meaning (semantic search), then narrowed by hard
filters.

## How it works
1. Each restaurant becomes a short text description that is embedded and stored
   in a Chroma vector database.
2. A user question is matched by **meaning** against those embeddings (semantic
   search), not by exact keywords.
3. **Five hard filters** then enforce structured requirements: city, cuisine,
   max price, minimum rating, and dietary needs (vegetarian / vegan /
   gluten-free).

The data is mock (28 restaurants across 6 tropical cities) but shaped like a
real restaurant API (Google Places–style fields), so it can be swapped for a
live API later by replacing a single function body — no changes to the agent,
prompt, or callers.

## Files
- `restaurant_finder.py` — the RAG engine (vector DB build, semantic search, hard filters)
- `restaurants_data.py` — the mock restaurant dataset (28 records)
- `restaurant_agent_ollama.py` — the Deep Agent: its tool, system prompt, and interactive loop
- `test_jig.py` — automatic black-box checker (8 cases over retrieval + filter correctness)
- `.env.template` — environment variable template
- `.gitignore` — excludes secrets and generated files

## Requirements
- Python 3.11+
- Ollama installed and running, with the model: `ollama pull lfm2.5`
- `pip install deepagents langchain-ollama chromadb`

## Run
```
python restaurant_agent_ollama.py
```
The first run downloads a small embedding model (~80 MB) once, then loads the 28
restaurants into the vector database. Then ask, for example:
`vegan gluten-free dinner in Aruba under 30 dollars`.

## Tests
```
python test_jig.py
```
Runs 8 deterministic checks over the retrieval + filter core (no LLM needed).
Expected result: `SCORE: 8/8`.

## Switching the model / provider
The agent runs locally on Ollama by default (`MODEL = "ollama:lfm2.5"` in
`restaurant_agent_ollama.py`). To use OpenRouter instead, set an OpenRouter key
in your `.env` and change that one line to an OpenRouter model string. The RAG
engine, the filters, and the data are provider-independent.

## Design note — why this is agentic RAG
Restaurant knowledge is **retrieved** from a stored corpus (the vector DB)
rather than fetched live, and the agent decides when to call the retrieval tool.
The knowledge source is a Chroma vector database today, with a clear path to a
real restaurant REST API as the live-data source later.
