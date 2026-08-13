# Destination Expert Agent

## Purpose
The Destination Expert Agent is part of a multi-agent travel planning system.

It helps identify a tropical destination based on user travel preferences and can also provide basic information about a specific destination.

## Current Features
- Destination information lookup
- Preference-based destination search
- Multi-preference matching
- Geoapify Geocoding and Places API integration
- Automatic destination profile generation
- Local JSON caching for previously retrieved destinations
- Tool calling with Deep Agents
- Claude-based reasoning
- LangSmith tracing
- Basic test jig with expected answers

## Current Knowledge Source

The Destination Expert Agent currently uses the Geoapify Geocoding and Places APIs to retrieve travel-oriented destination information.

The agent collects information such as:
- Beaches
- Tourist attractions
- Nature reserves
- Diving locations

Destination profiles are stored in a local JSON cache (`destination_profiles.json`).

If a requested destination is not already cached, the system automatically:
1. Geocodes the destination using Geoapify.
2. Retrieves relevant travel places.
3. Builds a structured destination profile.
4. Saves the profile to the local cache for future use.

Future work may extend the destination knowledge layer with vector-based retrieval and RAG.

## Requirements
- Python 3.11
- Anthropic API key
- LangSmith API key
- Geoapify API key

## Setup

### 1. Create and activate a virtual environment
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies:
```bash
pip install deepagents langchain-anthropic python-dotenv requests
```

### 3. Create a .env file:
```env 
ANTHROPIC_API_KEY=your_anthropic_api_key
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=destination-agent
GEOAPIFY_API_KEY=your_geoapify_api_key
```
Do not commit your .env file or real API keys to Git.

### 4. Run the Agent
```bash
python destination_agent.py
```

### 5. Run Tests
```bash
python test_destination_agent.py
```

### 6. Example
```text
Input:
Tell me about Barbados.

Example output:
First request for a new destination:

No cached profile found for Barbados.
Building new profile for Barbados...
Saved new destination profile for Barbados.

Subsequent request:

Using cached profile for Barbados

DESTINATION AGENT RESPONSE:

**Barbados**

Barbados is a tropical destination offering a diverse range of features for travelers:

**Beaches:**
- Sandy Lane Beach
- Rockley Beach
- Lakes Beach
- Batts Rock Beach
- Skeetes Bay Beach

**Attractions:**
- Rihanna's Childhood Home
- Malibu Beach Club (Cockspur)
- Tyrol Cot Village
- Hackletons Cliff
- Gallery of Caribbean Art; Courts

**Nature:**
- Graeme Hall Nature Sanctuary

**Diving:**
- Barbados Blue
- Spearfishing & Freediving Barbados
```

```text
Input:
I want a tropical destination with beaches and diving.

Example output:
Recommended destinations may include Aruba, Barbados, Saint Lucia, or Curacao,
depending on the destination profiles currently available in the knowledge cache.
```

## Project Structure

```text
destination_agent/
├── destination_agent.py
├── destination_data.py
├── destination_profiles.json
├── test_destination_agent.py
├── test_geoapify.py
└── README.md
```

```markdown
- `destination_agent.py`: Deep Agent and destination tools
- `destination_data.py`: Geoapify retrieval, profile generation, and caching
- `destination_profiles.json`: Cached destination knowledge
- `test_destination_agent.py`: Agent test jig
- `test_destination_data.py`: Geoapify API testing
```