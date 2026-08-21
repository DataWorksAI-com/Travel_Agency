# Activities Agent — Multi-city (+ MCP fallback)

Author: Limeng Zhang

Domain-expert agent for "things to do." Three-tier knowledge source,
now covering **4 cities locally** (New York, Paris, Rome, Kyoto)
instead of just one, with a live MCP fallback for everywhere else.

## Why multiple cities

The Destination Agent's semantic recommender draws from its own
47-city corpus (`destination_data/destinations.json`), which does
**not** include New York. That meant a traveler who gets a
destination *recommended* (rather than naming one directly) would
almost never be routed to my original New York-only data — most
real usage would fall through to the MCP tier, which has no pricing
data and thinner descriptions.

Paris, Rome, and Kyoto are all in that 47-city corpus, so adding
them means my curated tier 1/2 data actually gets used across a
realistic range of recommended destinations, not just when a user
names New York directly.

## Architecture

```
                    ┌─────────────────────────┐
   task string  →   │   Activities Agent       │  →  answer(task)
  (from orchestrator)│  (Deep Agents + LLM)     │     one message out
                    └───────────┬─────────────┘
                                │ picks a tool based on the request
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                  ▼
      Tier 1: exact       Tier 2: semantic    Tier 3: MCP live
      local filter        search (Chroma)     (OpenTripMap API)
      per-city JSON       across covered      ANY city not locally
      (4 covered cities)  cities              covered
```

**Tier 1 — exact local lookup**: filters a city's `<city>.json` file
directly by `category`/`price_tier`. No LLM reasoning, no network
call. Fastest and most reliable, but only for covered cities.

**Tier 2 — local semantic search**: Chroma vector DB across all
covered cities' data (tagged with `city` metadata), for descriptive/
vague queries. Can be filtered to one city or searched across all
covered cities at once.

**Tier 3 — MCP live fallback**: `mcp_opentripmap_server.py`, a real
MCP server wrapping the OpenTripMap REST API, run as a subprocess and
connected over stdio via `langchain-mcp-adapters`. Used for any city
not in the locally covered list.

## What's in this directory

| File | Purpose |
|---|---|
| `local_activity_docs/*.json` | One file per covered city (New York, Paris, Rome, Kyoto) |
| `build_vector_db.py` | Builds the Chroma index across all city files (tier 2) |
| `mcp_opentripmap_server.py` | The MCP server (tier 3) |
| `activities_agent.py` | The agent: tool definitions, `build_agent()`, `answer(task)` entry point |
| `test_jig.py` | Regression tests — tool tests + black-box agent tests |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for both API keys |

## Adding a city

Drop a `<city>.json` file into `local_activity_docs/` (same schema:
`name`/`category`/`price_tier`/`description`), then re-run
`build_vector_db.py`. No code changes needed — both tier 1 and tier 2
pick up new city files automatically.

## Orchestrator contract

- **Input:** a single task string. No shared context with other
  sub-agents — anything needed must be in that string.
- **Output:** `answer(task)` returns exactly one self-contained
  string. Never asks a follow-up question — if a tool errors or a
  detail is missing, it says so plainly in that one message.
- **Specificity:** the final message names each activity, its
  category, its price tier (or "unknown" for tier-3/MCP results),
  and a short description — ready for a day-by-day itinerary.

Matches the team's shared `answer(task)` convention (also used by
Budget, Money & Customs, and Restaurants).

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
python build_vector_db.py     # builds ./chroma_db (tier 2; internet required for the embedding model download, one time)
python activities_agent.py    # runs 7 self-test tasks end-to-end
```

## Testing

```bash
python test_jig.py
```

Tool tests (deterministic) verify each covered city's exact filter,
the "food is out of scope" boundary, and the "uncovered city" error
path. Black-box agent tests (via `answer()`) include a true-negative
case — asking for scuba diving in New York, which isn't in the
dataset — to catch a hallucinating agent.

## Known limitations

- Only 4 cities covered locally (20 hand-picked activities total).
- Tier 3 (OpenTripMap) has no pricing data — `price_tier` is
  `"unknown"` for those results.
- `build_vector_db.py`'s first run downloads a small embedding model
  (requires internet); every run after that works offline.
- The 4 covered cities were chosen to overlap with the Destination
  Agent's 47-city corpus where possible, not to comprehensively cover
  any particular region.
