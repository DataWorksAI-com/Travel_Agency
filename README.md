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

## External Services and APIs

The system combines local retrieval with several external services. Some require API keys and some can be used without authentication.

| Service | Used By | What It Provides | API Key Required? | Where to Get Access / Documentation |
|---|---|---|---|---|
| **Anthropic Claude** | Destination Agent | LLM reasoning and tool-calling for destination lookup and recommendation | Yes | https://console.anthropic.com/settings/keys |
| **Geoapify Geocoding API** | Destination Agent | Resolves destination names to geographic coordinates and structured location information | Yes | https://myprojects.geoapify.com/ |
| **Geoapify Places API** | Destination Agent | Returns destination POIs and travel features such as beaches, attractions, nature areas, and diving locations | Yes | https://apidocs.geoapify.com/docs/places/ |
| **Open-Meteo** | Destination Agent | Location/geocoding and climate or historical weather data used for destination context | No key for normal public access | https://open-meteo.com/en/docs |
| **Nager.Date** | Destination Agent | Public-holiday data by year and country | No | https://date.nager.at/Api |
| **ChromaDB** | Destination and Money & Customs | Local vector database used for semantic retrieval | No | https://docs.trychroma.com/ |
| **Travelpayouts** | Flights Agent | Cached flight-price and route data | Yes | https://support.travelpayouts.com/hc/en-us/articles/13024069738386-Where-to-find-API-token |
| **OpenRouter** | Flights Agent | LLM access used by the Flights Agent | Yes | https://openrouter.ai/settings/keys |
| **Cohere** | Money & Customs Agent | LLM used by the Deep Agent | Yes | https://dashboard.cohere.com/api-keys |
| **Frankfurter** | Money & Customs Agent | Current and historical currency exchange rates | No | https://frankfurter.dev/ |
| **World Bank Indicators API** | Money & Customs Agent | Country-level economic context, including GNI-per-capita data used as a rough price-scale reference | No | https://datahelpdesk.worldbank.org/knowledgebase/articles/889392 |
| **LangSmith** | Optional tracing | Tracing and debugging of agent/tool calls | Optional | https://smith.langchain.com/ |

### What each required API key is for

#### `ANTHROPIC_API_KEY`

Used by the **Destination Agent** to access Claude for reasoning and tool use.

To obtain a key:

1. Go to https://console.anthropic.com/.
2. Sign in or create an Anthropic account.
3. Open **Settings / API Keys**.
4. Create a new API key.
5. Copy the key and store it in the root `.env` file as:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
```

Do not paste a real key into GitHub, Slack, screenshots, or the README.

#### `GEOAPIFY_API_KEY`

Used by the **Destination Agent** for destination geocoding and place/POI retrieval.

Geoapify data in this project is used to help resolve destinations and enrich them with travel-related places such as attractions, beaches, nature areas, and diving locations.

To obtain a key:

1. Go to https://myprojects.geoapify.com/.
2. Create a Geoapify account or sign in.
3. Create a project.
4. Open the project's **API Keys** section.
5. Copy the generated API key.
6. Add it to `.env`:

```env
GEOAPIFY_API_KEY=your_geoapify_api_key
```

#### `TRAVELPAYOUTS_TOKEN`

Used by the **Flights Agent** to query Travelpayouts flight-price data.

The flight data are useful for travel recommendations, but they are cached price data and should not be treated as guaranteed live booking availability.

To obtain the token:

1. Go to https://www.travelpayouts.com/ and create an account.
2. Log in.
3. Open your **Profile**.
4. Open the **API token** tab.
5. Copy your token.
6. Add it to `.env`:

```env
TRAVELPAYOUTS_TOKEN=your_travelpayouts_token
```

#### `OPENROUTER_API_KEY`

Used by the **Flights Agent** for LLM access.

To obtain a key:

1. Go to https://openrouter.ai/.
2. Sign in.
3. Open https://openrouter.ai/settings/keys.
4. Create a new API key.
5. Copy the key into `.env`:

```env
OPENROUTER_API_KEY=your_openrouter_api_key
```

#### `COHERE_API_KEY`

Used by the **Money & Customs Agent** for its Deep Agent / LLM reasoning.

To obtain a key:

1. Go to https://dashboard.cohere.com/api-keys.
2. Sign in or create a Cohere account.
3. Create or copy an API key.
4. Add it to `.env`:

```env
COHERE_API_KEY=your_cohere_api_key
```

#### `LANGSMITH_API_KEY` — optional

LangSmith is used only for tracing/debugging when tracing is enabled. The system can be run without LangSmith if tracing is not needed.

1. Go to https://smith.langchain.com/.
2. Sign in.
3. Open the LangSmith settings and create an API key.
4. Add the following values to `.env`:

```env
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=travel-agency-ui
```

If you are not using LangSmith, omit these variables or set tracing to `false`.

---

## Environment Variables

All secret keys should be stored locally in a root `.env` file. **Never commit `.env` to Git.**

A complete example for the reduced three-agent system is:

```env
# Destination Agent
ANTHROPIC_API_KEY=your_anthropic_api_key
GEOAPIFY_API_KEY=your_geoapify_api_key

# Flights Agent
TRAVELPAYOUTS_TOKEN=your_travelpayouts_token
OPENROUTER_API_KEY=your_openrouter_api_key

# Money & Customs Agent
COHERE_API_KEY=your_cohere_api_key

# Optional LangSmith tracing
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=travel-agency-ui
```

The following services do **not** require a project API key for the way they are used here:

- Open-Meteo
- Nager.Date
- Frankfurter
- World Bank Indicators API
- ChromaDB, because it runs locally

---

## Setup: Step-by-Step for a New User

The steps below assume the user is starting with a new computer and has not run the project before.

### 0. Prerequisites

Install the following before starting:

1. **Python 3.11**
   - Download: https://www.python.org/downloads/
   - During Windows installation, select **Add Python to PATH**.

2. **Git**
   - Download: https://git-scm.com/downloads

3. **VS Code** — optional but recommended
   - Download: https://code.visualstudio.com/

Verify Python and Git from PowerShell:

```powershell
python --version
git --version
```

Expected Python output should begin with:

```text
Python 3.11
```

### 1. Clone the repository

Open PowerShell and run:

```powershell
git clone https://github.com/DataWorksAI-com/Travel_Agency.git
cd Travel_Agency
```

The current reduced system is on the `subset_dest_flights_money_orch` branch. Switch to it:

```powershell
git fetch origin
git switch subset_dest_flights_money_orch
git pull origin subset_dest_flights_money_orch
```

Confirm the current branch:

```powershell
git branch --show-current
```

Expected output:

```text
subset_dest_flights_money_orch
```

### 2. Create a Python virtual environment

From the project root:

```powershell
python -m venv .venv
```

This creates an isolated Python environment inside the `.venv` folder so the project's packages do not interfere with packages installed for other projects.

### 3. Activate the virtual environment

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

After activation, the terminal should begin with something similar to:

```text
(.venv) PS C:\...\Travel_Agency>
```

If PowerShell blocks the activation script, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 4. Upgrade `pip`

```powershell
python -m pip install --upgrade pip
```

### 5. Install all shared dependencies

From the repository root:

```powershell
pip install -r requirements.txt
```

This installs the packages needed by the three agents and the Chainlit UI.

Optional verification:

```powershell
python -c "import chainlit, chromadb, langchain; print('Core dependencies imported successfully')"
```

Expected output:

```text
Core dependencies imported successfully
```

### 6. Create the `.env` file

The repository contains `.env.example`, which lists the environment-variable names without real secrets.

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux:

```bash
cp .env.example .env
```

Open `.env` in VS Code or another text editor and replace placeholder values with your own API keys.

Example:

```env
ANTHROPIC_API_KEY=your_real_key_here
GEOAPIFY_API_KEY=your_real_key_here
TRAVELPAYOUTS_TOKEN=your_real_token_here
OPENROUTER_API_KEY=your_real_key_here
COHERE_API_KEY=your_real_key_here
```

Do **not** add quotation marks unless a provider specifically requires them.

### 7. Verify that required keys are visible

This command only prints whether each variable exists; it does **not** print the secret values.

```powershell
python -c "from dotenv import load_dotenv; import os; load_dotenv(); keys=['ANTHROPIC_API_KEY','GEOAPIFY_API_KEY','TRAVELPAYOUTS_TOKEN','OPENROUTER_API_KEY','COHERE_API_KEY']; [print(k, 'SET' if os.getenv(k) else 'MISSING') for k in keys]"
```

Expected result:

```text
ANTHROPIC_API_KEY SET
GEOAPIFY_API_KEY SET
TRAVELPAYOUTS_TOKEN SET
OPENROUTER_API_KEY SET
COHERE_API_KEY SET
```

If a variable shows `MISSING`, reopen `.env`, confirm the spelling, save the file, and run the check again.

### 8. Optional: enable LangSmith tracing

If you have a LangSmith key, add:

```env
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=travel-agency-ui
```

LangSmith is optional and is mainly useful for inspecting model/tool traces while debugging.

---

## Running and Testing Individual Agents

Run all commands below from the project root unless a step explicitly says otherwise.

### 1. Destination Agent

Run:

```powershell
python -m destination_agent.destination_agent
```

The Destination Agent can:

- resolve a named destination,
- retrieve destination/POI evidence,
- return climate and holiday context,
- or recommend one destination from user preferences.

Run its test suites:

```powershell
python -m destination_agent.test_destination_agent
python -m destination_agent.test_geoapify_data
```

Example request handled by this agent:

```text
Tell me about Aruba.
```

or:

```text
I want a tropical destination with beaches and diving.
```

If this agent fails with an authentication error, first check `ANTHROPIC_API_KEY` and `GEOAPIFY_API_KEY`.

### 2. Flights Agent

Run:

```powershell
python flights_agent.py
```

The built-in test prints the agent message trace, including tool calls and the final response.

The Flights Agent expects city names and resolves airport codes internally.

Example task:

```text
Find a flight from Boston to Paris under $700.
```

If no flights are returned, this does not always mean the code is broken. Travelpayouts coverage varies by route, and the project uses cached price data rather than guaranteed live booking inventory.

If the agent reports authentication problems, check:

```env
TRAVELPAYOUTS_TOKEN=...
OPENROUTER_API_KEY=...
```

### 3. Money & Customs Agent

The Money & Customs component is normally called by the Orchestrator through:

```python
answer(task: str) -> str
```

To test it manually from PowerShell, run:

```powershell
cd "money&customs_agent"
python -c "from dotenv import load_dotenv; load_dotenv('../.env'); from money_customs_agent import answer; print(answer('What are the exchange rate and tipping customs for France?'))"
cd ..
```

This agent combines:

- exchange-rate data from Frankfurter,
- curated tipping/haggling knowledge,
- semantic fallback retrieval through ChromaDB,
- and World Bank country-level economic context.

If the Cohere request returns `401 Unauthorized`, check that `COHERE_API_KEY` is current and valid.

---

## Running the Integrated 3-Agent UI

After the individual agents have been tested, run the complete reduced system.

### 1. Make sure the virtual environment is active

The PowerShell prompt should begin with:

```text
(.venv)
```

If it does not, activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 2. Select the real reduced-system agents

In PowerShell:

```powershell
$env:TRAVEL_UI_ORCHESTRATOR = "agent"
$env:TRAVEL_UI_AGENTS = "destination=real,flights=real,money_customs=real"
```

These settings tell the UI to use the real Destination, Flights, and Money & Customs agents.

### 3. Start Chainlit

```powershell
chainlit run app.py -w
```

Chainlit will print a local URL in the terminal. Open that address in a browser. It is commonly:

```text
http://localhost:8000
```

### 4. Try an end-to-end request

Example:

```text
Plan a 7-day trip from Boston to Paris.
Include destination information, flight options,
exchange-rate information, and local tipping customs.
```

A successful run should show the Orchestrator calling the relevant specialized agents and assembling their results into one response.

### 5. Stop the UI

Return to the terminal and press:

```text
Ctrl + C
```

For additional UI notes, see:

```text
RUNNING_THE_UI.md
```

---

## Common Setup Problems

### `python` is not recognized

Python is either not installed or was not added to `PATH`.

Reinstall Python 3.11 and select **Add Python to PATH**, then reopen PowerShell.

### PowerShell cannot run `Activate.ps1`

Run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate the environment again:

```powershell
.\.venv\Scripts\Activate.ps1
```

### `ModuleNotFoundError`

Confirm the virtual environment is active, then reinstall dependencies:

```powershell
pip install -r requirements.txt
```

### API returns `401 Unauthorized`

The API key/token is missing, expired, revoked, or incorrect.

Check the matching variable in `.env`, but never print or share the full key publicly.

### Agent returns no result

A valid "no data" result is different from a software failure. For example, Travelpayouts may have no cached fare for a particular route, and a retrieval agent may intentionally decline to answer when confidence is too low.

### Changes to `.env` are not taking effect

Stop the running UI with `Ctrl + C`, save `.env`, and restart:

```powershell
chainlit run app.py -w
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
