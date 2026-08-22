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

Why the UI can't just use orchestrator_config.get_client unchanged: it has
two error-string escape hatches, and either would land in the browser as
text that reads like a crash --

    orchestrator_config.py:130   "[{name} unavailable] {error_message}"   build failed
    subagent_client.py:98        "[subagent error] {exc}"                 call failed

For a work-in-progress demo those are the wrong impression. "Flights:
sample data" reads as not-wired-yet; "Flights: [subagent error] No module
named 'deepagents'" reads as broken. So this seam catches both shapes and
falls back to that slot's deterministic stand-in.

Swapping one agent from stand-in to real is a config change here and
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
# edit, no orchestrator edit. Anything not connected stays on DUMMY, which
# is why the browser never shows an error string.
# ---------------------------------------------------------------------------

REAL = "real"
DUMMY = "dummy"

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

    Never raises and never returns an error string -- an unreachable real
    agent degrades to its stand-in, and the caller is told which actually
    happened via `after`, so the UI can label it honestly.
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

    def _log_fallback(self, why: str) -> None:
        """The browser gets the stand-in; the terminal gets the truth.

        Degrading silently is how a genuinely broken agent hides behind
        plausible-looking sample data, so every fallback is announced here
        even though nothing about it reaches the UI.
        """
        print(f"[seam] {self.slot}: falling back to stand-in -- {why}", flush=True)
        if sys.exc_info()[0] is not None:
            traceback.print_exc()

    async def call(self, task: str) -> str:
        _ensure_paths()  # see the comment on _NEEDED_PATHS

        if self._before is not None:
            await self._before(self.slot, self.mode, task)

        effective = self.mode
        reply = None

        if self.mode == REAL:
            try:
                reply = await self._real_client().call(task)
            except Exception:
                self._log_fallback("call raised")
                reply = None
            if _looks_like_error(reply):
                self._log_fallback(f"error-shaped reply: {str(reply)[:120]}")
                reply, effective = None, DUMMY

        if reply is None:
            reply, effective = _dummy_reply(self.slot), DUMMY

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
