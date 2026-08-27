"""
orchestrator_config.py -- wires each subagent's actual entry point behind
the SubagentClient interface, so orchestrator.py never needs to know how
a given subagent is reached.

Import paths below were verified against main as merged on 23 Aug 2026
(through PR #20). Four of the six slots now point at real, merged code;
the two that don't are called out individually. Remaining TODO markers
correspond to open decisions in ORCHESTRATOR_DESIGN.md -- resolve those,
then update this file, not orchestrator.py.
"""

import os
import sys
from pathlib import Path

from subagent_client import DEFAULT_MAX_TOKENS, LocalFunctionClient, content_text

REPO_ROOT = Path(__file__).resolve().parent


def _build_destination_client() -> LocalFunctionClient:
    # Real, merged. destination_agent/__init__.py:20 exports `answer` as an
    # alias of run_destination_agent specifically so the orchestrator can
    # import it under the team-standard name (PRs #15/#16). The
    # destination_recommender vs destination_recommender_alice split that
    # made this uncertain is resolved -- both are merged into main.
    from destination_agent import answer
    return LocalFunctionClient(answer)


def _build_flights_client() -> LocalFunctionClient:
    # STILL A STOPGAP -- the one slot whose contract has not changed.
    # Flights exports a plain dict spec, not a callable, so it goes through
    # LocalFunctionClient.from_dict_spec(). See ORCHESTRATOR_DESIGN.md #2:
    # if the group aligns Flights to expose answer() like every other
    # subagent, switch to the normal pattern below.
    # The model is set HERE, not in Flights' spec. llama-3.3-70b was
    # non-deterministic on this slot's short structured output; gpt-4o-mini is
    # not. But which model a slot runs on depends on this system's budget,
    # latency and determinism needs, not on the agent -- so it is the
    # orchestrator's decision to make and its file to hold it in. Likewise the
    # output ceiling, which from_dict_spec caps for every slot
    # (subagent_client.DEFAULT_MAX_TOKENS) rather than each agent capping
    # itself.
    #
    # Which PROVIDER is a deployment concern too, not just which model. On
    # 27 Aug an OpenRouter throttle took this slot and Activities out while the
    # four slots on other providers ran fine, and there was no way to move them
    # without editing this line. FLIGHTS_MODEL makes that a config change; the
    # default is unchanged, so nothing moves unless it is set.
    from flights_agent import flights_subagent
    return LocalFunctionClient.from_dict_spec(
        flights_subagent,
        model=os.getenv("FLIGHTS_MODEL", "openrouter:openai/gpt-4o-mini"),
    )

    # once aligned:
    # from flights_agent import answer
    # return LocalFunctionClient(answer)


def _build_restaurants_client() -> LocalFunctionClient:
    # Real, merged. restaurant_agent/__init__.py:23 defines answer(task).
    from restaurant_agent import answer
    return LocalFunctionClient(answer)


def _build_activities_client() -> LocalFunctionClient:
    # Real, merged -- and this slot changed the most. Three fixes over what
    # was here before:
    #
    # 1. The import was `from activities_agent import build_agent`, which
    #    could never resolve: the package directory is `activities-agent`
    #    with a HYPHEN, which is not a legal Python module name. Adding the
    #    directory itself to sys.path makes the inner activities_agent.py
    #    importable by its own (legal) name. Same approach used at
    #    sandbox/run_envelope_test.py:29 and app.py:35.
    # 2. PR #20 (merged Limeng + Jainam) exposes `answer(task)` directly, so
    #    the hand-rolled build_agent/ainvoke wrapper is now redundant --
    #    and it skipped the deterministic food-request guard that lives
    #    inside answer(), which was a real behaviour difference.
    # 3. `answer` is a NATIVE COROUTINE. The old wrapper called
    #    asyncio.run() on it, which raises RuntimeError when a loop is
    #    already running -- exactly the case here, since
    #    _run_parallel_subagents() calls this from inside asyncio.gather().
    #    LocalFunctionClient.call now awaits a coroutine function directly
    #    instead of pushing it to a worker thread.
    #
    # NOTE: `activities/` (no hyphen, also in main) is a different, older
    # copy of this agent. `activities-agent/` is the merged one -- do not
    # switch this to the shorter path just because it imports more cleanly.
    activities_dir = REPO_ROOT / "activities-agent"
    if str(activities_dir) not in sys.path:
        sys.path.insert(0, str(activities_dir))

    # Cap the output ceiling from out here rather than in the agent's own
    # default. glm-5.2's default is 65536, and on a free-tier OpenRouter key
    # the affordable max_tokens scales with remaining credit, so that default
    # eventually exceeds it and the slot dies with "requested up to 65536
    # tokens, but can only afford N" -- which looks like a broken agent and is
    # a config cliff. The agent reads DEEP_AGENT_MAX_TOKENS and leaves its
    # behaviour unchanged when it is unset, so running it standalone is
    # unaffected by this line. Set before the import, since MAX_TOKENS is read
    # at module scope.
    #
    # An explicit value already in the environment wins -- this is a default,
    # not an override.
    os.environ.setdefault("DEEP_AGENT_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))

    from activities_agent import answer
    return LocalFunctionClient(answer)


def _build_budget_client() -> LocalFunctionClient:
    # Real, merged (Shashank's, PRs #17/#18). The budget slot is the
    # repo-root RAG cost estimator: vector search over city cost docs ->
    # total estimate -> feasibility check. build_agent() is at
    # budget_agent/agent.py:86 and returns an .invoke()-able agent.
    #
    # This used to be ambiguous: budget_agent_rohan/ shipped a SECOND
    # package also named `budget_agent` (the per-diem envelope proposer),
    # so `import budget_agent` resolved to whichever landed in sys.modules
    # first -- import order, not intent, picked the agent. That package is
    # now `proposed_envelope_agent` and is NOT wired to any slot; it is
    # proposed future work. This name means one thing again.
    #
    # Going live needs three things, not just the import: `langchain` +
    # `deepagents` installed, ANTHROPIC_API_KEY or OPENROUTER_API_KEY set
    # (budget_agent/config.py:29-49 raises RuntimeError with neither), and
    # the Chroma vectorstore built via
    # budget_agent/scripts/build_vectorstore.py (enforced at
    # budget_agent/tools/rag_tools.py:33-37).
    from budget_agent.agent import build_agent

    def _answer(task: str) -> str:
        agent = build_agent()
        result = agent.invoke({"messages": [{"role": "user", "content": task}]})
        # content_text, not .content: on a model with thinking enabled the last
        # message's content is a LIST of blocks. Returning it raw handed the
        # seam a non-string, which surfaced as "the Budget agent returned an
        # empty reply" -- reported against Shashank's agent, caused here.
        return content_text(result["messages"][-1].content)

    return LocalFunctionClient(_answer)


def _build_money_customs_client() -> LocalFunctionClient:
    # money_customs_agent.py:111 defines answer(task) over money_tools.py.
    #
    # These two files are maintained on the `exchange_rate_emily` branch, not
    # here. As of 26 Aug 2026 the copies on this branch are byte-identical to
    # that branch's HEAD -- verified with `git diff --stat
    # origin/exchange_rate_emily -- money_tools.py money_customs_agent.py`,
    # which returns empty. This orchestrator does not modify them; changes to
    # this slot's behaviour belong to whoever owns that branch.
    #
    # Do NOT resync these two files from an older main. Before PR #21 merged,
    # main's money_tools.py was two commits behind that branch (11 match_score
    # occurrences against 25) and money_customs_agent.py was not on main at
    # all. Taking main as the reference for this slot would drop the tool
    # layer's confidence work and, previously, the agent itself.
    #
    # Note for anyone debugging coverage: search_money_customs returns
    # found=True unconditionally, so a fuzzy near-miss is reported as a hit and
    # the nearest held country can be presented as though it were the one
    # asked for. match_score is returned on every path but nothing here reads
    # it, because this seam is str -> str: answer() returns prose, so the score
    # never leaves the agent. Having the orchestrator decide coverage from
    # match_score needs a structured return from the seam -- that is
    # orchestrator work, and it is not built yet.
    from money_customs_agent import answer
    return LocalFunctionClient(answer)


# ---------------------------------------------------------------------------
# Built lazily (not at import time) so a missing/unfinished subagent branch
# doesn't crash the whole orchestrator on startup -- only the first call to
# that specific subagent fails, and it fails as a plain-text problem
# description (per SubagentClient.call's contract), not an import error
# that takes down everything else.
# ---------------------------------------------------------------------------

_BUILDERS = {
    "destination": _build_destination_client,
    "flights": _build_flights_client,
    "restaurants": _build_restaurants_client,
    "activities": _build_activities_client,
    "budget": _build_budget_client,
    "money_customs": _build_money_customs_client,
}

_clients_cache = {}


# ---------------------------------------------------------------------------
# Provider fallback
#
# A slot's model can stop being reachable for reasons that have nothing to do
# with the agent: the account behind it runs out of credit, the key is revoked,
# the provider retires a slug. On 27 Aug the Anthropic account went to zero
# mid-session and every slot pointed at it died at once, each reporting itself
# as a broken agent.
#
# That is a deployment failure, so it is handled here rather than in six
# agents. Each slot names the environment variable that chooses its model; when
# a call comes back with a PROVIDER-level failure, that variable is repointed at
# FALLBACK_MODEL, the client is rebuilt, and the call is retried once.
#
# money_customs is deliberately absent. It constructs ChatCohere directly, so no
# model string can move it off Cohere -- a fallback entry would promise
# something this code cannot deliver.
# ---------------------------------------------------------------------------

FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "openrouter:openai/gpt-4o-mini")

SLOT_MODEL_ENV = {
    "destination": "DESTINATION_AGENT_MODEL",
    "flights": "FLIGHTS_MODEL",
    "restaurants": "RESTAURANT_AGENT_MODEL",
    "activities": "DEEP_AGENT_MODEL",
    "budget": "OPENROUTER_MODEL",
}

# Signatures of the PROVIDER being unusable -- not of the agent having nothing
# to say. "No flights found for these dates" is a correct answer and must never
# trigger a rebuild; so must a coverage refusal. Everything here is a failure
# that a different provider would not have.
_PROVIDER_DOWN = (
    "credit balance is too low",
    "requires more credits",
    "insufficient credit",
    "insufficient_quota",
    "prompt tokens limit exceeded",
    "invalid api key",
    "invalid_api_key",
    "authentication_error",
    "unauthorized",
    "permission denied",
    "no endpoints found",
    "model not found",
    "is not a valid model",
    "does not exist or you do not have access",
)


def provider_unavailable(reply: str) -> bool:
    """True if this reply says the PROVIDER failed, not that the agent had no data."""
    lowered = (reply or "").lower()
    return any(sig in lowered for sig in _PROVIDER_DOWN)


class _FallbackClient:
    """Wraps a slot's real client and retries once on a provider outage.

    Wrapping rather than editing get_client's cache: the seam caches whatever
    get_client returned, so evicting an entry after the fact would not reach the
    object the orchestrator is already holding. A wrapper stays in place and
    swaps what is underneath it.
    """

    def __init__(self, slot: str, inner):
        self._slot = slot
        self._inner = inner
        self._fell_back = False

    async def call(self, task: str) -> str:
        reply = await self._inner.call(task)
        if self._fell_back or not provider_unavailable(reply):
            return reply

        env = SLOT_MODEL_ENV.get(self._slot)
        if not env or os.environ.get(env) == FALLBACK_MODEL:
            return reply

        previous = os.environ.get(env)
        os.environ[env] = FALLBACK_MODEL
        self._fell_back = True
        try:
            rebuilt = _BUILDERS[self._slot]()
        except Exception as exc:
            if previous is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = previous
            return reply + f"\n[fallback to {FALLBACK_MODEL} failed to build: {exc}]"

        self._inner = rebuilt
        print(f"[{self._slot}] provider unavailable; retrying on {FALLBACK_MODEL}")
        return await rebuilt.call(task)


def get_client(name: str) -> LocalFunctionClient:
    """Get (and lazily build) the client for one subagent by name."""
    if name not in _clients_cache:
        try:
            _clients_cache[name] = _BUILDERS[name]()
        except Exception as exc:
            # Wrap the *build* failure the same way SubagentClient.call
            # wraps a *call* failure, so a broken/missing subagent import
            # degrades to one clear error message instead of crashing
            # orchestrator startup.
            #
            # NOTE: `exc` itself can't be referenced inside the closure
            # below -- Python deletes an `except ... as exc:` binding as
            # soon as the except block ends, so capture the message into
            # a plain variable first, which the closure CAN still see.
            error_message = str(exc)

            class _BrokenClient:
                async def call(self, task: str) -> str:
                    return f"[{name} unavailable] {error_message}"

            _clients_cache[name] = _BrokenClient()
        else:
            if name in SLOT_MODEL_ENV:
                _clients_cache[name] = _FallbackClient(name, _clients_cache[name])
    return _clients_cache[name]
