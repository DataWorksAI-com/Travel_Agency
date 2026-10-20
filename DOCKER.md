# Docker setup (CPU; runtime verification pending)

This Compose configuration is intended to provide one Linux-container workflow
for Windows, macOS and Ubuntu. It runs llama.cpp and the English Chainlit UI,
with no Windows executables or bundled desktop browser. The Windows installer
remains an optional distribution method.

## Prerequisites

- Docker Desktop with Linux containers on Windows/macOS, or Docker Engine with
  the Compose plugin on Ubuntu.
- A Qwen3-8B-Q4_K_M.gguf model file obtained from its publisher. The existing
  Windows installation has it in its models directory; it can be reused.
- Sufficient memory allocated to Docker for Qwen3-8B and the application.
  Start with at least 12 GB available to Docker; memory needs vary. Do not run
  another copy of the model concurrently on a memory-constrained machine.
- Internet access for the initial image pull and Python dependency installation.

## Start

1. In the repository root, create a directory named `models`.
2. Place `Qwen3-8B-Q4_K_M.gguf` inside it. Do not commit model files to Git.
3. Run these commands from the repository root:

```sh
docker compose config
docker compose up --build
```

Open http://localhost:8000 after the model and web app are ready. Model loading
and the first dependency build can take several minutes. Stop with
`docker compose down`. Check failures with `docker compose logs model web`.

The model directory is mounted read-only. The model and web services share a
network namespace so the existing loopback-only inference guard remains intact.
Only the web port is published, bound to the host's loopback interface. The model
API is not published. Do not change the local endpoint to a Docker service name.

## Current scope

CPU inference is the portable baseline. This is not a GPU configuration; Apple
Metal, CUDA and Vulkan support require separate host-specific work and testing.
Do not assume equal performance on all hosts or CPU architectures. The server
image currently uses the upstream `server` tag; pin a tested digest before a
reproducible release. Application dependencies also include existing unpinned
requirements, so this is not yet a locked release environment.

The default configuration uses bundled destination data and unverified model
guidance. Restaurant recommendations are unavailable; Activities and Budget are
sample modules. Travel-data calls may require internet. Optional data credentials
can be added to the web service environment locally; never commit real secrets.
Chroma may download embedding assets on first use; Docker is not an entirely
offline distribution on its first run. Each chat message is planned independently.

## Validation status

The authoring machine does not have Docker installed. Python syntax, Compose YAML
structure and the existing 11 regression tests were checked; no image build or
container runtime success is claimed. Before treating Docker as the team's main
setup, test `docker compose up --build` on Windows, macOS (including Apple Silicon)
and Ubuntu. Verify an English UI, a local model/tool round trip, an uncovered
city introduction, a restaurant refusal, and clean shutdown on each target.

References:
- https://docs.docker.com/compose/install/
- https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md
