"""Prepare LM Studio without downloading models or changing cloud keys."""

import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_llm import local_settings


def models(base: str):
    with build_opener(ProxyHandler({})).open(base + "/models", timeout=5) as response:
        return json.load(response).get("data", [])


def ensure():
    base, selected = local_settings()
    cli = Path.home() / ".lmstudio" / "bin" / "lms.exe"
    try:
        available = models(base)
    except (URLError, TimeoutError, OSError):
        if not cli.is_file():
            raise RuntimeError("Start the LM Studio local server, then try again.")
        port = urlparse(base).port or 80
        subprocess.run([str(cli), "server", "start", "--port", str(port)], check=True, timeout=90)
        available = models(base)
    if not any(item.get("id") == selected for item in available):
        raise RuntimeError(f"Local model '{selected}' is not available. Download or load it in LM Studio, or choose its model identifier in the launcher.")
    # LM Studio can list downloaded-but-unloaded models. Load the selected
    # model explicitly if this CLI is available; never select another model.
    if cli.is_file():
        with build_opener(ProxyHandler({})).open(base.replace("/v1", "/api/v0/models"), timeout=5) as response:
            detail = json.load(response).get("data", [])
        loaded = any(item.get("id") == selected and item.get("state") == "loaded" for item in detail)
        if not loaded:
            subprocess.run([str(cli), "load", selected, "--identifier", selected, "--context-length", "16384", "--yes", "--quiet"], check=True, timeout=180)
    print(f"Local model ready: {selected} at {base}")


if __name__ == "__main__":
    try:
        ensure()
    except Exception as error:
        # No provider keys are read, logged or requested by this helper.
        print(f"Local model setup failed: {error}", file=sys.stderr)
        sys.exit(1)
