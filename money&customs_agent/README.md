# Money & Customs Agent

Sub-agent for the multi-agent travel-planning system. Given a destination
(and optionally a home currency), it returns a live exchange rate,
tipping/haggling customs broken down by service, a rough sense of local
price scale, and an optional home-vs-destination comparison.

## Files

| File | Purpose |
|---|---|
| `money_tools.py` | Four standalone tool functions -- no framework dependency, usable by any tool-calling agent. |
| `money_customs_agent.py` | The Deep Agent (LangChain + Cohere) wrapping those tools. Exposes `answer(task)` for the Orchestrator. |

## The four tools

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

Every tool returns a JSON-serializable dict with `found` and `match_score` fields, so a caller
(human, agent, or Orchestrator) can check confidence programmatically:

- `match_score: null` -- exact match, full confidence, no fuzzy/semantic step was involved.
- `match_score: <number>` -- how the match was found, and how strong it was.
- `found: False` -- no usable data for what was actually asked; do not guess further.

## Data coverage

22 countries in a hand-curated dictionary (`MONEY_CUSTOMS_FACTS`), each disclosing its own
sourcing confidence in a `source` field -- ranging from single-named-authority (e.g. Rick
Steves) to multi-source corroboration to "general knowledge, not independently verified." Two
entries (Barbados, Seychelles) have a documented sourcing conflict on haggling norms specifically
-- see their `haggling_note` fields.

Live data (exchange rate, income) is not limited to these 22 -- it depends on Frankfurter's and
the World Bank's own coverage.

## Setup

```bash
pip install -r requirements.txt
```

`chromadb` is only imported lazily, inside `search_money_customs`, the first time a lookup falls
through to the semantic tier -- so the module loads fine without it if you're only using the
other three tools.

### Environment variables

Copy `.env.example` to `.env` and fill in a real `COHERE_API_KEY`. **Never commit a real key** --
see `.gitignore`, which already excludes `.env`.

Note: this file doesn't currently load `.env` automatically (no `python-dotenv` wired in) --
export the key directly in your shell before running, e.g. `export COHERE_API_KEY="..."`.

## Running

Import and call `answer(task: str) -> str` from `money_customs_agent.py`. This is the shared
contract every sub-agent follows -- one task string in, one self-contained message out, no
follow-up questions. Do not change this function's return type; the Orchestrator depends on it
staying a plain string.

## Known limitations

- The Orchestrator currently only consumes `answer()`'s plain-string output. Confidence data
  (`match_score`, `found`) exists on every tool call but isn't yet passed through to the
  Orchestrator's own decision-making.
- `get_income_context` and `get_comparative_context`'s income figures are national averages
  (GNI per capita, World Bank Atlas method), not city-level medians -- treat as rough scale
  context, not a precise benchmark.
- No city-to-country resolution exists in the tools themselves (e.g. querying "Marrakech" will
  not automatically resolve to Morocco inside `search_money_customs`) -- in practice this is
  handled by the agent's own reasoning, reformulating a failed lookup with a country name and
  retrying, but that is model behavior, not a guaranteed mechanism.
