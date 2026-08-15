# Destination Data Layer

The data/retrieval layer for the **Destination Agent** in the multi-agent travel system.

This folder provides **data tools only — it is not the agent.** There is no LLM call,
no system prompt, and no orchestration here. Alice builds the agent on top of these
tools; each tool is independently callable in-process and knows nothing about the others.

## The four tools

| Tool | File | Returns | Used when |
|---|---|---|---|
| `recommend_destinations(preferences, top_k=5)` | `recommend.py` | list of ~3–5 `{name, country_code, lat, lon, description, match_score}` | **Case 2** — the user described what they want but named no city. RAG over the local corpus. |
| `resolve_place(city_name)` | `resolve_place.py` | `{name, country_code, lat, lon}` | **Case 1** — the user already named a city. Live lookup, works for *any* city, not limited to the corpus. |
| `get_climate(lat, lon)` | `climate.py` | `{monthly, best_months, avoid_months, period, source, note}` | Enrichment — historical typical conditions by month. |
| `get_holidays(country_code, year=None)` | `holidays.py` | list of `{date, name, local_name}` | Enrichment — public holidays. Defaults to the current year. |

Both recommendation paths return `name`, `country_code`, `lat` and `lon`, so
`get_climate` and `get_holidays` can be called straight afterwards with no re-resolving.

## Data sources — all free, all keyless

**No API keys are required for this data layer.** There is no `.env` and nothing to configure.

- **Nager.Date** — public holidays (`holidays.py`)
- **Open-Meteo Historical Weather API (ERA5 archive)** — monthly climate averages (`climate.py`).
  This is the `/v1/archive` endpoint (real observed past weather), deliberately not
  `/v1/climate`, which serves model projections.
- **Open-Meteo Geocoding API** — city name → coordinates + country code (`resolve_place.py`)
- **Open-Meteo Geocoding + Marine + Archive** — corpus fields (`build_corpus.py`).
  Continent comes from the geocoder's IANA `timezone` prefix; coastal/inland from whether
  the marine grid returns a wave height at the city's coordinate.
- **ChromaDB + `all-MiniLM-L6-v2`** — local vector store and embeddings (`recommend.py`).
  Runs entirely on this machine.

## Contract

Every tool follows the same rules:

- Returns **plain Python dicts/lists, never JSON strings** — the agent calls these in-process.
- **Never raises.** Every failure — bad input, network error, non-200, bad JSON, missing
  fields — returns `{"error": "..."}`. Callers should check for an `error` key, not catch exceptions.
- **Reports only what the source returned.** Nothing is filled in from model knowledge.
  If a lookup fails, the field is omitted or reported unavailable — never guessed.
- **Climate is historical typical conditions, not a forecast** and not a guarantee. The
  returned `note` field says so; keep that framing in any user-facing text.

## The corpus

`destinations.json` holds 47 well-known travel destinations, built by `build_corpus.py`.

The **list of city names is hand-picked** (which places count as "well-known travel
destinations" is a judgement call, not a fact in any API). **Every field attached to them
is fetched** — name, country code, coordinates, population, region, timezone, coastal
status and annual mean temperature. Each entry also carries a `_source_fields` block
recording the raw values its description was composed from.

Descriptions are assembled from those structured fields, e.g.:

> Phuket is a coastal small city (population 79,308) in Phuket, Thailand, in Asia. Typical
> annual average temperature is 27.2°C, a hot tropical climate, warm all year round. It
> sits on the sea, with beaches and coastal scenery.

## Known limitations

- **Recommendations are limited to the ~47-city corpus.** Cities named directly via
  `resolve_place` are not — that path handles any city worldwide.
- **Holidays are unavailable for some countries.** Nager.Date covers 204 countries;
  Thailand is not among them and returns an error dict. **Treat "no holidays" as a normal
  outcome**, not a failure to retry.
- **`match_score` is semantic similarity** (how close the text is), a **relative rank only**.
  It is not a travel-quality rating and its absolute value means little — scores cluster
  in roughly 0.3–0.5 even for good matches.
- **Vector search matches topic more strongly than hard attributes.** A query for
  `["cool", "historic", "Europe", "inland"]` ranks coastal Nice first and inland Paris
  fifth. Hard constraints are better enforced by filtering the structured fields than by
  hoping the embedding respects them.
- **Bangkok is classified inland** (~25 km from the Gulf), so it will not surface for
  coastal queries. The coastal test is grid coverage at the city's own coordinate.
- **First run of the RAG downloads the ~80 MB MiniLM model** to `~/.cache/chroma`.
  Every run after that is offline.
- **Editing `destinations.json` re-embeds automatically.** The description text is
  fingerprinted (SHA-256), so a changed corpus is detected even if the entry count is unchanged.

## Environment

- **Python 3.13, Windows**, with a fresh `.venv` inside this folder (not shared with any
  other project in this repo).
- **`truststore` is required.** This network intercepts HTTPS with a certificate Windows
  trusts but Python does not. Every file that makes network calls runs
  `import truststore; truststore.inject_into_ssl()` **before** importing `requests` or
  triggering any download. Without it, calls hang ~5 minutes and fail with no useful error.
- **Run with `PYTHONIOENCODING=utf-8`** so non-ASCII place names and symbols
  (`Malé`, `Cancún`, `27.2°C`) print instead of crashing the console.

Setup from scratch:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install requests truststore chromadb
```

## Running the self-tests

Each tool file has a `__main__` block that exercises it, including a deliberate
failure case to prove it returns an error dict instead of crashing.

```powershell
$env:PYTHONIOENCODING='utf-8'

# Holidays: FR (works), TH (not covered), ZZ (invalid)
.\.venv\Scripts\python.exe holidays.py

# Climate: Bangkok (tropical), Paris (temperate), lat=999 (invalid)
.\.venv\Scripts\python.exe climate.py

# Place lookup: Tokyo (not in corpus), asdfghjkl, blank, non-string
.\.venv\Scripts\python.exe resolve_place.py

# RAG: two preference queries plus an empty one
.\.venv\Scripts\python.exe recommend.py
```

## Regenerating the corpus

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe build_corpus.py
```

This makes ~140 live API calls (three per destination, with a polite delay) and takes a
couple of minutes. It overwrites `destinations.json`. Seed cities live in `CITY_SEEDS` at
the top of `build_corpus.py`; population, temperature and region thresholds are named
constants above it. The next `recommend_destinations` call re-embeds automatically —
there is no need to delete `chroma_db/`.
