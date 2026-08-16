# Destination Expert Agent

## Purpose

The Destination Expert Agent is part of a multi-agent travel planning system.

It supports two main use cases:

1. Providing grounded information about a specific destination.
2. Recommending one destination based on user travel preferences.

The agent combines shared RAG retrieval, Geoapify travel data, climate data, and public holiday information.

---

## Current Features

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
- Tool calling with Deep Agents
- Claude-based reasoning
- LangSmith tracing
- Agent and Geoapify test jigs

---

## Agent Workflow

### Case 1 - Specific Destination

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

### Case 2 - Destination Recommendation

When the user provides travel preferences without selecting a destination, the agent:

1. Searches the shared destination RAG corpus.
2. Retrieves a shortlist of candidate destinations.
3. Enriches candidates with Geoapify travel features and places.
4. Compares candidates using explicit retrieved evidence.
5. Selects exactly one Recommended Destination.
6. Retrieves detailed climate and holiday information for the selected destination.
7. Optionally displays up to two alternatives.

The RAG match_score is treated only as semantic retrieval evidence and not as a destination-quality score.

### Low-Confidence Retrieval

If the current shared corpus does not contain a strong semantic match for all user preferences, the agent returns a retrieval limitation instead of forcing a recommendation.

Example behavior:

```text
Retrieval Note:
The current shared destination corpus does not contain a strong match
for all stated preferences.

Closest Retrieved Options:
- Destination A: supported preferences
- Destination B: supported preferences
- Destination C: supported preferences

Question:
Which of your stated preferences is most important to prioritize?
```
In this case, no destination is handed to downstream agents until the user clarifies the preference priority.

## Knowledge Source

### Shared Destination RAG

The Destination Agent uses a shared ChromaDB-based destination corpus.

The corpus contains:

Original destination descriptions
Geoapify travel features
Geoapify place examples
Dynamically added destinations

The retrieval layer uses the rag_text field when available and falls back to the original description field.

### Geoapify

Geoapify is used for:

Destination geocoding
Destination boundary information
Beaches
Tourist attractions
Nature reserves
Diving locations

Geoapify destination profiles are cached in:

destination_profiles.json

The cache reduces repeated API calls and improves demo reliability.

If a destination is not cached, the system automatically:

1. Geocodes the destination.
2. Searches relevant Geoapify place categories.
3. Builds a structured travel profile.
4. Saves the profile to the local cache.

### Climate and Public Holidays

The Destination Agent also uses the shared destination data layer for:

Historical climate information
Best and avoid months
Public holiday information

Unavailable climate or holiday information is handled gracefully.

### Dynamic Corpus Expansion

The shared RAG corpus can grow over time.

When a user requests information about a valid destination that is not already in the shared corpus:

```text
Named destination request
        ↓
Resolve destination
        ↓
Build/load Geoapify profile
        ↓
Validate destination data
        ↓
Add destination to shared corpus
        ↓
Available for future RAG retrieval
```

This allows named-destination lookups to support destinations outside the original curated corpus while gradually expanding future recommendation coverage.

## Requirements
- Python 3.11
- Anthropic API key
- Geoapify API key
- LangSmith API key
- ChromaDB

## Setup

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies:

```bash
pip install deepagents langchain-anthropic python-dotenv requests truststore chromadb
```

### 3. Create a `.env` file:

```env 
ANTHROPIC_API_KEY=your_anthropic_api_key
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=destination-agent
GEOAPIFY_API_KEY=your_geoapify_api_key
```
Do not commit your `.env` file or real API keys to Git.

## Run the Agent

From the project root:

```bash
python -m destination_agent.destination_agent
```

## Run Tests

### Destination Agent tests

```bash
python -m destination_agent.test_destination_agent
```

### Geoapify tests

```bash
python -m destination_agent.test_geoapify_data
```

## Example

### Specific destination

```text
Input:
Tell me about Aruba.

Output format:

Destination: Aruba
Travel Features: ...
Climate: ...
Public Holidays: ...
```

### Preference recommendation

```text
Input:
I want a tropical destination with beaches and diving.

Output format:

Recommended Destination: <one destination>
Reason: <retrieved evidence>
Matched Preferences: <supported preferences>
Climate: <available information>
Public Holidays: <available information>
Alternatives Considered: <optional alternatives>
```

```markdown
## Project Structure

```text
Capstone/
├── destination_agent/
│   ├── __init__.py
│   ├── destination_agent.py
│   ├── geoapify_data.py
│   ├── destination_profiles.json
│   ├── enrich_rag_corpus.py
│   ├── expand_rag_corpus.py
│   ├── test_destination_agent.py
│   ├── test_geoapify_data.py
│   └── README.md
│
└── destination_data/
    ├── recommend.py
    ├── resolve_place.py
    ├── climate.py
    ├── holidays.py
    ├── destinations.json
    └── ...
```

## Main Files

```markdown
- `destination_agent.py`: Destination Expert Agent, tool definitions, routing, ranking, and response generation.
- `geoapify_data.py`: Geoapify geocoding, place retrieval, profile generation, and local caching.
- `destination_profiles.json`: Cached Geoapify destination profiles used to reduce repeated API calls.
- `enrich_rag_corpus.py`: One-time enrichment utility used to add Geoapify travel features and POIs to the shared destination corpus. The repository already contains the enriched corpus, so this script is not required during normal startup.
- `expand_rag_corpus.py`: Adds newly requested valid destinations to the shared destination corpus.
- `test_destination_agent.py`: Tests Case 1, Case 2, low-confidence handling, and response rules.
- `test_geoapify_data.py`: Tests Geoapify geocoding, destination profiles, cache behavior, and graceful failure.
- `destination_data/destinations.json`: Shared destination corpus used by ChromaDB retrieval.
- `destination_data/recommend.py`: Shared RAG retrieval logic. Uses `rag_text` when available and falls back to `description`.
```
```