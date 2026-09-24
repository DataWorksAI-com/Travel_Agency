# Multi-Agent Travel Planning System

## Reduced 3-Agent Demo

This branch contains a reduced version of the Capstone multi-agent travel planning system. It focuses on three specialized travel agents coordinated by a central Orchestrator:

- Destination Agent — Joel & Alice
- Flights Agent — Brinda
- Money & Customs Agent — Emily
- Orchestrator — coordinates agent execution and combines results

The reduced branch is intended to provide a smaller, easier-to-demo end-to-end system while the original full multi-agent implementation remains preserved separately under the `v1.0-full-system` tag.

---

## System Architecture

```text
                         User Request
                              |
                              v
                        +-------------+
                        | Orchestrator|
                        +-------------+
                              |
                 +------------+------------+
                 |                         |
                 v                         v
        +------------------+      +------------------+
        | Destination Agent|      | Money & Customs  |
        +------------------+      | Agent            |
                 |                +------------------+
                 v
        Resolved Destination
                 |
                 v
        +------------------+
        | Flights Agent    |
        +------------------+
                 |
                 v
        +-------------------+
        | Final Orchestrated|
        | Travel Response   |
        +-------------------+
```

The Orchestrator provides the integration layer between the specialized agents. Each agent remains responsible for its own domain and returns a self-contained response that can be incorporated into the final travel result.

---

## Agent Overview

### 1. Destination Agent

The Destination Expert Agent supports two main use cases:

1. Providing grounded information about a specific destination.
2. Recommending one destination based on user travel preferences.

#### Main Capabilities

- Specific destination lookup
- Preference-based destination recommendation
- Shared ChromaDB RAG retrieval
- Geoapify Geocoding and Places API integration
- Travel feature and POI enrichment
- Automatic destination profile generation
- Local JSON caching for Geoapify profiles
- Dynamic expansion of the shared destination corpus
- Climate and public holiday enrichment
- Low-confidence retrieval handling
- Deep Agents tool calling
- Claude-based reasoning
- LangSmith tracing
- Agent and Geoapify test jigs

#### Case 1 - Specific Destination

When the user names a destination, the agent:

1. Resolves the destination and coordinates.
2. Retrieves or loads its Geoapify profile.
3. Retrieves travel features and places.
4. Retrieves climate information.
5. Retrieves public holiday information.
6. Adds the destination to the shared RAG corpus if it is not already present.
7. Returns a concise grounded response.

Example:

```text
Tell me about Aruba.
```

#### Case 2 - Destination Recommendation

When the user provides preferences without selecting a destination, the agent:

1. Searches the shared destination RAG corpus.
2. Retrieves a shortlist of candidate destinations.
3. Enriches candidates with Geoapify travel features and places.
4. Compares candidates using retrieved evidence.
5. Selects exactly one Recommended Destination.
6. Retrieves climate and holiday information for the selected destination.
7. Optionally displays up to two alternatives.

The RAG `match_score` is treated as semantic retrieval evidence, not as an overall destination-quality score.

#### Low-Confidence Retrieval

If the shared corpus does not contain a strong match for all stated preferences, the agent avoids forcing a recommendation and instead returns a retrieval limitation and asks the user which preference should be prioritized. No destination is handed to downstream agents until the user clarifies.

#### Knowledge Sources

The Destination Agent uses:

- Shared ChromaDB destination corpus
- Local destination JSON data
- Geoapify geocoding and places data
- Climate data
- Public holiday data
- Cached Geoapify destination profiles

The shared RAG corpus can expand dynamically. A valid named destination that is not already present can be resolved, profiled, validated, added to the shared corpus, and made available for future retrieval.

#### Destination Agent Tests

```bash
python -m destination_agent.test_destination_agent
python -m destination_agent.test_geoapify_data
```

---

### 2. Flights Agent

The Flights Agent handles flight search, route options, and price/date filtering. It is designed to be called by the Orchestrator as a sub-agent rather than used standalone in production.

#### Scope

In scope:

- Flight search
- Route options
- Airport-code resolution
- Price filtering
- Date filtering

Out of scope:

- Flight booking
- Hotels
- Activities
- Destination recommendations

#### Tools

| Tool                                                                           | Purpose                                                                                                             |
|--------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| `get_airport_code(city)`                                                       | Resolves a city name to an IATA airport/city code.                                                                  |
| `search_flights(origin_code, destination_code, date_str=None, max_price=None)` | Searches flight prices between two codes and can fall back to a full-month search when an exact date has no result. |

#### Data Source and Limitations

The Flights Agent uses Travelpayouts data. Prices are real but cached, not guaranteed live booking availability. Coverage varies by route, and less common routes may return no results even after widening the date range.

The Orchestrator should pass city names rather than airport codes because the Flights Agent resolves codes internally.

#### Flights Agent Test

```bash
python flights_agent.py
```

This runs the built-in test query and prints the message trace, including tool calls, intermediate steps, and the final answer.

---

### 3. Money & Customs Agent

The Money & Customs Agent provides destination-specific financial and cultural travel context. Given a destination, and optionally a home currency, it can return exchange-rate information, tipping and haggling customs, a rough local price-scale context, and an optional home-versus-destination comparison.

#### Main Tools

1. `get_exchange_rate` — live currency conversion through Frankfurter; no API key required.
2. `search_money_customs` — destination customs lookup with a three-tier fallback:

```text
Exact match
    |
    v
Fuzzy typo correction
    |
    v
ChromaDB semantic search
```

The fuzzy tier uses `difflib` with a cutoff of `0.75`. The semantic tier uses cosine similarity. Below a `0.55` similarity threshold, the tool returns `found: False` instead of guessing or substituting a different country's facts.

3. `get_income_context` — rough national price-scale reference using World Bank GNI per capita. These figures are national averages, not city-level medians.
4. `get_comparative_context` — combines money/customs and income context for a home-versus-destination comparison when both sides can be resolved reliably.

#### Confidence Fields

Money & Customs tools return JSON-serializable dictionaries with `found` and `match_score` fields:

- `match_score: null` — exact match; no fuzzy or semantic step was needed.
- `match_score: <number>` — strength of the fuzzy or semantic match.
- `found: False` — no usable data for the requested destination; the system should not guess further.

#### Data Coverage

The curated Money & Customs knowledge base currently covers 22 countries. Exchange-rate and income-data coverage may extend beyond those 22 countries because those values depend on Frankfurter and World Bank coverage.

#### Agent Contract

The Money & Customs Agent exposes:

```python
answer(task: str) -> str
```

The Orchestrator consumes the returned self-contained plain-text response.

#### Money & Customs Limitations

- Confidence metadata is produced by the tools but is not currently propagated directly into Orchestrator decision-making.
- Income figures are national averages, not city-level medians.
- City-to-country resolution is not guaranteed inside the tools themselves; the agent may reformulate a city lookup using a country name, but that is model behavior rather than a fixed tool-level guarantee.

---

## Orchestrator

The Orchestrator coordinates the three specialized agents and provides the integration layer for the reduced system.

### Main Responsibilities

1. Receive the user's travel-planning request.
2. Determine which agent capabilities are required.
3. Send appropriate tasks to specialized agents.
4. Pass relevant destination context between agents.
5. Collect agent responses.
6. Assemble the final travel-planning response.
7. Degrade gracefully when an agent is unavailable rather than crashing the whole workflow.

### Current Integration Contract

The current integration primarily uses a lightweight text-based sub-agent contract:

```text
task: str
    |
    v
Specialized Agent
    |
    v
self-contained response: str
```

This keeps agents loosely coupled and easier to test independently.

### Flights Integration Detail

Flights currently uses a dictionary-style sub-agent specification, and the Orchestrator includes compatibility logic for that shape. Aligning Flights to the same `build_agent()` / `answer()` pattern used by other sub-agents would simplify the integration layer in the future.

### Transport Status

The current reduced system runs agents locally through Python integration. A SLIM/A2A transport shape has been designed, but the agents are not currently deployed as separately running A2A services. Local function-based integration is what runs today.

---

## Example End-to-End Flow

Example user request:

```text
Plan a 7-day trip from Boston to Paris.
Include destination information, flights,
exchange-rate information, and local tipping customs.
```

Simplified flow:

```text
1. User request
       |
       v
2. Orchestrator parses the request
       |
       v
3. Destination Agent
   - resolves or recommends the destination
   - retrieves destination evidence
   - adds travel/climate/holiday context
       |
       v
4. Flights Agent
   - resolves airport codes
   - searches available cached flight-price data
       |
       v
5. Money & Customs Agent
   - retrieves exchange-rate context
   - provides tipping / haggling / money customs
       |
       v
6. Orchestrator combines the results
       |
       v
7. Final travel response
```

---

## Project Structure

```text
Capstone/
├── destination_agent/
│   ├── destination_agent.py
│   ├── geoapify_data.py
│   ├── destination_profiles.json
│   ├── enrich_rag_corpus.py
│   ├── expand_rag_corpus.py
│   ├── test_destination_agent.py
│   ├── test_geoapify_data.py
│   └── README.md
│
├── destination_data/
│   ├── recommend.py
│   ├── resolve_place.py
│   ├── climate.py
│   ├── holidays.py
│   └── destinations.json
│
├── money&customs_agent/
│   ├── money_customs_agent.py
│   ├── money_tools.py
│   ├── requirements.txt
│   └── README.md
│
├── flights_agent.py
├── FLIGHTS_AGENT_README.md
├── orchestrator.py
├── orchestrator_agent.py
├── orchestrator_config.py
├── subagent_client.py
├── app.py
├── requirements.txt
├── .env.example
├── ENVIRONMENT.md
├── HANDOFF.md
├── ORCHESTRATOR_DESIGN.md
├── RUNNING_THE_UI.md
└── README.md
```

---

## Shared Requirements

The reduced system uses a shared root `requirements.txt` for the Destination, Flights, Money & Customs agents, and the Chainlit UI.

```text
# Shared dependencies for the Destination, Flights, Money & Customs agents, and Chainlit UI

deepagents==0.7.4
chainlit
chromadb
langchain
langchain-anthropic
langchain-cohere
langchain-openrouter==0.2.7
python-dotenv==1.2.2
requests
truststore
```

Install all shared dependencies from the project root:

```bash
pip install -r requirements.txt
```

Recommended Python version: **Python 3.11**.

---

## Environment Variables

Create a local `.env` file or configure the required environment variables in the shell. Never commit real API keys.

Example:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
GEOAPIFY_API_KEY=your_geoapify_api_key
TRAVELPAYOUTS_TOKEN=your_travelpayouts_token
OPENROUTER_API_KEY=your_openrouter_api_key
COHERE_API_KEY=your_cohere_api_key

# Optional tracing
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=destination-agent
```

Notes:

- Destination requires Anthropic and Geoapify access for its full external-data workflow.
- Flights uses Travelpayouts and OpenRouter configuration.
- Money & Customs uses Cohere for the Deep Agent; Frankfurter exchange-rate access does not require a key.
- LangSmith is optional and used for tracing when configured.

---

## Setup

### 1. Create and activate a virtual environment

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install shared dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy or create a local `.env` file using `.env.example` as a reference, then provide the required API keys. Do not commit `.env`.

---

## Running Individual Agents

### Destination Agent

```bash
python -m destination_agent.destination_agent
```

### Flights Agent

```bash
python flights_agent.py
```

### Money & Customs Agent

The Orchestrator imports and calls:

```python
answer(task: str) -> str
```

from the Money & Customs agent module.

---

## Running the Integrated UI

From the project root, after dependencies and environment variables are configured:

```bash
chainlit run app.py -w
```

Additional setup and UI instructions are documented in:

```text
RUNNING_THE_UI.md
```

---

## Failure Handling

The system is designed to degrade gracefully when an individual agent is unavailable. Instead of crashing the entire workflow, the Orchestrator can preserve the available agent results and surface the unavailable component clearly.

This supports independent sub-agent development and improves demo reliability.

---

## Known Limitations

### Destination

- Recommendation quality depends on the current shared destination corpus.
- Some destination information depends on external API availability.
- Low-confidence retrieval may require user clarification before a destination is handed downstream.

### Flights

- Flight-price data are cached rather than guaranteed live booking availability.
- Some routes may have limited or unavailable Travelpayouts data.

### Money & Customs

- Curated customs data currently cover 22 countries.
- National income context is country-level rather than city-level.
- City-to-country resolution is partly dependent on agent reasoning.
- Tool confidence metadata is not currently propagated directly into Orchestrator decisions.

### Orchestration

- The current integration primarily uses plain-text task/response contracts.
- Flights still uses a compatibility adapter for its current sub-agent specification.
- SLIM/A2A transport is designed but not currently used for the local demo.
- External API availability and API-key configuration can affect individual agent responses.

---

## Reduced-System Scope

This branch intentionally contains the reduced system used for the current demo and integration work:

```text
Destination
+
Flights
+
Money & Customs
+
Orchestrator
```

The original full multi-agent system is preserved separately under:

```text
v1.0-full-system
```

The reduced configuration provides a clearer demonstration of multi-agent specialization, RAG retrieval, tool use, external API integration, local agent orchestration, and graceful failure handling.

---

## Supporting Documentation

For more detail, see:

- `destination_agent/README.md` — Destination Agent implementation and data workflow
- `FLIGHTS_AGENT_README.md` — Flights Agent tools, scope, and testing
- `money&customs_agent/README.md` — Money & Customs tools, confidence logic, and limitations
- `ORCHESTRATOR_DESIGN.md` — Orchestrator design notes and open architectural decisions
- `RUNNING_THE_UI.md` — UI startup and environment instructions
- `HANDOFF.md` — integration and handoff notes

---

## Contributors

| Component             | Contributor(s)   |
|-----------------------|------------------|
| Destination Agent     | Joel & Alice     |
| Flights Agent         | Brinda           |
| Money & Customs Agent | Emily            |
| Orchestrator          | Team Integration |
