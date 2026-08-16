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

4. If nothing comes back, the agent **looks again** — see below.

The data is mock (28 restaurants across 6 tropical cities) but shaped like a
real restaurant API (Google Places–style fields), so it can be swapped for a
live API later by replacing a single function body — no changes to the agent,
prompt, or callers.

## The reflection step — what makes this an agent, not a search pipeline

A search pipeline runs one query and returns whatever survives the filters. On a
genuinely tight request that means returning nothing, even when loosening a
single condition would have produced a good answer.

`search_with_reflection()` gives the agent a second look. When a search comes
back empty it **relaxes exactly one constraint, on its own, and searches again**:

```
Adjusted: Nothing matched under $15 per person, so the budget was widened to $22 for this search.
Recommended restaurant: Leilani Thai - Thai, Honolulu. About $22 per person, rated 4.4/5. Dietary: vegetarian, vegan, gluten-free.
```

Three rules keep it honest:

1. **One constraint at a time, in a published order** — `RELAXATION_ORDER = ("min_rating", "cuisine", "max_price")`. A rating floor is a preference, a cuisine is a preference, money is real, so price moves last.
2. **Never relaxed:** dietary needs (a medical or ethical requirement, not a preference) and the destination city (fixed upstream by the destination agent — a restaurant in the wrong country is a broken itinerary, not a weaker answer).
3. **A hard stop after two second looks,** and every adjustment is reported on its own `Adjusted:` line. Silently bending a requirement produces an answer that looks correct and is not.

## Hard constraints are not left to the language model

Measured on 15 Aug 2026: asked for *"highly rated vegan dinner in Nassau"*, the
local model called the tool with `cuisine='Vegan'` and `vegan=False`. That
demotes a dietary **requirement** into a cuisine **preference** — and preferences
are exactly what the reflection step may relax. The result offered a vegan diner
two restaurants that are not vegan.

The fix is not "use a bigger model", which would fail less often rather than
never. Dietary needs are now derived deterministically from the request text and
combined with whatever the model passes, so **the model can only ever add a
dietary requirement, never drop one.** Two tests cover it.

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

## Measured results

Run `python eval_retrieval.py`. Numbers below are from a real run on 15 Aug 2026
under the real embedding model.

**Experiment 1 — retrieval quality.** 20 hand-labelled questions, phrased the way
a traveller speaks, scored on recall@3 against a plain keyword baseline searching
the identical text.

| | recall@3 | top-1 hit rate |
|---|---|---|
| keyword baseline | 85% | 70% |
| vector search | 80% | 55% |

**Keyword search wins on this corpus, and that is reported rather than hidden.**
The pattern is what matters. Vector search won where the wording differed but the
concept was concrete — *"fresh fish right by the water"*, *"spicy asian curry"*.
It lost on abstract, social requests — *"somewhere romantic for an anniversary
dinner"*, *"a special occasion splurge"* — because the corpus describes food and
setting, not occasions. On a small corpus of rich descriptive text, keyword search
is a strong baseline; semantic search earns its place on vocabulary mismatch.

**Experiment 2 — the value of the second look.** Six deliberately tight requests,
measured with the reflection step off and on. This result does not depend on the
embedding model.

| | requests answered |
|---|---|
| without the second look | 0 / 6 |
| with the second look | 6 / 6 |

The agentic win comes from the second look, not from the retriever.

## Files
- `restaurant_finder.py` — the RAG engine (vector DB build, semantic search, hard filters), the reflection step `search_with_reflection`, plus the contract helpers `parse_task` and `format_for_itinerary`
- `restaurants_data.py` — the mock restaurant dataset (28 records)
- `restaurant_agent_ollama.py` — the Deep Agent: its tool, system prompt, the `answer()` orchestrator entry point, and an interactive loop
- `test_jig.py` — automatic black-box checker (30 cases: 8 retrieval/filter, 9 contract, 13 reflection and hard-constraint)
- `eval_retrieval.py` — the measured evaluation behind the numbers above
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
Runs 30 deterministic checks with no LLM needed: 8 over the retrieval and
hard-filter core, 9 over the orchestrator contract (task-string parsing,
itinerary-ready formatting, no questions back, nothing invented), and 13 over the
reflection step and the hard-constraint guarantees (relaxation order, the
two-attempt stop, dietary and city never relaxed, every adjustment reported).
Expected result: `SCORE: 30/30`.

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
