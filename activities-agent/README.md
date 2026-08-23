# Activities Agent — Merged (Limeng Zhang + Jainam Jayeshkumar Patel)

A single unified Activities Agent, combining two independently-built
implementations after comparing them and finding the same overall
design with different specific choices. Where the two disagreed, one
choice was made for this merged version — every decision is explained
in the docstring at the top of `activities_agent.py`, not left
implicit.

## Covered cities (combined from both original versions)

New York, Paris, Rome, Kyoto (originally Limeng's) plus Boston and
Chicago (originally Jainam's) — six cities total. Any additional city
looked up via `expand_activities_corpus()` is added automatically.

## Architecture

```
                    ┌─────────────────────────┐
   task string  →   │   Activities Agent       │  →  answer(task)
  (from orchestrator)│  (Deep Agents + LLM)     │     one message out
                    └───────────┬─────────────┘
                                │ picks a tool based on the request
       ┌──────────┬─────────────┼──────────────┬──────────────────┐
       ▼          ▼             ▼              ▼                  ▼
  Tier 1: exact  Tier 2:    hard_filter /  Tier 3: self-      Tier 3b: plain
  local filter   semantic   list_curated   expanding live     MCP fallback
  (6 cities)     search     (auxiliary,    (OpenTripMap,      (OpenTripMap,
                 (Chroma)   no LLM)        saves + reindex)   no persistence)
```

## What's in this directory

| File | Purpose |
|---|---|
| `activities_agent.py` | The merged agent — all tools from both original versions, `answer(task)` primary entry point |
| `corpus_expand.py` | Fetches + saves live OpenTripMap data (tier 3) |
| `build_vector_db.py` | Builds the Chroma index across all 6 cities' data (tier 2) |
| `offline_embedding.py` | Deterministic fake embedding function for offline testing |
| `mcp_opentripmap_server.py` | The MCP server (tier 3b) |
| `local_activity_docs/*.json` | 6 city files — 4 originally from Limeng, 2 from Jainam |
| `test_jig.py` | Tests covering data and tools from BOTH original versions |
| `run_tests_offline.py` | Runs tool tests with no network/API key/model download |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for both API keys |

## Merge decisions (see the full rationale in activities_agent.py)

1. **Embedding model**: Chroma's default was kept over Jainam's
   original choice of a local Ollama install, to avoid requiring
   every user of this merged agent to separately install and run
   Ollama.
2. **Orchestrator entry point**: `answer(task)` (Limeng's, matching
   the team convention) is the primary interface. Jainam's original
   `ask_activities(destination, interests, constraints, limit)`
   signature is kept as a backward-compatible wrapper that builds a
   task string and calls `answer()` internally.
3. **Food/dining guard**: Limeng's deterministic, code-level check
   (bypassing the model entirely) was kept, since it doesn't depend
   on the model following the system prompt.
4. **Auxiliary tools**: Jainam's `hard_filter_activities` and
   `list_curated_cities` were both kept — they don't conflict with
   anything in Limeng's version and are independently useful.
5. **Live-fetch mechanism**: Limeng's `corpus_expand.py` (direct
   `requests` calls, no extra dependency) is the underlying
   implementation for tier 3.

## Setup

```bash
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate         # Windows

pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:
- `OPENROUTER_API_KEY` — required
- `OPENTRIPMAP_API_KEY` — optional but recommended for tier 3; free at
  [dev.opentripmap.org](https://dev.opentripmap.org)

```bash
python build_vector_db.py     # one-time, builds ./chroma_db across all 6 cities
python activities_agent.py    # runs 9 self-test tasks end-to-end
```

## Testing

```bash
python test_jig.py            # requires OPENROUTER_API_KEY for black-box tests
python run_tests_offline.py   # no network, no API key needed
```

The offline suite currently passes 14/14, covering exact filtering
and semantic search for cities from BOTH original implementations,
the food guard, the auxiliary tools, and the self-expanding corpus
tool's error handling.

## Known limitations

- 6 cities covered locally out of the box (33 hand-picked/curated
  activities total).
- Tier 3/3b (OpenTripMap) has no pricing data — `price_tier` is
  `"unknown"` for those results.
- `build_vector_db.py`'s first run downloads a small embedding model
  (requires internet); use `run_tests_offline.py` if that's not
  available.
- `expand_activities_corpus()` overwrites a city's local file if
  called again for the same city — it isn't designed to merge with
  already-existing data for that city.
