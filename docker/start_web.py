"""Wait for the model on shared loopback, then run the Linux web server."""
import os
from pathlib import Path
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


def main():
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 300
    while True:
        try:
            with opener.open("http://127.0.0.1:8080/health", timeout=3) as response:
                if response.status == 200:
                    break
        except (URLError, OSError):
            pass
        if time.monotonic() >= deadline:
            raise SystemExit("Model did not become ready. Check docker compose logs model and the GGUF mount.")
        time.sleep(1)
    config = Path(".chainlit")
    config.mkdir(exist_ok=True)
    (config / "config.toml").write_text(
        '[project]\nuser_env=[]\n[UI]\nname="Travel Agency"\nlanguage="en-US"\n[meta]\ngenerated_by="2.11.0"\n',
        encoding="utf-8",
    )
    os.execv(sys.executable, [sys.executable, "-m", "chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000", "--headless"])


if __name__ == "__main__":
    main()
