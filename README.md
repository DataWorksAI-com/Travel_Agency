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

## Orchestrator interface

This agent implements the team's sub-agent contract: **one task string in, one
self-contained itinerary-ready message out.** It never asks a follow-up
question, never talks to another agent, and assumes no shared context — the
destination city must be included in the task string.

```python
from restaurant_agent_ollama import answer

message = answer("Recommend a vegan dinner in Aruba under $30")
```

`answer(task: str) -> str` returns a single message shaped for direct insertion
into an itinerary: one committed top pick with a one-line reason, then at most
two alternatives, each carrying cuisine, city, price per person, rating and
dietary tags. Example:

```
Recommended restaurant: Sunset Vegan Kitchen - Vegan, Aruba. About $26 per person, rated 4.8/5. Dietary: vegetarian, vegan, gluten-free.
Why: Fully plant-based restaurant with vegan bowls, raw desserts, gluten-free options and sunset ocean views.

Alternatives:
- Palma Verde - Mediterranean, Aruba. About $28 per person, rated 4.6/5. Dietary: vegetarian, vegan, gluten-free.
```

Contract guarantees:
- **Never raises.** Any failure is returned as a plain message, so one broken
  sub-agent cannot break the itinerary.
- **Never asks a question back.** If something is missing it makes one
  reasonable assumption and states it on an `Assumption:` line.
- **Degrades instead of failing.** If the language model is unavailable, the
  retrieval half still runs and `answer()` returns a real recommendation drawn
  from the vector database, saying plainly that it ran without the model.
- **Invents nothing.** If no record matches, it says so and names the filter
  most likely responsible.

## Files
- `restaurant_finder.py` — the RAG engine (vector DB build, semantic search, hard filters) plus the contract helpers `parse_task` and `format_for_itinerary`
- `restaurants_data.py` — the mock restaurant dataset (28 records)
- `restaurant_agent_ollama.py` — the Deep Agent: its tool, system prompt, the `answer()` orchestrator entry point, and an interactive loop
- `test_jig.py` — automatic black-box checker (17 cases: 8 retrieval/filter, 9 contract)
- `requirements.txt` — dependencies
- `.env.template` — environment variable template
- `.gitignore` — excludes secrets and generated files

## Requirements
- Python 3.11+
- Ollama installed and running, with the model: `ollama pull lfm2.5`
- `pip install -r requirements.txt`

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
Runs 17 deterministic checks with no LLM needed: 8 over the retrieval and hard-filter
core, and 9 over the orchestrator contract (task-string parsing, itinerary-ready
formatting, no questions back, nothing invented). Expected result: `SCORE: 17/17`.

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
