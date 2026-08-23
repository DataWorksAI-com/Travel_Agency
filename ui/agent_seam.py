"""
ui/agent_seam.py -- the real-vs-dummy seam for the UI.

The rule this file exists to enforce: the UI never chooses between a real
agent and a stand-in. app.py calls plan_trip. plan_trip reaches agents
through `get_client` (bound at orchestrator.py:30 by
`from orchestrator_config import get_client`). This file is the only place
that decides which of the two `get_client` hands back.

Mechanism: the same one-line intervention sandbox/run_pipeline.py:56 uses --
rebind the module attribute `orchestrator.get_client`. Emily's
orchestrator_config.py is NOT edited; its builders are still what produce a
real client, reached here through its own public get_client().

What this seam does NOT do, deliberately: it does not hide a failed agent
behind sample data. It used to. The layers below have two error-string
escape hatches --

    orchestrator_config.py:130   "[{name} unavailable] {error_message}"   build failed
    subagent_client.py:98        "[subagent error] {exc}"                 call failed

-- and this seam used to catch both and substitute that slot's stand-in, so
the browser never showed an error. That was the right call for a demo where
nothing should look broken. It is the wrong call for THIS UI, whose job is
to connect the orchestrator to live agents and show which ones actually
ran. Substituting plausible prose for the one honest signal the stack
produces means a complete, believable itinerary can be assembled entirely
from agents that never executed -- the hazard HANDOFF.md called "the one
thing most likely to mislead someone".

So a REAL slot that fails now reports FAILED and says so in the UI, with
the cause. The orchestrator already tolerates this: it never raises, and
_assemble_itinerary passes whatever came back straight through
(ORCHESTRATOR_DESIGN.md #4), so an honest failure string breaks nothing
that a stand-in was protecting.

DUMMY is still here, but it is now an EXPLICIT CHOICE for a key-free demo,
never an automatic fallback. Nothing silently becomes a stand-in.

Swapping one agent between real and stand-in is a config change here and
nowhere else -- see MODES below and UI_BUILD_REPORT.md.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The repo root, for orchestrator/orchestrator_config. (budget_agent_rohan was
# needed here too while the budget slot ran the envelope direct path; that is
# no longer an orchestrator option, so nothing under it is imported now.)
#
# APPENDED, and re-checked before every call, and neither is a style choice.
# Chainlit loads app.py with sys.path.insert(0, target_dir) at
# chainlit/config.py:592 and then sys.path.pop(0) at chainlit/config.py:624 --
# an unconditional pop of index 0 after exec_module. Two consequences:
#
#   * anything this module inserts at index 0 during app import is what that
#     pop removes, so append instead;
#   * the entry that pop removes is the repo root itself, so a LAZY import
#     done later (orchestrator_config is deliberately deferred to first call)
#     can fail even though startup was clean. Hence _ensure_paths(), called
#     again at call time.
#
# The symptom when this is wrong is a ModuleNotFoundError on the first agent
# call, silently degraded to sample data. That is exactly the failure this
# seam must not hide, which is why it is spelled out here.
_NEEDED_PATHS = (str(REPO_ROOT),)


def _ensure_paths() -> None:
    for path in _NEEDED_PATHS:
        if path not in sys.path:
            sys.path.append(path)


_ensure_paths()

from sandbox import fakes  # noqa: E402  deterministic stand-ins, prose left as-is

# ---------------------------------------------------------------------------
# Modes. One per orchestrator slot (the six keys of
# orchestrator_config._BUILDERS, orchestrator_config.py:99-106).
#
#   REAL   -- build through orchestrator_config.get_client(); needs that
#             agent's branch merged, its deps installed and its key present.
#   DUMMY  -- the deterministic stand-in in sandbox/fakes.py.
#
# There is deliberately no third mode. An earlier DIRECT mode routed the
# budget slot to budget_agent_rohan/evaluation/direct_path.render -- the
# per-diem envelope proposer, now `proposed_envelope_agent`. That agent is
# PROPOSED FUTURE WORK and is not an orchestrator option yet, so the mode is
# gone rather than merely defaulted off: leaving it selectable would let a
# stray TRAVEL_UI_AGENTS value put unreleased work in front of a user.
#
# The envelope agent itself is untouched and still runs standalone --
# budget_agent_rohan/ plus sandbox/run_envelope_test.py. Re-wiring it is a
# deliberate future change here, not a config flip.
#
# THE SWAP: flip one value to REAL (or set TRAVEL_UI_AGENTS, below). No UI
# edit, no orchestrator edit. A slot left on DUMMY shows stand-in content
# because that was chosen; a slot set to REAL shows either the live agent
# or an honest "not connected" with its cause. What it never shows is a
# stand-in standing in for a failure.
# ---------------------------------------------------------------------------

REAL = "real"
DUMMY = "dummy"

# Not a selectable mode -- an OUTCOME. Nothing can be configured to FAILED;
# it is what a REAL slot reports when its agent could not be reached. Kept
# distinct from DUMMY so the UI can say "not connected" rather than
# implying a stand-in was chosen on purpose.
FAILED = "failed"

MODES: dict[str, str] = {
    "destination": DUMMY,
    "flights": DUMMY,
    "restaurants": DUMMY,
    "activities": DUMMY,
    "budget": DUMMY,
    "money_customs": DUMMY,
}

# Env override so a swap needs no file edit at all:
#   $env:TRAVEL_UI_AGENTS = "flights=real,destination=real"
ENV_VAR = "TRAVEL_UI_AGENTS"

LABELS = {
    "destination": "Destination",
    "flights": "Flights",
    "restaurants": "Restaurants",
    "activities": "Activities",
    "budget": "Budget",
    "money_customs": "Money & Customs",
}

# fakes.REPLIES (sandbox/fakes.py:56) covers the five key-needing agents. It
# has no Budget entry, because in the sandbox Budget used to run the real
# envelope direct path. That path is no longer an orchestrator option, so
# the budget slot needs a stand-in like every other slot; the string lives
# here rather than in fakes.py so the sandbox's own fixtures stay untouched.
_BUDGET_DUMMY = (
    "Sample allocation: lodging $1,400, meals $760, activities $480, local "
    "transport $160, reserve $200. Stand-in figures, not a costed plan."
)


def _dummy_reply(slot: str) -> str:
    return fakes.REPLIES.get(slot, _BUDGET_DUMMY)


def _extract_cause(reply) -> str:
    """Pull the human-useful cause out of a layered error string.

    The shapes below wrap the real cause in a bracketed tag that names the
    layer, not the problem:

        "[flights unavailable] No module named 'deepagents'"
        "[subagent error] Rate limit exceeded: free-models-per-day"

    The tag is noise to a reader and, more practically, keeping it would put
    the literal text "unavailable]" into the assembled itinerary, which is
    exactly the internal-leakage that verify_seam.py checks for. So the tag
    is stripped and only the cause is surfaced.
    """
    if not isinstance(reply, str) or not reply.strip():
        return "the agent returned an empty reply"
    text = reply.strip()
    if text.startswith("[") and "]" in text:
        text = text.split("]", 1)[1].strip()
    return text or "no cause reported"


def _failure_reply(slot: str, cause: str) -> str:
    """What a failed REAL slot puts in front of the user.

    Written to be unmistakable in an itinerary full of prose: it must not
    read as a result. It says the agent did not run, and it carries the
    cause, because the cause is usually the entire actionable content --
    a missing dep, an absent key, a spent quota.
    """
    label = LABELS.get(slot, slot.title())
    return (
        f"Not connected -- the {label} agent did not run, so there is no "
        f"real data for this section.\nCause: {cause}"
    )


def resolve_modes(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """MODES, then the env var, then an explicit dict. Unknown slot -> DUMMY."""
    resolved = dict(MODES)

    raw = os.environ.get(ENV_VAR, "").strip()
    if raw:
        for pair in raw.split(","):
            if "=" not in pair:
                continue
            slot, _, mode = pair.partition("=")
            slot, mode = slot.strip().lower(), mode.strip().lower()
            if slot in resolved and mode in (REAL, DUMMY):
                resolved[slot] = mode

    if overrides:
        resolved.update({k: v for k, v in overrides.items() if k in resolved})

    return resolved


def _looks_like_error(reply) -> bool:
    """True for the error-string shapes the layers below can return.

    orchestrator_config.py:130  -> "[flights unavailable] ..."
    subagent_client.py:98       -> "[subagent error] ..."
    subagent_client.py:182      -> "[subagent unreachable over SLIM] ..."
    """
    if not isinstance(reply, str) or not reply.strip():
        return True
    head = reply.lstrip()[:160]
    if not head.startswith("["):
        return False
    return any(m in head for m in ("subagent error", "unavailable]", "unreachable"))


class SeamClient:
    """Implements the SubagentClient interface: await call(task) -> str.

    Never raises. An unreachable REAL agent does NOT degrade to a stand-in:
    it reports FAILED with its cause, so the UI can say "not connected"
    rather than showing sample data that reads like a result. The caller
    learns which of the three outcomes happened via `after`.
    """

    def __init__(self, slot: str, mode: str, before=None, after=None):
        self.slot = slot
        self.mode = mode
        self._before = before
        self._after = after
        self._real = None  # built on first use

    def _real_client(self):
        if self._real is None:
            # Emily's public entry point, unmodified. It swallows build
            # failures into a client whose call() returns
            # "[{name} unavailable] ...", which _looks_like_error catches
            # below -- so a missing branch or dep needs no special case here.
            from orchestrator_config import get_client

            self._real = get_client(self.slot)
        return self._real

    def _log_failure(self, why: str) -> None:
        """The browser gets the short cause; the terminal gets the traceback.

        The UI line is deliberately one sentence, so an itinerary stays
        readable. The full traceback still goes to the terminal, since that
        is where someone debugging a dep or key problem is looking.
        """
        print(f"[seam] {self.slot}: NOT CONNECTED -- {why}", flush=True)
        if sys.exc_info()[0] is not None:
            traceback.print_exc()

    async def call(self, task: str) -> str:
        _ensure_paths()  # see the comment on _NEEDED_PATHS

        if self._before is not None:
            await self._before(self.slot, self.mode, task)

        # DUMMY is a choice, so it is honoured without ever touching the
        # real client. REAL means real: it either succeeds or it reports
        # why not. There is no path from REAL to a stand-in.
        if self.mode == DUMMY:
            effective, reply = DUMMY, _dummy_reply(self.slot)
        else:
            try:
                raw = await self._real_client().call(task)
            except Exception as exc:
                # subagent_client already promises not to raise, so this is
                # the belt-and-braces path -- a client that broke its own
                # contract still must not take the whole run down.
                self._log_failure(f"call raised: {type(exc).__name__}: {exc}")
                effective = FAILED
                reply = _failure_reply(self.slot, f"{type(exc).__name__}: {exc}")
            else:
                if _looks_like_error(raw):
                    cause = _extract_cause(raw)
                    self._log_failure(cause)
                    effective, reply = FAILED, _failure_reply(self.slot, cause)
                else:
                    effective, reply = REAL, raw

        if self._after is not None:
            await self._after(self.slot, effective, task, reply)

        return reply


def install_seam(before=None, after=None, overrides=None) -> dict[str, str]:
    """Route every orchestrator slot through SeamClient. Returns the modes.

    `before(slot, mode, task)` and `after(slot, effective_mode, task, reply)`
    are optional async hooks -- how the UI gets per-agent visibility without
    the UI knowing anything about real-vs-dummy.
    """
    import orchestrator

    modes = resolve_modes(overrides)
    cache: dict[str, SeamClient] = {}

    def _get_client(name: str):
        if name not in cache:
            cache[name] = SeamClient(name, modes.get(name, DUMMY), before, after)
        return cache[name]

    orchestrator.get_client = _get_client  # the only intervention
    return modes
