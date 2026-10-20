"""Supervisor for the bundled Python, model server and browser."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

APP = Path(__file__).resolve().parents[1]
BUNDLE = APP.parent
sys.path.insert(0, str(APP))
CHILDREN = []


def configure():
    os.chdir(APP)
    if os.getenv("TRAVEL_OFFLINE_TEST") == "1":
        def local_sockets_only(event, values):
            if event == "socket.connect" and len(values) > 1:
                address = values[1]
                if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "localhost", "::1"}:
                    raise RuntimeError("External network is disabled during standalone verification.")
        sys.addaudithook(local_sockets_only)
    # No personal credentials are distributed or inherited by this app.
    for key in list(os.environ):
        if key.endswith(("_API_KEY", "_TOKEN")) or key in {"OPENAI_BASE_URL", "OPENAI_API_BASE"}:
            os.environ.pop(key, None)
    data = Path(os.getenv("TRAVEL_STANDALONE_DATA", str(Path(os.environ["LOCALAPPDATA"]) / "TravelAgencyStandalone")))
    data.mkdir(parents=True, exist_ok=True)
    settings = data / "data-services.env"
    if not settings.exists():
        settings.write_text("# Optional travel-data services. No LLM key is required.\nGEOAPIFY_API_KEY=\nTRAVELPAYOUTS_TOKEN=\nGOOGLE_ROUTES_API_KEY=\n", encoding="utf-8")
    from dotenv import dotenv_values
    values = dotenv_values(settings)
    for key in ("GEOAPIFY_API_KEY", "TRAVELPAYOUTS_TOKEN", "GOOGLE_ROUTES_API_KEY"):
        if values.get(key):
            os.environ[key] = values[key]
    os.environ.update({
        "TRAVEL_STANDALONE": "1", "TRAVEL_LLM_PROVIDER": "local",
        "TRAVEL_LOCAL_MODEL": "qwen3-8b", "TRAVEL_UI_ORCHESTRATOR": "pipeline",
        "TRAVEL_LOCAL_TIMEOUT": "600", "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false", "LANGCHAIN_TRACING": "false",
        "ANONYMIZED_TELEMETRY": "False", "DO_NOT_TRACK": "1",
        "PYTHONUTF8": "1", "TRAVEL_STANDALONE_DATA": str(data),
    })
    # Chroma's embedding weights ship with the installer, so first use does
    # not silently download a model from the internet.
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
    ONNXMiniLM_L6_V2.DOWNLOAD_PATH = BUNDLE / "assets" / "embedding"
    return data


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_http(url, process, seconds=240):
    opener = build_opener(ProxyHandler({}))
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError("A bundled service stopped. Check the local log.")
        try:
            with opener.open(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(0.5)
    raise RuntimeError("The bundled service did not start in time. Check available memory and local logs.")


def spawn(args, log):
    child = subprocess.Popen(args, cwd=APP, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    CHILDREN.append(child)
    return child


def stop_children():
    for child in reversed(CHILDREN):
        if child.poll() is None:
            subprocess.run(["taskkill.exe", "/PID", str(child.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()


def run(args):
    data = configure()
    if args.mode == "demo":
        os.environ["TRAVEL_LLM_PROVIDER"] = ""
    if args.web:
        # The caller has already bound the local inference endpoint.
        from chainlit.cli import cli
        sys.argv = ["chainlit", "run", str(APP / "app.py"), "--host", "127.0.0.1", "--port", str(args.port), "--headless"]
        cli()
        return
    if args.mode == "demo":
        os.environ["TRAVEL_UI_AGENTS"] = ",".join(f"{name}=dummy" for name in ("destination", "flights", "money_customs", "restaurants", "activities", "budget"))
    else:
        os.environ["TRAVEL_UI_AGENTS"] = "destination=real,flights=real,money_customs=real,restaurants=dummy,activities=dummy,budget=dummy"
    log_file = data / ("services-" + time.strftime("%Y%m%d-%H%M%S") + ".log")
    report = {"python": sys.executable, "bundle": str(BUNDLE), "mode": args.mode, "cloud_llm_used": False}
    with log_file.open("w", encoding="utf-8") as log:
        if args.mode != "demo":
            model_port = free_port()
            os.environ["TRAVEL_LOCAL_BASE_URL"] = f"http://127.0.0.1:{model_port}/v1"
            engine = BUNDLE / "engine" / ("vulkan" if args.mode == "gpu" else "cpu") / "llama-server.exe"
            print("STATUS Loading the bundled Qwen3 model...", flush=True)
            model = spawn([str(engine), "-m", str(BUNDLE / "models" / "Qwen3-8B-Q4_K_M.gguf"), "--host", "127.0.0.1", "--port", str(model_port), "--alias", "qwen3-8b", "-c", "16384", "-np", "1", "-t", str(min(8, max(2, (os.cpu_count() or 4) // 2))), "-ngl", "99" if args.mode == "gpu" else "0", "--jinja", "--reasoning-budget", "0", "--no-webui"], log)
            wait_http(f"http://127.0.0.1:{model_port}/health", model)
            if args.self_test:
                from desktop.verify_local import verify
                report["model_test"] = verify()
        web_port = free_port()
        url = f"http://127.0.0.1:{web_port}"
        web = spawn([sys.executable, "-I", "-u", str(Path(__file__)), "--web", "--mode", args.mode, "--port", str(web_port)], log)
        wait_http(url + "/", web)
        # Verify Chinese locale requests still receive English UI strings.
        with build_opener(ProxyHandler({})).open(url + "/project/translations?language=zh-CN", timeout=10) as response:
            translated = json.load(response)
        report["english_ui"] = translated.get("translation", {}).get("common", {}).get("actions", {}).get("cancel") == "Cancel"
        if not report["english_ui"]:
            raise RuntimeError("The bundled UI did not return English translations.")
        report["http_status"] = 200
        browser_exe = BUNDLE / "browser" / "firefox" / "firefox.exe"
        if args.self_test:
            profile = data / "browser-test"
            profile.mkdir(exist_ok=True)
            screenshot = data / "browser-test.png"
            browser = spawn([str(browser_exe), "-headless", "-no-remote", "-profile", str(profile), "-screenshot", str(screenshot), url], log)
            browser.wait(timeout=90)
            if browser.returncode != 0 or not screenshot.is_file() or screenshot.stat().st_size < 5000:
                raise RuntimeError("The bundled browser failed to render the page.")
            report["browser_started"] = True
            report["status"] = "PASS"
            (data / "self-test.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print("PASS " + str(data / "self-test.json"), flush=True)
            return
        print("READY " + url, flush=True)
        profile = data / "browser"
        profile.mkdir(exist_ok=True)
        spawn([str(browser_exe), "-no-remote", "-profile", str(profile), "-new-window", url], log)
        while web.poll() is None:
            time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["cpu", "gpu", "demo"], default="cpu")
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--port", type=int)
    parser.add_argument("--self-test", action="store_true")
    try:
        run(parser.parse_args())
    except Exception as error:
        print("ERROR " + type(error).__name__ + ": " + str(error), flush=True)
        sys.exit(1)
    finally:
        stop_children()
