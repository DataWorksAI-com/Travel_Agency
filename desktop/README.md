# Travel Agency desktop - local project edition

Windows per-user installer and native launcher for the existing whole-project
Chainlit entry point, `app.py`. Does not use `transportation_chat.py`.

## Build

Requires Windows and the .NET Framework C# compiler included on this machine:

```powershell
.\desktop\build.ps1 -OutputDirectory C:\path\to\output
```

The installer embeds only the compiled launcher and the suggested project path.
It does not embed `.env`, API credentials, Python, dependencies or project data.
This is a local project launcher, not a standalone distributable of the backend.

## Install and use

Run `TravelAgency-Setup.exe`, confirm the existing project folder, then Install.
No administrator privileges are requested. The installer creates Desktop and
Start menu shortcuts and a Windows Installed Apps uninstall entry.

The launcher defaults to Local LLM mode using LM Studio's loopback-compatible
API. Destination, Flights and Money & Customs all use the selected local model;
there is no cloud LLM fallback. The other three sections stay labelled sample
data. A separate Demo option uses sample data for all six sections. The main
orchestrator remains the deterministic pipeline. The optional model-based
orchestrator also respects local-model configuration when run separately.

Install `desktop/requirements.txt` in the existing virtual environment. Local
settings default to `http://127.0.0.1:1234/v1` and `qwen3-8b`; they can be changed
in the launcher and are saved in `local-settings.txt` beside the executable.
The preparation helper starts the LM Studio server if needed and loads the
selected already-downloaded model at 16,384 context tokens. It does not download
models. A failed local connection never switches to a cloud LLM. External
LangSmith tracing is disabled for local inference. The model transport ignores
proxy environment variables and rejects non-loopback LLM endpoints.

No LLM API key is needed. Existing travel-data API keys still apply. Tool calls
for flights, weather, exchange rates and other travel data can use the internet.
Local inference does not imply the entire travel app works offline.

Click Start app. A local Python service starts on a dynamically chosen loopback
port. Once HTTP responds successfully, Edge opens it in a dedicated app window
with a separate local profile. Keep the launcher open; Stop or closing it
terminates its owned backend process tree. Closing the planning window alone
does not stop the backend; Open window reopens it. Stop before uninstalling.

Prerequisites: existing `.venv`, its original base Python installation, Microsoft
Edge, LM Studio with a downloaded tool-capable chat model, and the existing
project directory. Travel data needs network access, agent-specific data and
any relevant data API keys. Moving the project requires
running Setup again. Uninstall preserves the source project, credentials and
local logs/browser profile, and removes only installer-owned application files
and shortcuts.

## Verification

`TravelAgency-Setup.exe --extract-test <directory>` exercises embedded payload
extraction without installation, shortcuts or registry writes.

The extracted `TravelAgency.exe --smoke-test` starts `app.py` in demo mode,
waits for HTTP 200, stops its backend and writes `smoke-test.txt` beside itself.
This test makes no LLM request. Logs stay in the test folder. Normal logs and
the dedicated Edge profile live under `%LOCALAPPDATA%\TravelAgencyDesktop`.
`--smoke-test-local` also prepares LM Studio before starting the main UI.
`python -m unittest desktop.test_local_llm -v` checks local endpoint guardrails.
`python -m desktop.verify_local` makes a real local LLM/tool round trip using
clearly fictional test data. These tests do not validate a completed itinerary.
