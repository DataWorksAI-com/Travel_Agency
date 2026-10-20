"""Explicit local chat-model routing; never falls back to a hosted model."""

import os
from urllib.parse import urlparse


def local_enabled() -> bool:
    return os.getenv("TRAVEL_LLM_PROVIDER", "").strip().lower() == "local"


def local_settings() -> tuple[str, str]:
    base = os.getenv("TRAVEL_LOCAL_BASE_URL", "http://127.0.0.1:1234/v1").strip().rstrip("/")
    parsed = urlparse(base)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path != "/v1"
    ):
        raise ValueError("Local LLM URL must be a loopback address ending in /v1, for example http://127.0.0.1:1234/v1.")
    model = os.getenv("TRAVEL_LOCAL_MODEL", "qwen3-8b").strip()
    if not model:
        raise ValueError("Choose a local model identifier from LM Studio.")
    return base, model


def local_model(max_tokens: int = 2048):
    for flag in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        os.environ[flag] = "false"
    # This client implements the protocol; requests go only to LM Studio.
    # Explicit httpx clients prevent proxy environment variables from routing
    # loopback prompts through an external proxy.
    import httpx
    from langchain_openai import ChatOpenAI

    base, model = local_settings()
    return ChatOpenAI(
        model=model,
        base_url=base,
        api_key="local-no-cloud-key",
        temperature=0,
        max_tokens=max_tokens,
        timeout=float(os.getenv("TRAVEL_LOCAL_TIMEOUT", "180")),
        max_retries=0,
        use_responses_api=False,
        http_client=httpx.Client(trust_env=False),
        http_async_client=httpx.AsyncClient(trust_env=False),
    )


def create_travel_agent(*, model, tools, system_prompt, **kwargs):
    if local_enabled():
        # Keep local contexts focused on the existing domain tools rather than
        # adding Deep Agents' generic filesystem/task-management tool suite.
        from langchain.agents import create_agent

        system_prompt += "\nWrite all final user-facing responses in English."
        if "qwen3" in local_settings()[1].lower():
            system_prompt += "\n/no_think"
        return create_agent(model=model, tools=tools, system_prompt=system_prompt, **kwargs).with_config(recursion_limit=24)
    from deepagents import create_deep_agent

    return create_deep_agent(model=model, tools=tools, system_prompt=system_prompt, **kwargs)
