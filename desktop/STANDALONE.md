# Complete Windows standalone build

This target is separate from the older desktop launcher that pointed to an
existing project folder. It includes its own embedded Python, site-packages,
app source, embedding weights, Qwen3 GGUF, llama.cpp and Firefox. It does not
start or contact LM Studio and does not need system Python, pip or Edge.

## Build inputs

- Python 3.13.5 Windows x64 embeddable distribution from python.org.
- The tested `.venv/Lib/site-packages` snapshot, including license metadata.
- Qwen3-8B-Q4_K_M.gguf, downloaded from lmstudio-community/Qwen3-8B-GGUF.
- llama.cpp b11669 Windows CPU and Vulkan distributions from ggml-org.
- Playwright Firefox revision 1555, from the official Playwright CDN.
- Chroma's cached all-MiniLM-L6-v2 ONNX files, copied into assets/embedding/onnx.
- App-local Microsoft Visual C++ runtime DLLs.
- Component license texts in the downloads/licenses directory.
- Inno Setup 7.1.0 compiler and the Windows .NET Framework C# compiler.

The build script only copies the selected application modules and public data.
It excludes .env files, chat uploads, local Chroma databases and LM Studio
credentials. It does not copy the developer's virtual environment launcher.
The embedded interpreter uses an explicit relative python313._pth file.

```powershell
.\.venv\Scripts\python.exe desktop\build_standalone.py --stage C:\build\stage --downloads C:\build\downloads
ISCC.exe --define=StageDir=C:\build\stage --define=OutputDir=C:\build\release desktop\standalone.iss
```

Distribute every generated .bin slice with the setup executable. The complete
ZIP is the transport artifact; recipients extract it and run Setup. Never send
only the small setup executable. Disk spanning is required because the bundled
model exceeds the installer's single-executable data limit.

## Runtime

The native launcher runs runtime/python.exe in isolated mode. The Python
supervisor starts a bundled llama-server on an ephemeral loopback port, waits
for readiness, then starts the existing whole-project app.py and bundled
Firefox. A Windows kill-on-close job owns the service process tree.

CPU mode is the default. GPU mode is optional and requires Vulkan support.
No inference fallback to cloud models exists. Normal travel tools can still
use external data services. Each recipient supplies their own optional data
API credentials in LocalAppData/TravelAgencyStandalone/data-services.env.
Without Geoapify, destination lookup uses the bundled public snapshot. Missing
flight credentials are reported instead of producing a quote. Restaurants,
Activities and Budget remain the existing explicitly labelled sample sections.

## Validation

Run the installed TravelAgency.exe --self-test. It launches the bundled CPU
model and performs a model/tool/result round trip; starts the UI and requests
English translations using a Chinese locale query; starts the bundled browser;
then stops its services. Python external socket connections are blocked during
this test. It saves self-test-data/self-test.json beside the executable.

A browser process or screenshot alone is not sufficient evidence of a working
chat. Also use the matching Playwright Firefox client to wait for the visible
Travel Planning Assistant welcome, submit a demo request through #chat-input
and #chat-submit, and wait for the sample itinerary. Verify the installed
directory, not only the staging directory. Compare the installed dependency
tree with the staged files; packaging exclusions must not accidentally remove
library subdirectories named models.

Target: Windows 10 2004+ / Windows 11 x64. Plan for at least 16 GB RAM
(32 GB recommended) and about 20 GB available disk for archive, extracted
installer and installed files. No clean-machine VM is included in this build
environment; a separate-machine acceptance run remains useful.
