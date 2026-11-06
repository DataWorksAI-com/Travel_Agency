"""
llm_config.py -- the one place that decides which chat model each agent runs on.

Every agent asks get_chat_model(agent) for its model instead of constructing a
provider class itself, so moving the whole system between a local Ollama model
and a hosted one is an env-var change, not a code change.

Resolution, first match wins:

    <AGENT>_MODEL   per-agent override (names below; two predate this file)
    LLM_MODEL       one model for every agent
    DEFAULT_MODEL   ollama:qwen3:8b

Values are init_chat_model strings, provider first: "ollama:qwen3:8b",
"anthropic:claude-haiku-4-5", "openrouter:openai/gpt-4o-mini",
"cohere:command-r-plus-08-2024". Any other OpenAI-compatible server (LM Studio,
vLLM, llama.cpp) is "openai:<model>" plus LLM_BASE_URL.

num_ctx and reasoning are Ollama options and are applied to ollama: models
only. temperature defaults to 0 there too, but is NOT passed to other providers
by default: the Anthropic API rejects it for the model Destination used (a 400,
"temperature: Extra inputs are not permitted"), so those get their provider
defaults unless LLM_TEMPERATURE is set.
"""

import json
import os
import urllib.request

from langchain.chat_models import init_chat_model

DEFAULT_MODEL = "ollama:qwen3:8b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

# ORCHESTRATOR_MODEL and MONEY_AGENT_MODEL were already read by their modules
# before this file existed; keeping the names means an existing .env still works
# -- though a bare model name there now needs its provider prefix.
_PER_AGENT = {
    "destination": "DESTINATION_MODEL",
    "flights": "FLIGHTS_MODEL",
    "money_customs": "MONEY_AGENT_MODEL",
    "orchestrator": "ORCHESTRATOR_MODEL",
}

# Ollama "thinking", per agent: <AGENT>_REASONING, then OLLAMA_REASONING, then
# the default here. Off for the three subagents: with it on, qwen3:8b ran ~10x
# slower, Flights searched the wrong year and Money & Customs' prompt neared
# num_ctx. On for the orchestrator: with it off, qwen3:8b's tool calls for the
# orchestrator's prompt come back unparseable and nothing gets called.
_REASONING = {
    "destination": ("DESTINATION_REASONING", "false"),
    "flights": ("FLIGHTS_REASONING", "false"),
    "money_customs": ("MONEY_AGENT_REASONING", "false"),
    "orchestrator": ("ORCHESTRATOR_REASONING", "true"),
}


def model_spec(agent: str) -> str:
    """The init_chat_model string this agent will run on."""
    return (
        os.getenv(_PER_AGENT[agent]) or os.getenv("LLM_MODEL") or DEFAULT_MODEL
    ).strip()


def get_chat_model(agent: str, max_tokens: int | None = None):
    """Build the chat model for one agent. No network call is made here."""
    spec = model_spec(agent)
    kwargs = {}
    if spec.startswith("ollama:"):
        kwargs.update(
            base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
            reasoning=_reasoning(reasoning_setting(agent)),
        )
        if max_tokens:
            kwargs["num_predict"] = max_tokens
    else:
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if os.getenv("LLM_TEMPERATURE"):
            kwargs["temperature"] = float(os.getenv("LLM_TEMPERATURE"))
        if spec.startswith("openai:") and os.getenv("LLM_BASE_URL"):
            kwargs["base_url"] = os.getenv("LLM_BASE_URL")
            # Local servers ignore the key, but the client refuses to start without one.
            kwargs["api_key"] = os.getenv("OPENAI_API_KEY") or "not-needed"
    try:
        return init_chat_model(spec, **kwargs)
    except ImportError as exc:
        # The library's message already names the package to pip install; this
        # adds which setting asked for it.
        raise ImportError(f"The {agent} agent is set to {spec!r}. {exc}") from exc


def reasoning_setting(agent: str) -> str:
    """The raw thinking setting for an ollama: model (see _REASONING)."""
    name, default = _REASONING[agent]
    return os.getenv(name) or os.getenv("OLLAMA_REASONING") or default


def _reasoning(value: str) -> bool | str:
    """OLLAMA_REASONING: true/false, or a level such as "low" for models that take one."""
    lowered = value.strip().lower()
    if lowered in ("", "0", "false", "no", "off"):
        return False
    if lowered in ("1", "true", "yes", "on"):
        return True
    return lowered


def _ollama_name(spec: str) -> str:
    name = spec.split(":", 1)[1]
    return name if ":" in name else f"{name}:latest"


def check_local_llm(agents=tuple(_PER_AGENT)) -> str | None:
    """One readable message if a local model the given agents need is not
    usable, else None. Checks only that the Ollama server answers and that each
    model is pulled -- cheap enough to run before every request. Makes no
    request at all when none of the agents runs on an ollama: model."""
    needed = sorted({_ollama_name(model_spec(a)) for a in agents if model_spec(a).startswith("ollama:")})
    if not needed:
        return None

    base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/")
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as resp:
            installed = {m["name"] for m in json.load(resp).get("models", [])}
    except Exception:
        return (
            f"The local model server (Ollama) isn't running at {base_url}. "
            "Start Ollama and try again."
        )

    missing = [name for name in needed if name not in installed]
    if missing:
        pulls = "; ".join(f"ollama pull {name}" for name in missing)
        return (
            f"The local model {', '.join(missing)} isn't installed in Ollama. "
            f"Run: {pulls}"
        )
    return None
