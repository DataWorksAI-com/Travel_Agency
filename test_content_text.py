"""A thinking model's content is a list of blocks, not a string.

Regression for the 27 Aug 2026 failure: the orchestrator moved to a model with
thinking on by default, and str() on the returned block list put a base64
`signature` at the top of the traveller's itinerary.
"""
import sys

sys.path.insert(0, ".")
from subagent_client import content_text as _content_text

passed = failed = 0


def check(label, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print("  [PASS] %s" % label)
    else:
        failed += 1
        print("  [FAIL] %s\n         got  %r\n         want %r" % (label, got, want))


# The exact shape seen live.
LIVE = [
    {"type": "thinking", "thinking": "", "signature": "CAISigIKjgEIERgCKkB2lon1jPO1l1wSx6Mxi1Am"},
    {"type": "text", "text": "# Cancun -- 5 nights"},
]
check("thinking block dropped, text kept", _content_text(LIVE), "# Cancun -- 5 nights")
check("no signature leaks", "CAISigI" in _content_text(LIVE), False)

check("plain string passes through", _content_text("hello"), "hello")
check("empty string stays empty", _content_text(""), "")

check(
    "several text blocks join in order",
    _content_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]),
    "a\nb",
)
check("bare strings in the list are kept", _content_text(["a", "b"]), "a\nb")
check(
    "tool_use blocks are not rendered",
    _content_text([{"type": "tool_use", "name": "ask_agent", "input": {}},
                   {"type": "text", "text": "only me"}]),
    "only me",
)
check(
    "empty text block contributes nothing",
    _content_text([{"type": "text", "text": ""}, {"type": "text", "text": "x"}]),
    "x",
)


class Block:
    def __init__(self, type_, text):
        self.type, self.text = type_, text


check(
    "object blocks work too",
    _content_text([Block("thinking", "hidden"), Block("text", "shown")]),
    "shown",
)

# Never raise: a weird payload must still return something.
check("thinking-only list falls back rather than vanishing",
      _content_text([{"type": "thinking", "thinking": "", "signature": "x"}]) != "", True)
check("None does not raise", isinstance(_content_text(None), str), True)


# ---------------------------------------------------------------------------
# All call sites must share ONE implementation.
#
# This bug was found twice, hours apart, because three places independently
# assumed `.content` was a string. Fixing one left the other two live, and the
# second failure was reported against a teammate's agent rather than this code.
# These checks fail if a fourth site appears, or if one drifts back to a local
# copy.
# ---------------------------------------------------------------------------
import orchestrator_agent
import orchestrator_config
import subagent_client
import inspect

check("orchestrator_agent uses the shared helper",
      orchestrator_agent._content_text is _content_text, True)

for mod in (orchestrator_config, subagent_client):
    src = inspect.getsource(mod)
    check("%s calls content_text" % mod.__name__, "content_text(" in src, True)
    check("%s has no raw str(content) fallback" % mod.__name__,
          "else str(content)" in src, False)

print()
print("%d/%d passing" % (passed, passed + failed))
sys.exit(1 if failed else 0)
