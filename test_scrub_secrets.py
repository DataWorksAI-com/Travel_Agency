"""Tests for the seam-level secret scrub in orchestrator.scrub_secrets.

Case 1 replays the actual leak: the Travelpayouts token arrives inside a
stringified requests exception, which is how the URL-as-error-message shape
put a credential in a reply.

The rest are the false positives that would make this worse than nothing --
mangling ordinary prose, or blanking the placeholder text that tells someone
their key is not set yet.

Run: python test_scrub_secrets.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import orchestrator
from orchestrator import scrub_secrets

cases = []


def check(name, condition):
    cases.append((name, bool(condition)))


# Isolate: drop any real credential from this process so the test is
# deterministic and never depends on (or prints) the developer's own keys.
for _name in [n for n in os.environ if any(
        h in n.upper() for h in orchestrator._SECRET_NAME_HINTS)]:
    del os.environ[_name]

os.environ["TRAVELPAYOUTS_TOKEN"] = "c02dab7f91e4471aa9f3d5e8b7c61d02"
os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-9f8e7d6c5b4a39281706abcdef123456"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-your-key-here"       # placeholder
os.environ["SHORT_TOKEN"] = "abc123"                            # too short
os.environ["ORCHESTRATOR_MODEL"] = "openrouter:openai/gpt-4o-mini"  # not a secret

# 1 -- the real leak shape: token inside a stringified requests exception
leak = (
    "Flight search failed for BOS→CUN: HTTPSConnectionPool(host='api.travelpayouts.com', "
    "port=443): Max retries exceeded with url: /v1/prices/cheap?origin=BOS&destination=CUN"
    "&token=c02dab7f91e4471aa9f3d5e8b7c61d02 (Caused by ConnectTimeoutError)"
)
out = scrub_secrets(leak)
check("real leak: token no longer present", "c02dab7f91e4471aa9f3d5e8b7c61d02" not in out)
check("real leak: names the variable", "<TRAVELPAYOUTS_TOKEN redacted>" in out)
check("real leak: keeps the diagnostic context", "ConnectTimeoutError" in out and "BOS" in out)

# 2 -- covers every credential-shaped var, not just a hardcoded list
check("scrubs an OpenRouter key too",
      "sk-or-v1-9f8e7d6c5b4a39281706abcdef123456" not in
      scrub_secrets("auth failed with key sk-or-v1-9f8e7d6c5b4a39281706abcdef123456"))

# 3 -- FALSE POSITIVE GUARDS
check("leaves a clean reply untouched",
      scrub_secrets("No flights found from BOS to AUA in September.")
      == "No flights found from BOS to AUA in September.")
check("does not blank placeholder values (they mean 'key not set')",
      "sk-ant-your-key-here" in scrub_secrets("ANTHROPIC_API_KEY is still sk-ant-your-key-here"))
check("ignores short values that would mangle prose",
      "abc123" in scrub_secrets("Booking reference abc123 confirmed."))
check("ignores non-secret vars with a model name",
      "openrouter:openai/gpt-4o-mini" in scrub_secrets("model: openrouter:openai/gpt-4o-mini"))
check("empty string is safe", scrub_secrets("") == "")
check("None is safe", scrub_secrets(None) is None)

# 4 -- multiple occurrences and multiple secrets in one reply
both = ("token=c02dab7f91e4471aa9f3d5e8b7c61d02 and again "
        "c02dab7f91e4471aa9f3d5e8b7c61d02 plus sk-or-v1-9f8e7d6c5b4a39281706abcdef123456")
out = scrub_secrets(both)
check("replaces every occurrence", "c02dab7f91e4471aa9f3d5e8b7c61d02" not in out)
check("replaces a second distinct secret", "sk-or-v1-9f8e7d6c5b4a39281706abcdef123456" not in out)

passed = sum(1 for _, ok in cases if ok)
for name, ok in cases:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"\n{passed}/{len(cases)} passing")
sys.exit(0 if passed == len(cases) else 1)
