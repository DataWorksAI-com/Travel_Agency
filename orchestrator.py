"""
orchestrator.py -- routes, sequences, and assembles the five subagents into
one itinerary response.

This is a SKELETON. It runs today against LocalFunctionClient stand-ins
(see orchestrator_config.py) and is deliberately structured so real
subagent code -- and later, a real SLIM transport -- can be dropped in
without changing the logic below. See ORCHESTRATOR_DESIGN.md for the
open decisions this file currently makes a provisional call on.

Sequencing, per the actual dependencies found while reviewing each
subagent's code (not a guess):
  1. Destination runs first -- Flights/Restaurants/Activities all need a
     resolved city; Destination is the only subagent that can produce one
     from either a named city or vague preferences.
  2. Flights, Restaurants, Activities run in parallel -- none of the three
     depends on either of the other two's output.
  3. Budget runs last -- its own docstring states its knowledge is "purely
     the priced line items it receives from the other sub-agents," so it
     cannot run before they have.

Money & Customs is called once here, by the orchestrator itself, rather than
every subagent importing it independently. Its reply is reported to the reader
as its own itinerary section and is NOT folded into any other subagent's task
string -- see _run_parallel_subagents.

HUB AND SPOKE. Every subagent talks to the orchestrator and to nobody else. No
subagent's response is passed into another subagent's prompt: doing that makes
this module a message bus between agents rather than the thing that decides,
and it is not the agreed architecture. Two places used to break that rule and
no longer do:

  - Money & Customs' reply was prepended to Flights' and Restaurants' tasks
    (ORCHESTRATOR_DESIGN.md #3, "implemented as a provisional guess").
  - Every reply was concatenated into Budget's task (#5). Budget now receives
    verified line items from orchestrator_costs instead.

If you are tempted to forward one agent's text to another, extract the decided
fact in here and pass that instead.
"""

import asyncio
import sys
import os

from orchestrator_config import get_client
from orchestrator_costs import build_budget_brief

# The only slot names that may reach get_client. Worth a guard now that a model
# picks them: orchestrator_config.get_client swallows its own KeyError, so an
# unknown name returns "[typo unavailable] 'typo'", and agent_seam falls back to
# modes.get(name, DUMMY) -- sample data. A hallucinated slot would come back as
# plausible prose instead of an error.
SLOTS = ("destination", "flights", "restaurants", "activities", "budget", "money_customs")


# ---------------------------------------------------------------------------
# Secret scrubbing at the seam
#
# Flights returned the Travelpayouts token to its caller: the token is a query
# parameter, and requests' exceptions stringify as the full request URL, so a
# failed search put the credential in the reply string. That was fixed at
# source (flights_agent._redact), which is the right place -- it also protects
# that agent when it runs standalone.
#
# This is the belt-and-braces version, and it belongs to the orchestrator
# rather than to any agent: EVERY slot's reply passes through ask_slot below,
# so one filter here covers all six, plus the seam's own failure strings.
# ui/agent_seam.py:297 interpolates `{type(exc).__name__}: {exc}` into a
# reply, which is precisely the shape that leaked -- and agent_seam runs
# UPSTREAM of this function, so its output is scrubbed too.
#
# It does not replace a source fix. An agent that leaks a credential still
# leaks it into its own logs, and into anything a teammate pastes into an
# issue on what is a public repo. This only guarantees that nothing reaches
# the browser transcript or, under the agentic orchestrator, the model's
# context -- where a leaked key would then be replayed to a provider.
# ---------------------------------------------------------------------------

# Any env var whose NAME contains one of these is treated as a credential. Name
# based rather than a hardcoded list, so a key added later is covered without
# anyone remembering to update this file.
_SECRET_NAME_HINTS = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")

# Below this length a value is more likely to be a flag ("true", "1") whose
# accidental replacement would mangle ordinary prose than a real credential.
_MIN_SECRET_LEN = 12

# .env.example ships placeholders, and budget_agent/config.py treats a value
# with one of these as ABSENT. Scrubbing them would turn a helpful "your key is
# still the placeholder" message into an unreadable one.
_PLACEHOLDER_MARKERS = ("your-", "your_", "-here", "changeme", "xxxx")


def _secret_values() -> dict[str, str]:
    """Credential-looking env values worth redacting, keyed by variable name."""
    found = {}
    for name, value in os.environ.items():
        if not any(hint in name.upper() for hint in _SECRET_NAME_HINTS):
            continue
        candidate = (value or "").strip()
        if len(candidate) < _MIN_SECRET_LEN:
            continue
        if any(marker in candidate.lower() for marker in _PLACEHOLDER_MARKERS):
            continue
        found[name] = candidate
    return found


def scrub_secrets(text: str) -> str:
    """Replace any credential value in `text` with '<NAME redacted>'.

    Named for the variable, not blanked, so a reader can still tell which key
    the failure was about -- that is the diagnostic value of the original
    error, and losing it would trade one debugging problem for another.
    """
    if not text:
        return text
    for name, value in _secret_values().items():
        if value in text:
            text = text.replace(value, f"<{name} redacted>")
    return text


# ---------------------------------------------------------------------------
# Concurrency gate
#
# On a free-tier OpenRouter key, an in-flight request RESERVES credit, and the
# max_tokens a later request can afford is what is left after those
# reservations. Fire three deep agents at once and whichever arrives last is
# told it "can only afford" a number far below what it asked for, and dies with
# HTTP 402.
#
# Measured on one run, 26 Aug 2026, with $4.81 of $5 unused on the key:
#
#   Activities    asked 2048, could afford 1015   (parallel three in flight)
#   orchestrator  asked 4000, could afford 3682   (fewer in flight)
#
# The affordable figure went UP between those two calls, which rules out
# cumulative spend -- the story I wrongly told twice while capping max_tokens
# on two agents. Both error messages said "in-flight requests"; the cause is
# concurrency, and the fix is to stop competing with ourselves.
#
# Gating here rather than at each call site covers BOTH orchestrators: the
# deterministic path's asyncio.gather AND the deep agent, which emits several
# ask_agent tool calls in one batch and would otherwise bypass any fix applied
# to _run_parallel_subagents alone.
#
# Default 1 (fully serialised) because that is what a free-tier key sustains.
# Raise it with TRAVEL_UI_MAX_CONCURRENCY once the key has headroom -- parallel
# is genuinely faster, it is just not free. 0 or less disables the gate.
# ---------------------------------------------------------------------------

MAX_CONCURRENCY = int(os.getenv("TRAVEL_UI_MAX_CONCURRENCY", "1"))

_gate_lock: "asyncio.Semaphore | None" = None


def _gate() -> "asyncio.Semaphore | None":
    """The shared slot gate, built on first use.

    Built lazily, not at import: an asyncio.Semaphore binds to the running loop
    the first time it is awaited, and orchestrator.py is imported long before
    Chainlit has a loop.
    """
    global _gate_lock
    if MAX_CONCURRENCY <= 0:
        return None
    if _gate_lock is None:
        _gate_lock = asyncio.Semaphore(MAX_CONCURRENCY)
    return _gate_lock


async def ask_slot(slot: str, task: str) -> str:
    """Call one subagent by slot name.

    `get_client` is looked up as a module global on purpose: ui/agent_seam.py
    rebinds `orchestrator.get_client` as its single intervention, and that only
    works if the name resolves here at call time. Importing get_client into
    another module, or caching a client at construction time, silently disables
    real/dummy mode, failure detection, timing and every per-agent UI step.

    Two things happen around the call, and this is the one place every slot's
    reply passes through on both paths:
      - concurrency is gated, so slots do not compete for credit reservations
      - the reply is scrubbed of credentials on the way out
    """
    if slot not in SLOTS:
        raise ValueError(f"unknown slot {slot!r}; expected one of {SLOTS}")
    gate = _gate()
    if gate is None:
        return scrub_secrets(await get_client(slot).call(task))
    async with gate:
        return scrub_secrets(await get_client(slot).call(task))


async def _call_money_customs_context(origin_country: str, destination_country: str) -> str:
    """Call Money & Customs once and return its reply for the itinerary.

    RESOLVED (ORCHESTRATOR_DESIGN.md, decision #3). This used to describe a
    blurb prepended to the other subagents' task strings, and that is no longer
    what happens: the reply goes to _assemble_itinerary as its own section and
    reaches no other agent. See the note in _run_parallel_subagents for why.

    The docstring is corrected here rather than left as-was because it
    described the relay this file was specifically changed to stop doing --
    anyone reading only this function would conclude the old behaviour is
    still live.
    """
    task = (
        f"Traveler is going from {origin_country} to {destination_country}. "
        f"Give the exchange rate and money customs (tipping/haggling) for "
        f"{destination_country}."
    )
    return await ask_slot("money_customs", task)


async def _run_destination(task: str) -> str:
    return await ask_slot("destination", task)


async def _run_parallel_subagents(task: str, money_context: str) -> dict:
    """Run Flights, Restaurants, Activities together -- none depends on
    the others' output, only on Destination having already resolved a
    city (assumed already folded into `task` by the caller).

    TODO (ORCHESTRATOR_DESIGN.md, decision #4): this currently has no
    uniform failure policy. If one of the three comes back with an
    error-shaped message, what should happen to final assembly -- omit
    that section and say so, retry once, or something else? Decide this
    before relying on the placeholder behavior below (currently: pass
    whatever came back straight through, error message or not).
    """
    # Money & Customs' reply is NOT forwarded here any more.
    #
    # It used to be prepended to both of these task strings
    # (ORCHESTRATOR_DESIGN.md #3, which marked it "implemented as a provisional
    # guess, worth confirming"). Review confirmed it, negatively: one agent's
    # response should not be passed to another agent. Every subagent talks to
    # the orchestrator and to nobody else -- that is the agreed architecture,
    # and prepending her reply here made this function a relay.
    #
    # Nothing is lost by dropping it. Flights prices routes and never needed
    # tipping norms; Restaurants returns records that already carry their own
    # prices. What the traveller actually needed -- the exchange rate and the
    # customs advice -- now reaches them directly, as a Money & Customs section
    # in _assemble_itinerary, which it never had before.
    flights_task = task
    restaurants_task = task
    activities_task = task  # money/customs likely irrelevant here -- confirm

    flights_result, restaurants_result, activities_result = await asyncio.gather(
        ask_slot("flights", flights_task),
        ask_slot("restaurants", restaurants_task),
        ask_slot("activities", activities_task),
    )

    return {
        "flights": flights_result,
        "restaurants": restaurants_result,
        "activities": activities_result,
    }


def _build_budget_task(task: str, destination_result: str, parallel_results: dict, stated_budget: str) -> str:
    """Build Budget's task from DECIDED line items, not the others' prose.

    RESOLVED (ORCHESTRATOR_DESIGN.md #5, "the biggest unresolved gap in the
    whole skeleton"). This used to concatenate every subagent's free text into
    one string and pass it through, which made the orchestrator a relay between
    subagents rather than the thing that decides -- not the agreed
    architecture, and the source of Budget billing $425 for a flight Flights
    had just said it could not find.

    Of the three options the design doc listed, this is (c) rather than (a).
    An LLM extraction step would add a second model whose job is to read prose
    and emit numbers -- a new place for figures to be invented, introduced to
    fix a problem that is entirely about invented figures. orchestrator_costs
    extracts deterministically instead and VERIFIES every figure appears
    verbatim in the reply it is attributed to. See that module's docstring.

    (b) -- a structured block at the source -- is still the better long-term
    answer, but it needs four other people to change their output contract.
    """
    # The traveller's own words reach Budget via build_budget_brief's `task`.
    # Without them Budget received the stated budget and the other subagents'
    # prose but never the request itself, so it could not know trip length,
    # party size or dates. On "Plan a week in Aruba from Boston, budget $3000"
    # it costed THREE DAYS and reported "Assumed 3 days (a reasonable default
    # when not specified)" -- correct reasoning over inputs that had the
    # duration stripped out of them.
    #
    # Destination is deliberately NOT forwarded. It returns climate, holidays
    # and beaches, none of which are costs, and forwarding it was part of what
    # made this function a relay.
    return build_budget_brief(
        task=task,
        replies={
            "flights": parallel_results.get("flights", ""),
            "restaurants": parallel_results.get("restaurants", ""),
            "activities": parallel_results.get("activities", ""),
        },
        is_failure=_looks_like_failure,
        stated_budget=stated_budget,
    )


def _looks_like_failure(reply: str) -> bool:
    """A slot that did not run, for the deterministic path.

    orchestrator_agent has its own version that defers to the seam's detector;
    this one stays here so orchestrator.py keeps working with no UI imported --
    that is what makes the deterministic path offline- and keyless-testable.
    """
    if not reply:
        return True
    lowered = reply.lower()
    return (
        reply.startswith("Not connected")
        or "[subagent error]" in lowered
        or "unavailable]" in lowered
        or "unreachable" in lowered
    )


async def _run_budget(budget_task: str) -> str:
    return await ask_slot("budget", budget_task)


def _assemble_itinerary(destination: str, parallel: dict, budget: str,
                        money_customs: str = "") -> str:
    """Combine every subagent's reply into one itinerary.

    Money & Customs now gets a section of its own. It previously had none: its
    reply was fetched, folded into Flights' and Restaurants' task strings, and
    printed to DEBUG -- so the one agent whose output never reached the reader
    was the one being used as an input to other agents. A traveller planning a
    trip to Mexico never saw the exchange rate or the tipping norms.

    TODO (ORCHESTRATOR_DESIGN.md, decision #1): once every subagent
    agrees on a single ask-vs-assume policy, this is also where any
    'Assumption:' lines from subagents should probably be surfaced
    together, rather than buried inline per section as they are now.
    """
    sections = ["=== Destination ===\n" + destination]
    if money_customs:
        sections.append("=== Money & Customs ===\n" + money_customs)
    sections += [
        "=== Flights ===\n" + parallel["flights"],
        "=== Restaurants ===\n" + parallel["restaurants"],
        "=== Activities ===\n" + parallel["activities"],
        "=== Budget ===\n" + budget,
    ]
    return "\n\n".join(sections) + "\n"


async def plan_trip(
    task: str,
    origin_country: str = "",
    destination_country: str = "",
    stated_budget: str = "",
) -> str:
    """Top-level entry point: one user request in, one assembled itinerary out.

    Dispatches to one of two orchestrators, selected by TRAVEL_UI_ORCHESTRATOR:

      deterministic (default) -- the fixed pipeline below. No model, so it stays
                                 reproducible, offline-testable and free.
      agent                   -- orchestrator_agent.plan_trip_agentic, a deep
                                 agent that decides who to call and with what.

    Both are kept: the deterministic path is the control condition the agent is
    measured against, not merely a fallback.
    """
    if os.getenv("TRAVEL_UI_ORCHESTRATOR", "deterministic").strip().lower() == "agent":
        # Deferred so the deterministic path never imports deepagents or a model
        # client -- that is what keeps it offline, keyless and free to test.
        # The path insert is required because Chainlit pops sys.path[0] after
        # loading app.py, so the repo root is not importable by the time this
        # runs (ui/agent_seam.py re-runs _ensure_paths every call for the same
        # reason).
        root = os.path.dirname(os.path.abspath(__file__))
        if root not in sys.path:
            sys.path.insert(0, root)
        from orchestrator_agent import plan_trip_agentic

        return await plan_trip_agentic(task, origin_country, destination_country, stated_budget)
    return await _plan_trip_fixed(task, origin_country, destination_country, stated_budget)


async def _plan_trip_fixed(
    task: str,
    origin_country: str = "",
    destination_country: str = "",
    stated_budget: str = "",
) -> str:
    """The original fixed pipeline: Money & Customs, Destination, the parallel
    three, then Budget. Unchanged behaviour."""
    # Money & Customs is the slowest slot by a wide margin -- 27-358s measured
    # on 27 Aug 2026, against single-digit seconds for everything else -- and
    # NOTHING downstream reads its reply. It depends only on the two country
    # strings the UI already parsed, and its result is used once, as its own
    # itinerary section. Awaiting it here put its whole duration on the
    # critical path, ahead of a pipeline that never needed it.
    #
    # Started now, collected at assembly. It takes a permit from the gate like
    # any other slot, so this overlaps rather than oversubscribes; at
    # MAX_CONCURRENCY=1 the total is unchanged, which is the honest cost of a
    # serialised key.
    money_task = None
    if origin_country and destination_country:
        money_task = asyncio.create_task(
            _call_money_customs_context(origin_country, destination_country)
        )


    destination_result = await _run_destination(task)

    # "" rather than the reply: it is not resolved yet, and this parameter is
    # deliberately unused -- see the note in _run_parallel_subagents on why the
    # relay it used to feed was removed.
    parallel_results = await _run_parallel_subagents(task, "")

    budget_task = _build_budget_task(task, destination_result, parallel_results, stated_budget)
    budget_result = await _run_budget(budget_task)

    money_context = await money_task if money_task is not None else ""
    if money_context:
        print(f"\n[DEBUG] Money & Customs said: {money_context}\n")

    return _assemble_itinerary(
        destination_result, parallel_results, budget_result, money_customs=money_context
    )


if __name__ == "__main__":
    # Hello-world check: runs even before any real subagent code exists,
    # since orchestrator_config.get_client() degrades a missing/broken
    # subagent to a plain error message instead of crashing.
    result = asyncio.run(
        plan_trip(
            task="Plan a week in Cancun for someone who likes snorkeling and seafood.",
            origin_country="USA",
            destination_country="Mexico",
            stated_budget="$2000",
        )
    )
    print(result)
