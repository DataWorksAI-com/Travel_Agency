"""Assemble a relocatable, credential-free Windows distribution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".env", "*.env", ".git", "chroma_db", "chroma_db_offline", ".files", "destination_profiles.json")


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size == source.stat().st_size and destination.stat().st_mtime >= source.stat().st_mtime:
        return
    shutil.copy2(source, destination)


def extract_once(archive, target, marker):
    if not (target / marker).exists():
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as source:
            source.extractall(target)


def build(args):
    stage = args.stage.resolve()
    downloads = args.downloads.resolve()
    stage.mkdir(parents=True, exist_ok=True)
    runtime = stage / "runtime"
    extract_once(downloads / "python.zip", runtime, "python.exe")
    shutil.copytree(PROJECT / ".venv" / "Lib" / "site-packages", runtime / "Lib" / "site-packages", dirs_exist_ok=True, ignore=IGNORE)
    (runtime / "python313._pth").write_text("python313.zip\n.\nLib\nLib/site-packages\n../app\nimport site\n", encoding="utf-8")
    # App-local Visual C++ libraries avoid a separate system-wide installer.
    redist = ["msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll"]
    for name in redist:
        source = Path(os.environ["WINDIR"]) / "System32" / name
        if not source.is_file():
            raise RuntimeError("Missing build-machine redistributable: " + name)
        for folder in [runtime, runtime / "Lib" / "site-packages" / "onnxruntime" / "capi", stage / "engine" / "cpu", stage / "engine" / "vulkan"]:
            copy_file(source, folder / name)
    for kind in ("cpu", "vulkan"):
        engine = stage / "engine" / kind
        shutil.copytree(downloads / ("llama-" + kind), engine, dirs_exist_ok=True)
    extract_once(downloads / "firefox.zip", stage / "browser", "firefox/firefox.exe")
    model = Path.home() / ".lmstudio" / "models" / "lmstudio-community" / "Qwen3-8B-GGUF" / "Qwen3-8B-Q4_K_M.gguf"
    copy_file(model, stage / "models" / model.name)
    embeddings = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2" / "onnx"
    shutil.copytree(embeddings, stage / "assets" / "embedding" / "onnx", dirs_exist_ok=True)
    app = stage / "app"
    for name in ("app.py", "orchestrator.py", "orchestrator_agent.py", "orchestrator_config.py", "subagent_client.py", "flights_agent.py", "local_llm.py"):
        copy_file(PROJECT / name, app / name)
    for directory in ("ui", "sandbox", "airport_transport", "destination_agent", "destination_data"):
        shutil.copytree(PROJECT / directory, app / directory, dirs_exist_ok=True, ignore=IGNORE)
    for name in ("money_tools.py", "money_customs_agent.py"):
        copy_file(PROJECT / "money&customs_agent" / name, app / "money&customs_agent" / name)
    for name in ("standalone_runtime.py", "verify_local.py", "bundled_data.py", "dining_policy.py"):
        copy_file(PROJECT / "desktop" / name, app / "desktop" / name)
    (app / "desktop" / "__init__.py").write_text("", encoding="utf-8")
    (app / ".chainlit").mkdir(exist_ok=True)
    (app / ".chainlit" / "config.toml").write_text('[project]\nuser_env=[]\ncache=false\npersist_user_env=false\n[UI]\nname="Travel Agency"\nlanguage="en-US"\n[meta]\ngenerated_by="2.11.0"\n', encoding="utf-8")
    (app / "chainlit.md").write_text("# Travel Agency\n\nThe local model, Python and browser are included. Travel data tools may require internet and your own optional API credentials. Restaurant recommendations are unavailable until a verified data source is connected. Activities and Budget currently use labelled sample data. General model guidance is unverified.\n", encoding="utf-8")
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll", "/out:" + str(stage / "TravelAgency.exe"), str(PROJECT / "desktop" / "StandaloneLauncher.cs")], check=True)
    notices = """Travel Agency Standalone - third-party software notices

This distribution includes Python 3.13.5 (PSF license), Python packages with
their original .dist-info license metadata, llama.cpp (MIT), Qwen3-8B
(Apache-2.0), Chroma's all-MiniLM-L6-v2 ONNX embedding model (Apache-2.0),
Firefox via Playwright (MPL-2.0 and third-party licenses), LLVM OpenMP, and Microsoft
Visual C++ redistributable runtime files. Component license files are retained.
The Travel Agency source is included under app/. Existing project ownership
and licensing continue to apply. This build does not grant additional rights
to third-party data or API services.

No user API keys, .env files, chats or LM Studio account information are included.
"""
    (stage / "THIRD-PARTY-NOTICES.txt").write_text(notices, encoding="utf-8")
    for source in (downloads / "licenses").glob("*"):
        copy_file(source, stage / "licenses" / source.name)
    if any(path.name == ".env" for path in stage.rglob("*")):
        raise RuntimeError("A private environment file was found in the payload.")
    for path in app.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".json", ".toml"}:
            content = path.read_text(encoding="utf-8-sig", errors="ignore")
            import re
            if re.search(r"(?:sk-proj-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{30,})", content):
                raise RuntimeError("Potential credential in payload file: " + str(path.relative_to(stage)))
    files = [p for p in stage.rglob("*") if p.is_file()]
    manifest = {"version": "1.0.1", "files": len(files), "uncompressed_bytes": sum(p.stat().st_size for p in files), "python": "3.13.5-embed-amd64", "llama_cpp": "b11669", "browser": "playwright-firefox-1555", "model": model.name, "includes_credentials": False, "external_python_required": False, "lm_studio_required": False, "external_browser_required": False}
    (stage / "bundle-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--downloads", type=Path, required=True)
    build(parser.parse_args())
