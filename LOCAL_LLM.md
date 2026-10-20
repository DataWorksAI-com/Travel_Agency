# Local Qwen integration

This branch adds optional local inference and English Windows standalone packaging.
No model weights, installers, personal credentials or virtual environments are committed.

## Docker setup

See [DOCKER.md](DOCKER.md) for the proposed cross-platform CPU Compose setup.
Build and live model checks passed on Windows Docker Desktop (Linux/amd64).
Native macOS and Ubuntu host acceptance tests remain pending.

## Run from source

Install the existing project dependencies and `desktop/requirements.txt`.
Load Qwen3 in LM Studio and start its local OpenAI-compatible server.
Set these environment variables before running `python -m chainlit run app.py`:

```powershell
$env:TRAVEL_LLM_PROVIDER = "local"
$env:TRAVEL_LOCAL_BASE_URL = "http://127.0.0.1:1234/v1"
$env:TRAVEL_LOCAL_MODEL = "qwen3-8b"
$env:TRAVEL_STANDALONE = "1"
$env:TRAVEL_UI_ORCHESTRATOR = "pipeline"
$env:TRAVEL_UI_AGENTS = "destination=real,flights=real,money_customs=real,restaurants=dummy,activities=dummy,budget=dummy"
```

Use the model identifier actually served by your local endpoint.
Local mode allows only loopback URLs and does not fall back to a hosted LLM.
Travel-data services may still require internet and optional API credentials.

## Behavior and limitations

Named-place introductions use the destination snapshot first. Missing places
receive explicitly unverified model guidance, which can contain factual errors.
Standalone restaurant requests return unavailable instead of fabricated venues;
restaurant samples are blocked in the itinerary pipeline. Activities and Budget
remain samples; flight prices require travel-data credentials. The UI is English.
Each chat message is planned independently.

## Tests and packaging

Run `python -m unittest desktop.test_dining_policy desktop.test_bundled_data desktop.test_local_llm`.
See `desktop/STANDALONE.md` for Windows build inputs and commands.
The 1.0.1 package passed its local model/tool round trip, English UI and bundled
browser checks. A clean-machine Windows installation test has not been performed.
