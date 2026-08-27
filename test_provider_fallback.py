"""A slot whose provider dies must fall back, not report itself broken.

On 27 Aug the Anthropic account hit zero mid-session. Every slot pointed at it
failed at once, each reporting "the agent did not run" -- which reads as six
broken agents rather than one dead provider.

The hard part is not the retry. It is telling a PROVIDER failure apart from an
agent that correctly has nothing to say: "No flights found for these dates" is a
right answer, and rebuilding a client over it would be a bug.
"""
import asyncio
import os
import sys

sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))

import orchestrator_config as oc

passed = failed = 0


def check(label, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print("  [PASS] %s" % label)
    else:
        failed += 1
        print("  [FAIL] %s  got %r want %r" % (label, got, want))


# --- provider down vs agent with no data -------------------------------------
for text, want in [
    ("Error 400: Your credit balance is too low to access the Anthropic API.", True),
    ("This request requires more credits, or fewer max_tokens.", True),
    ("Prompt tokens limit exceeded: 3062 > 2681", True),
    ("authentication_error: invalid x-api-key", True),
    ("No endpoints found for openrouter/nonexistent-model", True),
    # Correct answers that must NEVER trigger a rebuild:
    ("No flight data found for Boston to Cancun in September.", False),
    ("I hold no data for Colombia. The nearest country I hold is Belize.", False),
    ("Cancun is outside my coverage.", False),
    ("No cached flight data found from BOS to CUN around 2026-09.", False),
    ("Recommended restaurant: El Muelle Seafood, about $35 per person.", False),
    ("", False),
]:
    check("%-52r" % text[:52], oc.provider_unavailable(text), want)


# --- the wrapper actually swaps and retries -----------------------------------
class _Dying:
    async def call(self, task):
        return "Error 400: Your credit balance is too low to access the Anthropic API."


class _Healthy:
    def __init__(self):
        self.calls = 0
    async def call(self, task):
        self.calls += 1
        return "real answer from the fallback model"


healthy = _Healthy()
oc._BUILDERS["restaurants"] = lambda: healthy
os.environ["RESTAURANT_AGENT_MODEL"] = "anthropic:claude-haiku-4-5"

c = oc._FallbackClient("restaurants", _Dying())
out = asyncio.run(c.call("t"))
check("falls back and returns the retry's answer", out, "real answer from the fallback model")
check("env var repointed at the fallback", os.environ["RESTAURANT_AGENT_MODEL"], oc.FALLBACK_MODEL)
check("the rebuilt client was actually called", healthy.calls, 1)

# Only once: a second outage must not loop rebuilding.
c2 = oc._FallbackClient("restaurants", _Dying())
c2._fell_back = True
out2 = asyncio.run(c2.call("t"))
check("does not fall back twice", "credit balance" in out2, True)

# A healthy reply passes straight through, untouched.
class _Fine:
    async def call(self, task):
        return "No flight data found for this route."

c3 = oc._FallbackClient("flights", _Fine())
check("a correct 'no data' answer is passed through unchanged",
      asyncio.run(c3.call("t")), "No flight data found for this route.")

check("money_customs has no fallback entry (Cohere is hardcoded)",
      "money_customs" in oc.SLOT_MODEL_ENV, False)

print()
print("%d/%d passing" % (passed, passed + failed))
sys.exit(1 if failed else 0)
