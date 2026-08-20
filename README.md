# Travel Agency — Destination Agent

A multi-agent RAG travel chatbot. This repository holds the **Destination Agent**: it
recommends a destination from a traveller's stated preferences, or reports typical
climate and public holidays for a place they name, and serves both through a Chainlit
chat UI.

**This branch (`climate_timing_joel`) is a complete working copy** — the agent, the
data layer, the corpus, and the UI, all runnable together.

---

## Architecture

Three layers, each independently usable.

### 1. The agent — `destination_agent/`

A deep agent (`deepagents` + LangChain + `claude-haiku-4-5`) that does the reasoning and
routing. It exposes exactly two tools to the model:

| Tool | Purpose |
|---|---|
| `get_destination_info(destination_name)` | Case 1 — a named place |
| `search_destinations(preferences)` | Case 2 — preference-based search |

Entry point: `run_destination_agent(user_query: str) -> str` in
`destination_agent/destination_agent.py`.

It also owns **Geoapify enrichment** (`geoapify_data.py`), which attaches real
points of interest in four categories — `beaches`, `attractions`, `nature` (nature
reserves) and `diving` (dive centres) — cached to `destination_profiles.json`.

### 2. The data layer — `destination_data/`

Four tools. Each returns plain Python dicts/lists, and **never raises** — every failure
returns `{"error": "..."}`.

| Tool | File | Source |
|---|---|---|
| `recommend_destinations(preferences, top_k=5)` | `recommend.py` | RAG over the local corpus (ChromaDB + MiniLM) |
| `resolve_place(city_name)` | `resolve_place.py` | Open-Meteo Geocoding |
| `get_climate(lat, lon)` | `climate.py` | Open-Meteo ERA5 archive |
| `get_holidays(country_code, year=None)` | `holidays.py` | Nager.Date |

### 3. The UI — `app.py`

A Chainlit chat app at the repo root. It wraps `run_destination_agent` and adds nothing
else: the call is async-wrapped (it blocks ~10–15 s), replies are normalised to text,
and errors surface as a message instead of a crashed session.

### 4. The corpus — `destination_data/destinations.json`

51 destinations. Every field is fetched from a real API — population, region, coastal
status, annual mean temperature — and the description is composed from those fields.
`build_corpus.py` regenerates it from a hand-picked list of 47 seed cities; the
remaining entries were added at runtime (see *Known issues*).

### Query flow

```
                        user
                         |
                    app.py (Chainlit)
                         |
              run_destination_agent()
                         |
              agent decides the case
                 /                \
        CASE 1                    CASE 2
   named a place            gave preferences
        |                          |
   resolve_place()        recommend_destinations()
   (any city, live)        (RAG over 51-entry corpus)
        |                          |
        |                   picks ONE candidate
        \                        /
         +----------+-----------+
                    |
          Geoapify profile (POIs)
          get_climate(lat, lon)
          get_holidays(country_code)
                    |
                 answer
```

Both paths return `name`, `country_code`, `lat`, `lon`, so climate and holidays can be
called straight afterwards with no re-resolving.

---

## The two cases

**Case 1 — the user names a place.** `resolve_place` geocodes it live, so this works for
*any* city on earth, not just corpus entries. The agent then enriches with Geoapify POIs,
climate, and holidays.

**Case 2 — the user describes what they want.** `recommend_destinations` embeds the query
and returns the 5 nearest corpus entries by cosine similarity. Each is enriched with
Geoapify data, the agent picks exactly **one** recommendation (mentioning up to two
alternatives), then calls Case 1's tool on the winner for full detail. When the top
`match_score` is below 0.30 the tool returns a `retrieval_note`, and the agent asks a
clarifying question instead of recommending.

---

## Data sources and keys

**Free and keyless** — the entire data layer:

- **Open-Meteo Historical Weather API** (`/v1/archive`, ERA5 reanalysis) — climate.
  Deliberately the archive endpoint, not `/v1/climate`, which serves model projections.
- **Open-Meteo Geocoding API** — place resolution and corpus fields.
- **Open-Meteo Marine API** — coastal/inland test at corpus build time.
- **Nager.Date** — public holidays.
- **ChromaDB + `all-MiniLM-L6-v2`** — vector store and embeddings, entirely local.

**Requires an API key** — the agent layer only:

- **`ANTHROPIC_API_KEY`** — required. The LLM (`claude-haiku-4-5`). Without it the app
  fails at startup.
- **`GEOAPIFY_API_KEY`** — optional. POI enrichment. Without it the agent still returns
  climate and holidays, and reports travel features as unavailable.
- **`LANGSMITH_API_KEY` / `LANGSMITH_TRACING` / `LANGSMITH_PROJECT`** — optional tracing.

---

## Running it

**Python 3.13, Windows.** Packages, from the actual imports:

```powershell
pip install deepagents langchain-anthropic chainlit chromadb requests truststore python-dotenv
```

Create `destination_agent/.env` — **gitignored, so it must be created locally**. Variable
names only:

```
ANTHROPIC_API_KEY=
GEOAPIFY_API_KEY=
LANGSMITH_API_KEY=
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=destination-agent
```

Launch the UI **from the repo root** — the agent uses package-absolute imports
(`destination_agent.*`, `destination_data.*`) which only resolve from there:

```powershell
chainlit run app.py
```

Opens `http://localhost:8000`. To run the agent headless instead:

```powershell
python -m destination_agent.destination_agent
```

**First run** downloads the ~80 MB MiniLM embedding model to `~/.cache/chroma` and builds
the Chroma index under `destination_data/chroma_db/`, so the first preference query is
slow. Both are cached afterwards, and `chroma_db/` is gitignored because it rebuilds
itself — the corpus text is SHA-256 fingerprinted, so editing `destinations.json`
re-embeds automatically.

### truststore

Every file that makes network calls runs `import truststore; truststore.inject_into_ssl()`
**before** importing `requests`. This network intercepts HTTPS with a certificate Windows
trusts but Python does not; without the injection, calls hang about five minutes and then
fail with no useful error. It is not optional on this network.

---

## Known issues and limitations

**The agent is stateless.** Every call builds a fresh single-message list, so there is no
conversation memory. Follow-ups like *"what about Thailand instead?"* arrive with no
context and are treated as new requests. This particularly affects the low-confidence
flow: the agent asks *"which preference matters most?"*, but the answer comes back with no
memory of the question. Fixing it means passing message history into `agent.invoke`.

**Medical and health queries route through the RAG** rather than deferring to an
authoritative source. Asked about vaccinations or health risks, the agent answers from
retrieved destination text instead of pointing at CDC/WHO. There is no medical guardrail.

**Geoapify sometimes mislabels inland cities.** Category radius searches can return
beaches or dive centres for a landlocked place — Paris being the clearest case. The POIs
are real records, but their relevance to the named city is not verified.

**Holidays are unavailable for some countries.** Nager.Date covers 204 countries;
Thailand and Fiji, among others, are not included. `get_holidays` returns an error dict —
treat "no holidays" as a normal outcome, not a failure to retry.

**`match_score` is semantic similarity, not quality.** It measures text closeness and is
meaningful only as a relative rank; values cluster around 0.3–0.5 even for good matches.
It is never a rating of how good a destination is.

**Recommendations are limited to the corpus** (51 entries). Named cities via
`resolve_place` are not — that path is worldwide.

**The corpus grows at runtime.** `expand_rag_corpus.py` writes newly queried destinations
into `destinations.json`. Four entries arrived this way — Aruba, Seychelles, Fiji, and
Tokyo, the last added during a live demo. Useful, but it means the committed corpus can
change from ordinary use, and `build_corpus.py` must not clobber it (see changelog).

---

## Recent changes on this branch

- **Climate months are now location-relative.** Rainfall is judged against the location's
  own median month rather than a fixed millimetre threshold. The absolute rule made
  `best_months` permanently empty for equatorial climates — Singapore's driest month is
  ~101 mm — while flagging two thirds of the year as avoid. Temperature stays absolute
  (`COMFORT_MIN_C` 15 °C, `HARD_COLD_C` 8 °C) but no longer vetoes on its own, and
  `avoid_months` is capped at 4 so it can never be most of the year.
- **`build_corpus.py` is non-destructive.** A rebuild preserves `rag_text` and
  `geoapify_profile` written by the agent layer, and carries over runtime-added entries
  instead of deleting them.
- **Dynamic entries are field-complete (prototype).** Runtime-added destinations now get
  real `_source_fields` and a composed description, reusing `build_corpus.py`'s fetchers,
  instead of the placeholder `"<name> is a travel destination."`
- **truststore and path fixes in the agent scripts.** `geoapify_data.py` now injects
  truststore before `requests`; `enrich_rag_corpus.py` and `expand_rag_corpus.py` resolve
  the corpus path from `__file__` rather than the working directory, so they work from any
  directory.
- **Chainlit UI added** (`app.py`).
