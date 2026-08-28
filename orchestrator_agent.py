"""The orchestrator, as a deep agent.

The deterministic pipeline in orchestrator.py calls six subagents in a fixed
order and concatenates their replies. It cannot carry a resolved city forward
(orchestrator.py computes one and drops it), cannot react to an agent that says
"outside my coverage", and has no failure policy. This module replaces that
sequencing with a model that decides who to ask, with what, and in what order.

Two things keep a planning layer from making matters worse:

  1. State travels by code, not by instruction. The model commits the resolved
     facts once via record_trip_state; ask_agent prepends them to every
     subsequent task string. If this were a prompt rule the model could forget
     it, which is the exact bug being fixed.

  2. A deterministic floor. Every call is recorded in a ledger, and after the
     agent finishes, an "Agent status" block is appended for any slot that
     failed or was never called. The model cannot suppress it -- today the
     honest-failure guarantee holds only because _assemble_itinerary is too
     dumb to paraphrase, and handing those strings to a model would reopen it.
"""

import asyncio
import os
import re
from datetime import date

from dotenv import load_dotenv

# Every subagent module calls this on import, but the orchestrator builds its
# own model BEFORE touching any of them -- so without this, anything that isn't
# Chainlit (the jig, a script) gets a ValidationError for a missing key.
load_dotenv()

from langchain.chat_models import init_chat_model
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage

from deepagents import create_deep_agent

from orchestrator import SLOTS, ask_slot
from orchestrator_costs import (
    LODGING, NO_DATA_PHRASES, _AMOUNT, absences, build_budget_brief, held_no_data,
)
from subagent_client import content_text
from ui.agent_seam import LABELS, _looks_like_error

MODEL = os.getenv("ORCHESTRATOR_MODEL", "openrouter:openai/gpt-4o-mini")

# The orchestrator's OWN output ceiling. Was hardcoded at 4000, and that is how
# it took itself out: a live run died with "You requested up to 4000 tokens, but
# can only afford 3682" -- the orchestrator's model, not a subagent's -- after
# five slots had answered but before Budget was called. The whole run was lost
# to a number nobody could change without editing this file.
#
# There is a real tension in this value, so it is a knob rather than a constant:
# too high and a free-tier key refuses the request outright; too low and the
# final itinerary is truncated mid-assembly, which is worse because it looks
# like a content bug. 3000 is a compromise. With TRAVEL_UI_MAX_CONCURRENCY=1
# (the default) the affordable ceiling recovers, because the slots are no longer
# holding credit reservations while this call is made, so 3000 has headroom it
# did not have when 4000 failed.
MAX_TOKENS = int(os.getenv("ORCHESTRATOR_MAX_TOKENS", "3000"))

# Whole-run backoff, not per-call: a deep agent makes many model calls, so a 429
# surfaces from the middle of the graph rather than from one request. Lifted from
# budget_agent_rohan/proposed_envelope_agent/agent.py.
RETRY_BACKOFF = (15, 30, 60)
TRANSIENT = ("429", "rate", "too many requests", "timeout", "overloaded")

# create_deep_agent's tools= is additive and never removes a built-in, so the
# agent otherwise gets execute/write_file/delete for free. This repo already has
# agents that overwrite shared corpus files; an orchestrator with a shell is not
# a tidiness question. HarnessProfile(excluded_tools=...) does this too, but its
# registry is global and keyed by provider, which would also reshape Flights.
_BUILTINS = frozenset(
    {"ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute", "delete", "task"}
)


class _OnlyOurTools(AgentMiddleware):
    """Hide the built-in filesystem/shell suite from the model, and refuse it.

    Two hooks, because hiding alone was one layer short of the intent above.
    wrap_model_call edits what the model is OFFERED; the graph's ToolNode is
    built from the full list and still had all nine registered:

        ask_agent, ask_agents, record_trip_state,
        delete, edit_file, execute, glob, grep, ls, read_file, task, write_file

    So a call the model was never shown -- hallucinated, replayed from history,
    or carried in on injected text -- would still have executed. No observed
    case, and a model cannot ordinarily pick what it is not offered. This is
    defence in depth on a path that should not exist, which is the right
    posture for `execute` and `delete` sitting next to agents that write to a
    shared corpus.

    Costs nothing on the happy path: none of our three tool names is in
    _BUILTINS, so _refuse returns None and the handler runs untouched.
    """

    def wrap_model_call(self, request, handler):
        return handler(request.override(tools=self._keep(request.tools)))

    async def awrap_model_call(self, request, handler):
        return await handler(request.override(tools=self._keep(request.tools)))

    def wrap_tool_call(self, request, handler):
        return self._refuse(request) or handler(request)

    async def awrap_tool_call(self, request, handler):
        return self._refuse(request) or await handler(request)

    @staticmethod
    def _keep(tools):
        return [t for t in tools if getattr(t, "name", None) not in _BUILTINS]

    @staticmethod
    def _refuse(request):
        """A ToolMessage instead of an execution, or None to let it through."""
        call = getattr(request, "tool_call", None) or {}
        name = call.get("name")
        if name not in _BUILTINS:
            return None
        return ToolMessage(
            content=(
                f"{name} is not available to the orchestrator. You have exactly "
                f"three tools: ask_agent, ask_agents, record_trip_state."
            ),
            tool_call_id=call.get("id", ""),
            name=name,
            status="error",
        )


SYSTEM_PROMPT = f"""You are the orchestrator for a travel-planning system. You do
not plan trips yourself. You delegate to six specialist agents and assemble what
they return.

The agents, reachable with ask_agent(slot, task):

  destination    resolves a city from a name or vague preferences; climate, holidays
  flights        live prices (cached up to 7 days -- not live availability)
  restaurants    dining; holds records for 6 Caribbean cities only
  activities     things to do; holds 6 temperate cities only
  budget         feasibility and totals; tropical destinations only
  money_customs  exchange rate, tipping, haggling; 17 countries only

HOW TO WORK

1. ALWAYS call destination first, even when the traveller named the city. It is
   the only agent that can turn "somewhere warm" into a place, and it also
   returns climate, public holidays, beaches and local detail that nothing else
   provides. Knowing the city's name is not a reason to skip it.
2. Then call record_trip_state with what you now know. Everything you record is
   automatically prepended to every later ask_agent call, so the other agents
   can see the resolved city. Do this before calling anyone else.
3. Then ask flights, restaurants, activities and money_customs with a SINGLE
   ask_agents call, passing all four slots and their tasks together. None of
   them depends on another's answer, and ask_agents runs them at the same time,
   which is most of the difference between a fast run and a slow one. A
   traveller needs the exchange rate and tipping norms, so do not skip
   money_customs.
4. Call budget LAST, on its own, only after flights, restaurants and activities
   have actually returned. It prices what they found. Do not include it in the
   same batch of tool calls as them -- it will have nothing to work from.
5. Your final message is a SHORT SUMMARY, not the itinerary. Each agent's own
   reply is appended below it verbatim, under its own heading, automatically --
   so do NOT write "=== Name ===" sections and do not restate what an agent
   said. Write a few sentences that only an orchestrator can write: how the
   pieces fit, what the traveller should decide, and anything one agent's
   answer implies for another's. If two agents disagree, or one reports a gap
   that undercuts another's answer, say so -- that is the part no single agent
   can see.

RULES

- Report what the agents returned. Do not add prices, restaurants, activities or
  customs advice from your own knowledge. If a figure did not come from an agent,
  do not state it.
- If an agent says a destination is outside its coverage, that is a final answer
  and a useful one. Say so plainly in your summary. Do NOT retry it with a
  different spelling, a nearby city, or a rephrased task -- the answer will not
  change, and you will waste the run.
- If an agent reports it did not run, say so in your summary and say what the
  itinerary is therefore missing. Never fill the gap from your own knowledge.
- Never speak for an agent you did not call, and never attribute a figure or a
  claim to an agent that did not make it. Only agents that actually replied get
  a section, and their sections are their own words -- yours is the summary.
- Call each agent once. Call one a second time only if you have genuinely new
  information for it, such as a city that agent had not been given yet.
- Do not ask the user follow-up questions. Work with what you have and state your
  assumptions.
- Trip details carries 'travel month' as an explicit YYYY-MM whenever the traveller
  named one. Use that value verbatim for anything date-related. Do NOT work out a
  year yourself, and never send a bare month name to an agent that searches by date.

Valid slot names are exactly: {", ".join(SLOTS)}.
"""


_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")

_MONTH_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\b(?:\s+(\d{4}))?", re.I
)


def resolve_travel_month(task: str, today=None) -> str:
    """The month the traveller meant, as YYYY-MM, or "" if they named none.

    Carrying today's date was not enough. On the 14:0x run the task said
    "today's date: 2026-08-27" and the orchestrator still instructed Flights to
    search "September 2024" -- the fact was present and the model did the
    arithmetic wrong anyway. A weaker model will keep doing that, and the
    failure is invisible: the agent dutifully reports no cached data for a route
    that has fares.

    So the resolved month becomes a FACT rather than a derivation. Same
    principle as record_trip_state and today's date: anything a model can get
    wrong silently should travel by code.

    A bare month resolves to its NEXT occurrence -- "in September" said in
    August 2026 means 2026-09, said in October 2026 means 2027-09. An explicit
    year is honoured as written, even a past one, because that is a statement
    rather than an omission.
    """
    today = today or date.today()
    match = _MONTH_RE.search(task or "")
    if not match:
        return ""
    month = _MONTHS.index(match.group(1).lower()) + 1
    if match.group(2):
        return "%04d-%02d" % (int(match.group(2)), month)
    year = today.year if month >= today.month else today.year + 1
    return "%04d-%02d" % (year, month)


def _new_run(base_facts=None, stated_budget="", request=""):
    """Fresh per-run state and tools, closed over rather than global.

    Chainlit serves concurrent sessions; module-level state would let two runs
    write into each other's ledger.
    """
    state: dict[str, str] = {}
    ledger: dict[str, list[str]] = {}

    async def ask_agent(slot: str, task: str) -> str:
        """Ask one specialist agent to do one thing, and return its reply.

        Args:
            slot: one of destination, flights, restaurants, activities, budget,
                money_customs.
            task: a self-contained instruction. The agent shares no context with
                you or with the other agents, so everything it needs must be in
                this string.

        A reply saying the destination is outside the agent's coverage is final.
        Do not retry it with a different spelling or a nearby place.
        """
        if slot not in SLOTS:
            return f"'{slot}' is not an agent. Valid slots: {', '.join(SLOTS)}."
        if any(_is_failure(r) for r in ledger.get(slot, [])):
            # orchestrator_config caches a broken client for the life of the
            # process, so a retry here returns the same failure. Say so instead
            # of letting the model spend its loop rediscovering it.
            return f"The {slot} agent already failed this run and will not recover. Do not call it again."
        # Today's date travels with every task, by code.
        #
        # A traveller writes "in September" and means the next one. A model has
        # no reliable idea what year it is: on 27 Aug 2026 the Flights slot
        # searched 2025-09 and reported "no cached flight data" for a route that
        # had three fares from $154. That reads as an agent with no coverage. It
        # was a year off. Verified against the live API -- 2026-09 returns data,
        # 2025-09 returns none, same route, same call.
        #
        # This goes in the task string rather than the system prompt for the
        # same reason the trip state does: a prompt rule can be forgotten, and
        # the agent on the other side shares no context with us.
        facts = {"today's date": date.today().isoformat()}
        facts.update(base_facts or {})
        facts.update({k.replace("_", " "): v for k, v in state.items()})
        detail = "\n".join(f"{k}: {v}" for k, v in facts.items())
        task = f"Trip details:\n{detail}\n\n{task}"
        if slot == "budget":
            # Budget must see the others' replies, and it cannot if the model
            # emits every tool call in one parallel batch -- observed live: all
            # six fired together, the ledger was still empty, and Budget billed
            # $425 for a flight Flights had just reported it could not find.
            # Refusing here forces the second, informed call; the model is free
            # to call budget again once the others have returned.
            pending = [s for s in ("flights", "restaurants", "activities") if s not in ledger]
            if pending:
                return (
                    f"Budget cannot run yet: {', '.join(pending)} have not returned. "
                    f"Budget prices what the other agents found, so calling it now would "
                    f"produce invented figures. Wait for their replies, then call budget again."
                )
            # Budget receives DECIDED INPUTS, not the other agents' replies.
            #
            # This used to concatenate every reply into the task string. That
            # stopped Budget inventing a $425 flight, but it made the
            # orchestrator a relay between subagents rather than the thing that
            # decides -- which is not the agreed architecture, and is
            # ORCHESTRATOR_DESIGN.md #5, "the biggest unresolved gap in the
            # whole skeleton". orchestrator_costs now extracts verified line
            # items and, just as importantly, states which categories have no
            # figure and why. No subagent prose reaches another subagent.
            # The TRAVELLER'S words, not the model's composition of them.
            #
            # Whatever the model wrote here went in above the verified ledger and
            # undid both of this module's guarantees. Captured 28 Aug 2026: "...
            # Flights: B6 at $538 per person. Restaurants: mix of Champers ($95
            # for two) ... Determine if this fits the budget and provide cost
            # breakdown." That relays three agents' figures as unverified prose
            # -- the relaying the comment above says does not happen -- and
            # instructs Budget to produce the total rule 5 tells it to withhold.
            # Budget resolved that contradiction toward the instruction.
            #
            # The deterministic path already passes the traveller's request here
            # and does not have the problem, because a traveller states a trip,
            # not a method. Falls back to the model's text only if the request
            # never arrived, since orchestrator.py:285 records what Budget does
            # with no request at all: it invented a 3-day trip.
            task = build_budget_brief(
                task=request or task,
                replies={s: r[-1] for s, r in ledger.items() if s != "budget"},
                is_failure=_is_failure,
                # The VALUE guard in build_budget_brief is a no-op without
                # this, so the traveller's own budget was costable here even
                # though the deterministic path was protected. record_trip_state
                # is the fallback when the UI parsed no budget but the model did.
                stated_budget=stated_budget or state.get("total_budget", ""),
                trip_facts=(
                    "\n".join(f"{k.replace('_', ' ')}: {v}" for k, v in state.items())
                    if state else ""
                ),
            )
        reply = await ask_slot(slot, task)
        ledger.setdefault(slot, []).append(reply)
        return reply

    async def ask_agents(slots: list[str], tasks: list[str]) -> str:
        """Ask several INDEPENDENT agents at the same time, and return all replies.

        Args:
            slots: the agents to ask, e.g. ["flights", "restaurants", "activities",
                "money_customs"].
            tasks: one self-contained instruction per slot, in the same order.

        Use this for flights, restaurants, activities and money_customs, which do
        not depend on each other's answers. It is much faster than asking them one
        at a time. Do NOT put budget in here -- it prices what the others found and
        must be asked on its own, afterwards.
        """
        # Parallelism is enforced HERE rather than asked for in the prompt.
        # Measured on three live runs: told to issue the four independent calls as
        # one batch, the model mostly emitted them one at a time -- run 3 finished
        # with slot wall-clock 100.7s against a 115.3s total, i.e. no overlap at
        # all. Whether a run is parallel was therefore a property of the model's
        # mood, which is exactly the kind of thing this module already refuses to
        # leave to a model (see resolve_travel_month and record_trip_state).
        #
        # Every guard still applies: this only fans out over ask_agent, so the
        # ledger, the failure memo, the trip-state facts, the budget ordering
        # refusal, the concurrency gate and the credential scrub are unchanged.
        # TRAVEL_UI_MAX_CONCURRENCY still caps how many actually run at once.
        if len(slots) != len(tasks):
            return (f"Mismatched call: {len(slots)} slots but {len(tasks)} tasks. Pass one task per slot, in the same order.")
        if not slots:
            return "No slots given."
        replies = await asyncio.gather(*(ask_agent(s, t) for s, t in zip(slots, tasks)))
        return "\n\n".join(f"=== {s} ===\n{r}" for s, r in zip(slots, replies))

    def record_trip_state(
        destination_city: str = "",
        destination_country: str = "",
        origin_city: str = "",
        origin_country: str = "",
        nights: str = "",
        travelers: str = "",
        total_budget: str = "",
    ) -> str:
        """Record the resolved trip facts. Call this once the destination is known.

        Everything recorded here is prepended to every later ask_agent call, so
        this is how the resolved city reaches the other agents. Omit anything you
        do not know rather than guessing.
        """
        # Listed explicitly rather than via locals(): `state` is a closure
        # variable, so locals() includes it and the dict ends up containing
        # itself, which then gets rendered into every downstream prompt.
        state.update({k: v for k, v in {
            "destination_city": destination_city,
            "destination_country": destination_country,
            "origin_city": origin_city,
            "origin_country": origin_country,
            "nights": nights,
            "travelers": travelers,
            "total_budget": total_budget,
        }.items() if v})
        return f"Recorded: {state}"

    return state, ledger, [ask_agent, ask_agents, record_trip_state]


def _is_failure(reply: str) -> bool:
    """A slot that did not run. Reuses the seam's own detection."""
    return reply.startswith("Not connected") or _looks_like_error(reply)


# "Ran correctly but holds nothing for this request" -- NOT the same as a
# failure. "No flights found from BOS to AUA in September" is a correct, useful
# answer; the problem is what happens downstream of it. The phrase list lives in
# orchestrator_costs (imported as held_no_data / NO_DATA_PHRASES) because the
# budget brief needs exactly the same distinction, and two copies would drift.
_held_no_data = held_no_data

# A currency amount: "$850", "1,400 USD", "MXN 300". Deliberately narrow --
# a bare number is not evidence of a price, and a false positive here would
# attach a caveat to an itinerary that does not need one.
_CURRENCY = re.compile(
    r"[$£€]\s?\d|\b\d[\d,]*(?:\.\d{2})?\s?(?:USD|EUR|GBP|MXN|JPY|THB)\b",
    re.IGNORECASE,
)


def _unsourced_figures_note(final: str, ledger: dict[str, list[str]]) -> str:
    """Name the slots that supplied no figures, when the itinerary quotes some.

    THE BUG THIS EXISTS FOR, observed live: Flights reported it found no prices
    and Activities did not run at all, and Budget then billed "$850
    (estimated)" for flights and "$200 (estimated)" for activities, producing
    "Total $2,310 -- comfortably feasible". It labelled both as estimates in
    its own table, but the headline a reader takes away is the total, and the
    total is built on numbers no agent produced. Lodging was $400 with no
    lodging agent in the system at all.

    The jig measures this: grounding drops from 1.0 on the deterministic path
    to 0.75 under the agent.

    Detection, not attribution. Working out WHICH figure came from which agent
    would mean parsing the model's prose, and getting that wrong would either
    miss the real case or slander a correctly-sourced number. Instead this
    states a fact that is always true and always checkable: these slots
    returned no figures, so any figure here attributed to them is unsourced.
    Appended after the model has finished, for the same reason the rest of the
    floor is -- so it cannot be paraphrased away.

    THE SECOND BUG, observed on run 6 of 27 Aug 2026 with ALL SIX SLOTS GREEN:
    the lodging sentence used to live inside the slot list, so it only fired
    when some slot had failed. On a fully successful run the list is empty, the
    whole note was suppressed, and the orchestrator wrote, unqualified:

      "you have approximately $376 per night available for accommodation for
       both travelers ($188 per person/night), which comfortably covers
       mid-range to nice hotels in Cancun's hotel zone"

    No agent prices lodging -- that is true on every run, not only on a broken
    one -- and the second half is a market-quality claim on top of the invented
    figure. So the two halves are now gated differently. Naming a slot as
    unsourced when it answered WOULD be a false positive, and stays gated. The
    lodging sentence is unconditionally true whenever money is on the page, so
    it is no longer conditional on someone else having failed.
    """
    if not _CURRENCY.search(final):
        return ""

    # absences(), not a loop of our own. This used to hand-roll the same three
    # branches -- not called / failed / held_no_data -- and orchestrator_costs
    # has had a fourth one all along:
    #
    #     elif not extract_line_items(slot, reply): "answered but published no prices"
    #
    # That branch is derived by code from the reply, so it holds when the phrase
    # list misses. Run 8 of 27 Aug 2026 is the case: Activities answered
    # "Cancun ... lacks the necessary details in the local data" and improvised.
    # No phrase in NO_DATA_PHRASES matches that -- the two that WOULD match are
    # literal strings the agent's TOOLS return, and the seam only ever sees
    # gpt-4o-mini's paraphrase of them, which is reworded every run. The local
    # copy scored it healthy and named nobody; absences() names it.
    #
    # Budget drops out for free: it is not in PRICED_SLOTS, so the explicit skip
    # this loop needed is gone. So do destination and money_customs, which is
    # correct here -- neither produces a trip cost by design (orchestrator_costs
    # :50, an exchange rate is a ratio), and if either breaks, the Agent status
    # block above names it.
    gaps = absences({s: r[-1] for s, r in ledger.items()}, _is_failure)

    note = "\n\n=== Unsourced figures ===\n"
    if gaps:
        note += "\n".join(f"- {LABELS[g['source']]}: {g['reason']}." for g in gaps)
        note += (
            "\n\nAny cost above for the categories listed came from no agent in this "
            "system. Treat those numbers as unverified, and do not read the total as "
            "priced.\n"
        )
    return note + (
        "No agent in this system prices lodging. Any accommodation or per-night "
        "figure above came from no agent, and so does any statement about what "
        "such a figure will or will not cover."
    )


# A correction an agent stated about its OWN answer -- "Note: I interpreted X as
# Y", "Assumption: ...". Measured 27 Aug 2026, Rome run: money_customs replied
# 'Note: I interpreted "Italy" as Germany.' and the assembling model rewrote the
# section as Italy's customs with that line deleted, then added "Not expected in
# Italy" on its own authority. Same reasoning as the failure notes below --
# a caveat that lives only in prose is one the model is free to drop.
_CAVEAT_RE = re.compile(r"^[ \t]*(?:Note|Assumption|Adjusted)[ \t]*:.*", re.M)


def _stated_caveats(final: str, ledger: dict[str, list[str]]) -> str:
    lowered = final.lower()
    # ponytail: exact-substring containment, so a caveat the model KEPT but
    # reworded gets repeated here. Duplicated is the safe direction; tighten to
    # fuzzy matching only if the repetition actually bothers a reader.
    notes = [
        f"- {LABELS[slot]}: {line.strip()}"
        for slot in SLOTS
        for reply in ledger.get(slot, [])
        for line in _CAVEAT_RE.findall(reply)
        if line.strip().lower() not in lowered
    ]
    return "\n\n=== Stated by the agents ===\n" + "\n".join(notes) if notes else ""


# The model's own writing keeps its own heading, and every agent section below
# it is that agent's reply verbatim.
#
# Measured 28 Aug 2026, with the model writing the sections itself: Budget
# crashed and returned only "Not connected -- the Budget agent did not run",
# and the === Budget === section still read "Flights: $1,076 ... approximately
# $385 per night for lodging". Every figure invented, under a heading naming an
# agent that produced nothing, directly above the floor's own notice that no
# agent prices lodging. Earlier the same day: Germany's tipping norms relabelled
# as Italy's, and Budget's "INCOMPLETE BUT PROMISING" rewritten to "FEASIBLE".
#
# Those are all one failure -- the model was authoring text under someone else's
# name. Guards downstream of that argue with the output after the fact, and the
# floor already proved a correct notice at the bottom does not undo a confident
# claim at the top. So the model no longer writes the sections. It still decides
# everything that makes it an orchestrator: who to call, with what, in what
# order, and when to stop. It just no longer speaks for them.
_SUMMARY_HEADING = "=== Summary (orchestrator) ==="

# The summary is the one place a model still writes freely, and lodging is where
# it reaches. Measured across 28 Aug 2026: "$385 per night for lodging",
# "~$300-400/night", "$70-120/night for guesthouses", "Expect $350-$1,500 for 5
# nights" -- every one of them on a run where the itinerary also said, correctly,
# that no agent prices lodging. So that single claim is barred outbound, the same
# way _NOT_A_PRICE bars it inbound.
#
# No exemption for "leaving $X for accommodation". An earlier version spared a
# line if it read like an allowance rather than a quote, to save the sentence
# "leaving $1,924 for accommodations, meals and activities". The very next live
# run wrote "leaving you $1,924 ... allocate roughly $350-600 for budget-friendly
# guesthouses, leaving $1,300-1,575 for meals" -- an invented nightly range that
# walked through on the word "leaving". Two keyword signals with one vetoing the
# other is a classifier, and a classifier leaks. A dropped good sentence costs a
# rephrase; a missed one puts an unsourced price in a customer's itinerary.
#
# Sentence, not line: models write the summary as one paragraph, so line
# granularity would delete all of it over a single clause.
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


# SYSTEM_PROMPT rule 5 tells the model its final message is a summary and that
# the sections are appended for it. Measured 28 Aug 2026: it wrote them anyway,
# as "=== destination ===" ... "=== money_customs ===", restating every agent
# above the real ones. Asking was worth a try; the summary is now simply
# everything before the model's first heading.
_HEADING = re.compile(r"^\s*#*\s*===", re.M)


def _bounded(summary: str) -> tuple[str, bool]:
    """Drop sentences quoting a lodging price. Returns (summary, dropped_any)."""
    summary = _HEADING.split(summary, maxsplit=1)[0]
    kept, dropped = [], False
    for line in summary.splitlines():
        parts = [
            s for s in _SENTENCE.split(line)
            # ponytail: regex sentence split, so "approx." or "St. Lucia" ends a
            # sentence early. Costs at most a slightly shorter drop.
            if not (LODGING.search(s) and _AMOUNT.search(s))
        ]
        dropped = dropped or len(parts) != len(_SENTENCE.split(line))
        kept.append(" ".join(parts))
    return "\n".join(kept).strip(), dropped


def _itinerary(summary: str, ledger: dict[str, list[str]]) -> str:
    summary, dropped = _bounded(summary)
    if dropped:
        summary += (
            "\n\n(A line quoting a price for lodging was removed from this "
            "summary: no agent in this system prices lodging, so the figure "
            "came from no source.)"
        )
    sections = [
        f"{_SUMMARY_HEADING}\n{summary.strip()}\n\n"
        "The sections below are each agent's own reply, unedited."
    ]
    sections += [
        f"=== {LABELS[slot]} ===\n{ledger[slot][-1].strip()}"
        for slot in SLOTS
        if ledger.get(slot) and ledger[slot][-1].strip()
    ]
    return "\n\n".join(sections)


def _floor(final: str, ledger: dict[str, list[str]]) -> str:
    """Append what the model left out. Concatenated after the fact, so the model
    cannot paraphrase a failure away or quietly drop an agent."""
    lowered = final.lower()
    notes = []
    for slot in SLOTS:
        replies = ledger.get(slot)
        label = LABELS[slot]
        if not replies:
            notes.append(f"- {label}: not called, so this itinerary contains no {label} data.")
        elif _is_failure(replies[-1]) and not (
            # Checked per slot, not globally: one reported failure must not
            # suppress the note for a different slot the model stayed quiet about.
            "not connected" in lowered and label.lower() in lowered
        ):
            notes.append(f"- {label}: did not run. {replies[-1].splitlines()[0]}")

    if notes:
        final = final + "\n\n=== Agent status ===\n" + "\n".join(notes)

    # Appended last, and separately: a slot can be perfectly healthy and still
    # have supplied no figures ("No flights found for these dates"), which the
    # Agent status block above deliberately says nothing about.
    return final + _stated_caveats(final, ledger) + _unsourced_figures_note(final, ledger)


# One definition, three callers -- see subagent_client.content_text for the
# three different ways this same assumption failed on 27 Aug 2026.
_content_text = content_text


async def plan_trip_agentic(
    task: str,
    origin_country: str = "",
    destination_country: str = "",
    stated_budget: str = "",
) -> str:
    """Same signature and return type as orchestrator.plan_trip."""
    travel_month = resolve_travel_month(task)
    # Everything the UI already resolved deterministically travels as a FACT,
    # prepended to every task by ask_agent -- same principle as travel month and
    # today's date. Previously these appeared only in the model's own prompt, so
    # they reached the agents only if the model remembered to call
    # record_trip_state; anything it records still overrides these.
    base_facts = {k: v for k, v in {
        "travel month": travel_month,
        "origin country": origin_country,
        "destination country": destination_country,
        "total budget": stated_budget,
    }.items() if v}
    state, ledger, tools = _new_run(base_facts, stated_budget, request=task)
    agent = create_deep_agent(
        model=init_chat_model(MODEL.strip(), max_tokens=MAX_TOKENS),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[_OnlyOurTools()],
    )

    request = "\n".join(
        p for p in (
            f"Traveller's request: {task}",
            f"Origin country: {origin_country}" if origin_country else "",
            f"Destination country: {destination_country}" if destination_country else "",
            f"Stated budget: {stated_budget}" if stated_budget else "",
        ) if p
    )

    for attempt, wait in enumerate((*RETRY_BACKOFF, None)):
        try:
            result = await agent.ainvoke({"messages": [{"role": "user", "content": request}]})
            break
        except Exception as exc:
            if wait is None or not any(t in str(exc).lower() for t in TRANSIENT):
                return _floor(f"The orchestrator could not complete this request: {exc}", ledger)
            print(f"[orchestrator] transient failure, retry {attempt + 1} in {wait}s: {exc}")
            await asyncio.sleep(wait)

    message = result["messages"][-1]
    return _floor(_itinerary(_content_text(getattr(message, "content", message)), ledger), ledger)
