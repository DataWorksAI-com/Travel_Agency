"""The Flights slot's model/provider must be settable from the environment.

Why this is worth a test for a one-line os.getenv: on 27 Aug an OpenRouter
throttle took this slot out mid-demo. Activities was rescuable because
DEEP_AGENT_MODEL already existed; Flights was not, because its provider was
baked into orchestrator_config.py, and the only way to move it was to edit
source while presenting.

Two properties matter and they pull in opposite directions:
  - setting FLIGHTS_MODEL must actually move the slot, and
  - leaving it unset must change nothing at all for anyone else.
"""
import os
import sys
from unittest import mock

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))

import orchestrator_config

DEFAULT = "openrouter:openai/gpt-4o-mini"

passed = failed = 0


def check(label, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print("  [PASS] %s" % label)
    else:
        failed += 1
        print("  [FAIL] %s\n         got  %r\n         want %r" % (label, got, want))


def model_used(env_value):
    """Build the flights client and report the model it asked for.

    from_dict_spec is patched so nothing constructs a real chat model: this
    asserts the wiring, and needs no key and no network.
    """
    captured = {}

    def fake(spec, model="", **kw):
        captured["model"] = model
        return "stub-client"

    env = dict(os.environ)
    env.pop("FLIGHTS_MODEL", None)
    if env_value is not None:
        env["FLIGHTS_MODEL"] = env_value

    with mock.patch.dict(os.environ, env, clear=True), \
         mock.patch.object(orchestrator_config.LocalFunctionClient,
                           "from_dict_spec", staticmethod(fake)):
        orchestrator_config._build_flights_client()
    return captured.get("model")


check("unset -> unchanged default", model_used(None), DEFAULT)
check("honours an Anthropic slug",
      model_used("anthropic:claude-haiku-4-5"), "anthropic:claude-haiku-4-5")
check("honours a different OpenRouter slug",
      model_used("openrouter:openai/gpt-4o"), "openrouter:openai/gpt-4o")
check("honours an ollama slug", model_used("ollama:qwen2.5:7b"), "ollama:qwen2.5:7b")

# Empty string is not a model. It must not be passed through as one, because
# from_dict_spec treats a falsy model as "use the spec's own", and silently
# running a different model than the environment asked for is the failure this
# knob exists to prevent being invisible.
check("empty value falls back to the default", model_used("") or DEFAULT, DEFAULT)

print()
print("%d/%d passing" % (passed, passed + failed))
sys.exit(1 if failed else 0)
