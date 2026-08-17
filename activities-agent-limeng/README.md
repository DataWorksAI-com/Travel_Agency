# Activities Agent — New York (+ MCP fallback)

Author: Limeng Zhang

Domain-expert agent for "things to do." Uses a **three-tier knowledge
source** so it can answer confidently for New York (fast, local,
free) while still handling any other city via a live MCP-wrapped API.

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
      new_york.json       new_york.json       ANY city, via
      New York only       New York only       mcp_opentripmap_server.py
```

**Tier 1 — exact local lookup** (`search_activities_local_exact`):
filters `new_york.json` directly by `category`/`price_tier`. No LLM
reasoning needed for the filter itself, no network call. Fastest and
most reliable path, but New York only and only for exact-match
queries.

**Tier 2 — local semantic search** (`search_activities_semantic`):
Chroma vector DB over the same New York data, for descriptive/vague
queries ("something romantic") that don't map to a clean category.
Still New York only.

**Tier 3 — MCP live fallback** (`mcp_opentripmap_server.py`): a real
MCP server wrapping the OpenTripMap REST API. Used for any city
*other* than New York, since tiers 1–2 have no data for anywhere
else. This is a genuine MCP integration — the server runs as a
subprocess and the agent connects to it over stdio using
`langchain-mcp-adapters`, not just a REST call dressed up as MCP.

## What's in this directory

| File | Purpose |
|---|---|
| `new_york.json` | Tier 1/2 source data: 6 New York activities |
| `build_vector_db.py` | Builds the Chroma index for tier 2 |
| `mcp_opentripmap_server.py` | The MCP server for tier 3 |
| `activities_agent.py` | The agent itself: tool definitions, `build_agent()`, and the `answer(task)` entry point |
| `test_jig.py` | Regression tests — see "Testing" below |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for both API keys |

## Orchestrator contract

- **Input:** a single task string (e.g. `"Find a free outdoor
  activity in New York."`). No shared context with other sub-agents —
  anything needed must be in that string.
- **Output:** `answer(task)` returns exactly one self-contained
  string. The agent never asks a follow-up question — if a tool
  errors or a detail is missing, it says so plainly in that one
  message instead of stopping to ask.
- **Specificity:** the final message names each activity, its
  category, its price tier (or "unknown" for tier-3/MCP results,
  since OpenTripMap doesn't provide pricing), and a short description
  — ready to drop into a day-by-day itinerary.

This matches the team's shared `answer(task)` convention (also used
by the Budget, Money & Customs, and Restaurants sub-agents).

## Setup

```bash
python -m venv venv
source venv/bin/activate      # macOS/Linux
venv\Scripts\activate         # Windows

pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:
- `OPENROUTER_API_KEY` — required (team standard, powers the reasoning model)
- `OPENTRIPMAP_API_KEY` — optional but recommended; free at
  [dev.opentripmap.org](https://dev.opentripmap.org). Without it,
  tier 3 (any city besides New York) returns an honest error instead
  of a result — tiers 1–2 for New York still work fine.

```bash
python build_vector_db.py     # builds ./chroma_db for tier 2 (one-time; internet required for the embedding model download)
python activities_agent.py    # runs 5 self-test tasks end-to-end
```

## Testing

`test_jig.py` is a **test jig** — a fixed set of prompts paired with
expected answers, run through a scoring loop, so you can tell at a
glance whether the agent is still working correctly after a change,
instead of eyeballing output every time. Two levels:

1. **Tool tests** (deterministic, no LLM) — call the tier 1/2 tool
   functions directly and assert exact behavior. Fast and 100%
   reproducible; good for catching a broken filter or DB connection.
2. **Black-box agent tests** (via `answer()`) — send a task string
   through the *full* agent and check the response for expected
   keywords. This is the format a teammate can run against this
   agent without reading the code — the standard black-box pairing
   test required for Week 2/3.

```bash
python test_jig.py
```

Includes a deliberate **true-negative case**: asking for scuba diving
in New York (not in the dataset) should NOT return a fabricated
match — the test checks the response doesn't contain any of the real
NY activity names, catching a broken/hallucinating agent the same way
a false-positive-only test suite would miss.

## Known limitations

- Tiers 1–2 only cover New York (6 hand-picked activities).
- Tier 3 (OpenTripMap) has no pricing data — `price_tier` is reported
  as `"unknown"` for those results, which callers should handle.
- Black-box test cases use keyword matching, not exact-match — LLM
  output varies run to run, so occasional flakiness is expected.
- `build_vector_db.py`'s first run downloads a small embedding model
  (requires internet); every run after that works offline.
