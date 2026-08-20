"""
Centralized configuration for the Budget Cost Aggregator Agent.

Loads settings from environment variables (via a local `.env` file)
so API keys are never hard-coded in source.

Supports two ways to access an LLM:
  1. Direct Anthropic API key (simplest -- just set ANTHROPIC_API_KEY)
  2. OpenRouter (lets you swap between many providers/models)

If ANTHROPIC_API_KEY is set, it's used directly and takes priority.
Otherwise, falls back to OPENROUTER_API_KEY.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    provider: str          # "anthropic" or "openrouter"
    model_string: str      # e.g. "anthropic:claude-sonnet-4-6" or "openrouter:anthropic/claude-sonnet-4.5"


def load_settings() -> Settings:
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    # Prefer a direct Anthropic key if it looks real.
    if anthropic_key and not anthropic_key.startswith("sk-ant-your-key-here"):
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        return Settings(provider="anthropic", model_string=f"anthropic:{model}")

    # Fall back to OpenRouter.
    if openrouter_key and not openrouter_key.startswith("sk-or-your-key-here"):
        model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
        return Settings(provider="openrouter", model_string=f"openrouter:{model}")

    raise RuntimeError(
        "No API key found.\n"
        "1. Copy .env.example to .env\n"
        "2. Set EITHER:\n"
        "   - ANTHROPIC_API_KEY (from https://console.anthropic.com/settings/keys), or\n"
        "   - OPENROUTER_API_KEY (from https://openrouter.ai/settings/keys)\n"
    )
