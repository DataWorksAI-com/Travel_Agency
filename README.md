# Travel Agency — multi-agent RAG travel planner

Six agents (Destination, Flights, Restaurants, Activities, Budget, Money &
Customs) coordinated by an orchestrator and served through a Chainlit chat UI.

## Run the UI

```powershell
chainlit run app.py -w
```

No keys and no vector stores needed for the default path — every slot starts on
a deterministic stand-in. Turn real agents on one at a time.

## Connecting and disconnecting real agents

One environment variable, no code change:

```powershell
$env:TRAVEL_UI_AGENTS = "flights=real,restaurants=real"
```

Slots: `destination`, `flights`, `restaurants`, `activities`, `budget`,
`money_customs`. Modes: `real` and `dummy`. Omit a slot and it stays on
`dummy`. The "Agents currently connected" message on open tells you what was
actually accepted.

**A slot set to `real` that cannot be reached reports `NOT CONNECTED` with the
cause — it never silently shows sample data.** Each step header also carries
elapsed time, which is the real evidence: a stand-in returns in `0.0s`, a live
agent cannot.

## Where things live

| Document | What it covers |
|---|---|
| [`RUNNING_THE_UI.md`](RUNNING_THE_UI.md) | **Start here.** Running it, switching your agent on, proving it ran, reading failures. §3b has a verified known-good configuration. |
| [`UI_STATUS.md`](UI_STATUS.md) | What is live, what is blocked, and on what |
| [`ENVIRONMENT.md`](ENVIRONMENT.md) | Every environment variable, with `file:line` |
| [`ORCHESTRATOR_DESIGN.md`](ORCHESTRATOR_DESIGN.md) | The orchestrator's open design decisions |
| `app.py`, `ui/` | The Chainlit UI and the real-vs-stand-in seam |
| `orchestrator.py`, `orchestrator_config.py`, `subagent_client.py` | Sequencing, slot registry, transport |

Each agent has its own README in its own directory.

---

# Money & Customs Agent

> The rest of this file documents the Money & Customs agent specifically. It
> became the repository README in `0798e35`, which replaced the previous
> project-level README; the orientation above restores that without removing
> anything. Worth moving this into its own file at some point.

## What it does
Gives a traveller four things in one answer: the live exchange rate between
their home currency and the destination's, money-related customs for the
destination (tipping and haggling norms, broken down per service where
relevant), a rough sense of local price scale via national income context,
and -- if their currency unambiguously implies a home country -- a direct
comparison between home and destination. Built to be called by the
group's **Orchestrator Agent**, which folds the relevant parts into
whichever subagent's task string needs them -- this agent's knowledge is
not shared directly among subagents themselves.

## Contract
- **Input:** one plain-language task string from the orchestrator (e.g.
  origin + destination + what the traveller wants to know).
- **Output:** one self-contained message, itinerary-ready.
- **Ask-vs-assume policy:** never asks a follow-up question. If something
  is missing or ambiguous, it states one reasonable assumption (prefixed
  `Assumption:`) and answers anyway -- same policy as the Budget and
  Restaurants agents.

## Knowledge sources
| Tool | Source | Type |
|---|---|---|
| `get_exchange_rate` | Frankfurter API (ECB-backed) | Live, free, no key |
| `search_money_customs` | **Hand-curated data, not sourced from a verified external dataset** (see note below); agentic RAG: exact match \u2192 fuzzy typo correction \u2192 semantic search (local ChromaDB) | Static + local vector search |
| `get_income_context` | World Bank Open Data API (GNI per capita) | Live, free, no key |
| `get_comparative_context` | No new data source -- calls the two tools above twice each (home + destination) | Composite |

**Country coverage today (17 total):** France, India, USA, Japan, Mexico,
Morocco, Germany, Jamaica, Dominican Republic, Bahamas, Thailand, Bali,
Philippines, Costa Rica, Belize, Fiji, Hawaii. Add more by extending
`MONEY_CUSTOMS_FACTS`, `GEOGRAPHY`, and `COUNTRY_ISO3` in `money_tools.py`
(all three use the same country-name keys, kept in sync intentionally).

**Honesty note on the customs data itself:** every country's entry in
`MONEY_CUSTOMS_FACTS` carries a `source` field, so provenance travels with
the data itself rather than living only in this README. Confidence varies
by tier, not uniform across all 17:
- **France** -- Rick Steves (ricksteves.com/travel-tips/money/tipping-in-europe
  and his community forum), a well-regarded, published European travel
  authority. The strongest-sourced entry.
- **Thailand, Bali, Philippines** -- corroborated across multiple sources
  including Lonely Planet's tipping-customs guide, itself a well-regarded
  travel authority.
- **Jamaica, Dominican Republic, Bahamas, Costa Rica, Fiji, Hawaii** --
  corroborated across several independent travel guides each, though no
  single named authority like Rick Steves or Lonely Planet.
- **Belize** -- a single source (Upgraded Points' worldwide tipping guide);
  the weakest-corroborated entry in the dataset.
- **India, USA, Japan, Mexico, Morocco, Germany** -- hand-written from
  general knowledge, **not** independently verified. Say so explicitly in
  their own `source` field.

Anyone extending this data should check the `source` field first and
prioritize verifying the unverified entries over adding new countries.

**Scope note:** the actual assignment describes a travel agent for
**tropical vacation tours**. The 10 destinations above (Jamaica through
Hawaii) were added specifically to cover that scope with real, sourced
content. The original 7 (France, India, USA, Japan, Mexico, Morocco,
Germany) are mostly not tropical -- kept intentionally as a broader,
more inclusive dataset alongside the assignment's actual focus, rather
than removed.

**Honesty note on `get_income_context`:** this reports GNI per capita, a
national *average*, not a city-level *median* -- true free, real-time median
income data isn't reliably available across countries. The tool's own
output says this explicitly so it's never presented as more precise than
it is.

## Setup
```
pip install -r requirements.txt
cp .env.example .env   # then fill in your real CEREBRAS_API_KEY
python agent.py
```

## Known limitations
- **Ambiguous requests with no country/city mentioned** (e.g. "Do I tip for
  room service?") may return an error rather than the agent stating an
  assumption and picking a reasonable default, even though the system
  prompt's rule 6 calls for the latter. Not yet fixed -- worth revisiting
  the prompt wording if this agent gets picked back up.
- **Exchange rate dates may lag a few days on weekends/holidays** -- this
  reflects the European Central Bank's actual publishing schedule via
  Frankfurter, not stale or broken data.
- **Semantic search only knows what's written in its own corpus.** Geography
  was added specifically so phrasing like "south of the US border" can
  resolve correctly, but coverage is limited to the borders/regions
  actually written into `GEOGRAPHY` -- it has no general world knowledge
  beyond that text. Confirmed working for the Mexico/US case; other
  geographic phrasing may still miss depending on wording.
- **The local ChromaDB cache can go stale after editing the corpus,
  despite the fingerprint check meant to auto-invalidate it.** Hit once
  during this session (geography was added, but the old index kept being
  served) -- fixed by manually deleting the `money_customs_chroma_db`
  folder to force a full rebuild. Worth deleting that folder if search
  results ever look like they're ignoring a recent data change.
- **`get_comparative_context`'s currency-to-home-country inference only
  covers 5 unambiguous currencies** (USD, JPY, INR, MXN, MAD). EUR is
  deliberately excluded, since this data covers both France and Germany --
  guessing between them from "EUR" alone would be a real guess, not a
  reasonable assumption. Any other currency also skips the comparison
  rather than guess.
- **Cohere (the current LLM provider) intermittently returns odd
  responses** -- either an empty 200-status response (raw `ApiError`), or
  occasionally a generic refusal ("I'm sorry, I can't help you with that
  request") to a perfectly ordinary question it answers correctly on
  other runs. Confirmed to happen even when run as a plain `.py` file (not
  just in one-line shell commands, which rules out shell-quoting as the
  cause). Retrying the same question has resolved it every time so far;
  worth wrapping in a retry loop if this becomes disruptive.
- **Geography text must never name an unsupported neighboring country.**
  Found and fixed during testing: Philippines' geography originally said
  "east of Vietnam" -- since Vietnam isn't itself one of our destinations,
  asking about Vietnam matched the Philippines' document purely because
  it contained the literal word "Vietnam," not because of genuine
  similarity, and returned Philippines' customs with false confidence
  instead of correctly saying "not found." Fixed by only naming
  neighboring countries that are themselves in `MONEY_CUSTOMS_FACTS`;
  every other neighbor is now described generically (region/coastline)
  instead of by name. Worth re-checking this rule any time a new country
  is added.
- **Provider history, for context:** this agent has run on Cerebras
  (hit a one-time trial-credit wall, not a daily reset), OpenRouter (free
  models require a purchase-history that this account didn't have), and
  now Cohere (currently working, 1,000 free calls/month). Worth knowing if
  picking this back up and the current provider stops working too.
- **Untested:** malformed currency codes, live API failures (Frankfurter or
  World Bank being down/slow), and service names outside the four defined
  in `by_service` (restaurants, taxis, hotel_housekeeping, tour_guides).

## Example
```python
from agent import answer

answer(
    "I'm traveling from the USA to France. What's the current exchange "
    "rate, should I tip at restaurants and hotels, and what's the general "
    "price scale like there?"
)
```

Running `python agent.py` directly executes a hello-world check followed by
this exact scenario, so you can confirm the whole pipeline works end to end
without writing any extra code.

## Reusing just the tools (no agent needed)
`money_tools.py` has no dependency on deepagents, Cerebras, or any agent
framework -- it's three plain Python functions with type hints and
docstrings. Any teammate's agent, in any framework, can do:

```python
from money_tools import get_exchange_rate, get_money_customs, get_income_context
```

and register them as tools directly, without needing this repo's agent,
model choice, or system prompt at all.
