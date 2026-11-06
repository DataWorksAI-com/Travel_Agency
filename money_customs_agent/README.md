# Money & Customs Agent

Sub-agent for the multi-agent travel-planning system. Given a destination
(and optionally a home currency), it returns a live exchange rate,
tipping/haggling customs broken down by service, a rough sense of local
price scale, and an optional home-vs-destination comparison.

## Files

| File | Purpose |
|---|---|
| `money_tools.py` | Five standalone tool functions -- no framework dependency, usable by any tool-calling agent. |
| `money_customs_agent.py` | The Deep Agent (LangChain + OpenRouter) wrapping those tools. Exposes `answer(task)` for the Orchestrator and `answer_with_trace(task)` for testing. |
| `test_suite.py` | Section A: tools directly (no key). Section B: full agent, with each tool call printed. |
| `test_agent_edge_cases.py` | Pass/fail checks for edge cases: EUR ambiguity, no currency, city names, typos, unmapped countries, unsupported services. |

## The five tools

1. **`get_exchange_rate`** -- live currency conversion via Frankfurter (no API key required).
2. **`search_money_customs`** -- tipping/haggling lookup for a destination, with a three-tier fallback:
   `exact match -> fuzzy typo correction (difflib, cutoff 0.75) -> semantic search (ChromaDB, cosine similarity)`.
   Below a `0.55` similarity threshold, it returns `found: False` and says plainly that the
   information isn't available, rather than guessing -- it will not substitute a different
   country's facts under the requested country's name.
3. **`get_income_context`** -- rough price-scale reference via World Bank GNI per capita
   (a national average, not a city-level median -- always frame it as such).
4. **`get_comparative_context`** -- combines the above for a home-vs-destination comparison.
   Requires an unambiguous home currency (e.g. `EUR` matches multiple countries and is
   intentionally skipped). If the destination side isn't found, the home side is dropped too --
   a comparison with only one side populated is not a comparison.
5. **`resolve_location_country`** -- resolves a city or region name to a country using the
   Open-Meteo Geocoding API (free, no key), for the one-retry recovery when a traveller names a
   city instead of a country (e.g. "Marrakech" -> "Morocco"). Returns `ambiguous: true` rather
   than guessing when places in several countries share the name (e.g. "Paris"); namesakes under
   1,000 people are ignored, so "Tokyo" is not ambiguous. It finds only populated places and
   regions, so a description ("south of the US border") or an attraction finds nothing.
   Spelling variants are retried once: if "Marrakech" finds nothing (GeoNames spells it
   "Marrakesh"), it searches "Marrak" and keeps only names at least 0.8 similar to what was typed
   and within 2 letters of its length -- so Marrakesh is kept, and look-alikes such as Marrak
   (Pakistan) and Marrakai (Australia) are not.
   **Attribution:** location data from GeoNames (https://www.geonames.org), licensed CC BY 4.0,
   via the Open-Meteo Geocoding API (https://open-meteo.com).

Every tool returns a JSON-serializable dict with `found` and `match_score` fields, so a caller
(human, agent, or Orchestrator) can check confidence programmatically:

- `match_score: null` -- exact match, full confidence, no fuzzy/semantic step was involved.
- `match_score: <number>` -- how the match was found, and how strong it was.
- `found: False` -- no usable data for what was actually asked; do not guess further.

## Data coverage

22 entries in a hand-curated dictionary (`MONEY_CUSTOMS_FACTS`), each disclosing its own
sourcing confidence in a `source` field -- ranging from single-named-authority (e.g. Rick
Steves) to multi-source corroboration to "general knowledge, not independently verified." Two
entries (Barbados, Seychelles) have a documented sourcing conflict on haggling norms specifically
-- see their `haggling_note` fields. Two entries (Bali, Hawaii) are regions, not countries.

Common alternate names map to their entry (`COUNTRY_ALIASES` in `money_tools.py`), e.g.
"United States" and "US" -> USA. Add to it when a lookup misses a name it should know.

Live data (exchange rate, income) is not limited to these 22 -- it depends on Frankfurter's and
the World Bank's own coverage.

The semantic tier's vector store (`money_customs_chroma_db/`) is a cache. It is built on first
use from `MONEY_CUSTOMS_FACTS` and rebuilt automatically when the facts change, so it never
needs to be copied or committed.

## Setup

```bash
pip install -r requirements.txt
```

`chromadb` is only imported lazily, inside `search_money_customs`, the first time a lookup falls
through to the semantic tier -- so the module loads fine without it if you're only using the
other tools.

### Environment variables

The agent reads the shared `.env` file (via `python-dotenv`):

```
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
MONEY_AGENT_MODEL=            # optional, full "openrouter:<model>" string for this agent only

# Optional: to run on a local model in LM Studio instead of OpenRouter,
# remove the # from these three lines and set the model id shown in
# LM Studio's server tab.
# LLM_BACKEND=local
# TRAVEL_LOCAL_MODEL=
# TRAVEL_LOCAL_BASE_URL=http://localhost:1234/v1
```

The setting names match the team's `desktop/local_llm.py`. `TRAVEL_LOCAL_BASE_URL` must point to
a server on this computer (`localhost`, `127.0.0.1` or `::1`, path `/v1`); any other address is
rejected, so prompts in local mode never leave the machine. In LM Studio, keep serving on the
local network turned off, so no one else can use your model.

**Never commit `.env` or a real key.** No key is written in any source file.

### Choosing a model: cloud vs. local

The agent follows eleven rules, and smaller models follow them less reliably. Results on
`test_agent_edge_cases.py` (22 checks):

| Model | Where it runs | Result |
|---|---|---|
| `openai/gpt-4o-mini` | OpenRouter (paid, a few cents per run) | 22 / 22 |
| `google/gemma-4-e4b` | LM Studio, local (free, no key) | 17 / 22 |

What the local 4B model missed: for descriptions like "south of the US border" and "the
Caribbean", it asked the traveller to "please specify" a country -- a follow-up question,
which Rule 6 forbids -- instead of interpreting a clear description (Rule 10). It also
occasionally extended general tipping norms to a service the data doesn't cover, and
mislabeled a source.

What stays reliable on any model, because it is enforced in code rather than by the prompt:
the "retried as" note after a successful city lookup, the currency "Assumption:" line, removal
of fabricated retries when no data was found, and the Sources-line cleanup.

**Recommendation:** use a cloud model for demos and evaluation; use a local model for
offline development and for testing the tools. A larger local model (12B+) may close the gap
but has not been tested here.

## Running

Import and call `answer(task: str) -> str` from `money_customs_agent.py`. This is the shared
contract every sub-agent follows -- one task string in, one self-contained message out, no
follow-up questions. Do not change this function's return type; the Orchestrator depends on it
staying a plain string.

Tests:

```bash
python test_suite.py              # Section A needs no key; Section B needs OPENROUTER_API_KEY
python test_agent_edge_cases.py   # Part 1 needs network only; Part 2 needs a model (OpenRouter key, or LLM_BACKEND=local)
```

## Known limitations

- The Orchestrator only consumes `answer()`'s plain-string output. Confidence data
  (`match_score`, `found`) exists on every tool call but isn't passed through to it.
- Income figures are national averages (GNI per capita, World Bank Atlas method), not
  city-level medians -- treat them as rough scale context, not a precise benchmark.
- Descriptions ("south of the US border") are interpreted by the agent itself (Rule 10): it may
  map a description to ONE country, and must open its reply with "Note: I interpreted ... as
  ...". Multi-country descriptions ("the Caribbean") are answered as "held per country".
  Because the model makes this call, it can be wrong; the disclosure line makes that visible.
- `resolve_location_country` keeps a result only if its own name resembles the input, so
  abbreviations such as "NYC" find nothing. Landmarks are not resolved.
- If no tool found any data, the agent's reply cannot claim a retry or an interpretation: a reply
  that does is replaced in code with a plain "not available" message.
- Ubud or Jakarta resolve to Indonesia, but the data holds "Bali", not Indonesia, so the agent
  reports no data for them.
- City-to-country recovery is agent behavior, not tool behavior: `search_money_customs` does
  not resolve "Marrakech" itself. Rule 9 tells the agent to call `resolve_location_country`
  and retry once, which the model usually but not always follows -- see the Rule 9 check in
  `test_agent_edge_cases.py`.
