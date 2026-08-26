"""
check_model.py — work out which layer is failing before blaming the agent.

Free-tier model slugs get retired, throttled, or turn out not to support tool
calling in practice even when the catalogue says they do. This walks up the
stack one rung at a time and prints the real exception rather than a wrapped
"Provider returned error".

    python check_model.py
    python check_model.py openrouter:google/gemma-4-31b-it:free
"""

import os
import sys
import traceback

from dotenv import load_dotenv

load_dotenv(override=True)

SLUG = (sys.argv[1] if len(sys.argv) > 1
        else os.getenv("BUDGET_AGENT_MODEL")
        or "openrouter:openai/gpt-oss-20b:free").strip()


def show(exc: Exception) -> None:
    """Print the real error, including anything nested inside it."""
    print(f"    FAILED: {type(exc).__name__}: {exc}")
    for attr in ("response", "body", "llm_output"):
        val = getattr(exc, attr, None)
        if val is not None:
            print(f"    {attr}: {val}")
    if exc.__cause__:
        print(f"    caused by: {type(exc.__cause__).__name__}: {exc.__cause__}")


def main() -> int:
    print(f"model: {SLUG}\n")

    # 1. Can we even build the client?
    print("1. build client")
    try:
        from langchain.chat_models import init_chat_model
        model = init_chat_model(SLUG, max_tokens=200)
        print("    ok")
    except Exception as exc:                      # noqa: BLE001
        show(exc)
        return 1

    # 2. Plain chat, no tools. Isolates the model from tool calling.
    print("2. plain chat")
    try:
        reply = model.invoke("Reply with exactly: OK")
        print(f"    ok -> {reply.content!r}")
    except Exception as exc:                      # noqa: BLE001
        show(exc)
        print("\n    The model itself is unreachable. Wrong slug, retired free")
        print("    tier, or rate limited. Try another slug as an argument.")
        return 1

    # 3. Tool calling. This is the rung most free models fail.
    print("3. tool calling")
    try:
        def add(a: int, b: int) -> int:
            """Add two integers together."""
            return a + b

        bound = model.bind_tools([add])
        out = bound.invoke("Use the add tool to add 2 and 3.")
        calls = getattr(out, "tool_calls", []) or []
        if calls:
            print(f"    ok -> requested {calls[0]['name']}{calls[0]['args']}")
        else:
            print("    NO TOOL CALL. The model answered in prose instead.")
            print(f"    content: {out.content!r}")
            print("\n    This model cannot drive the agent. Pick another.")
            return 1
    except Exception as exc:                      # noqa: BLE001
        show(exc)
        print("\n    Tool calling rejected by the provider. Pick another slug.")
        return 1

    # 4. The real agent, one task.
    print("4. full agent")
    try:
        from proposed_envelope_agent.agent import run_task
        print("   ", run_task("4 nights in Barbados for 2 people, budget 2000"))
    except Exception:                             # noqa: BLE001
        traceback.print_exc()
        return 1

    print("\nAll four rungs passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
