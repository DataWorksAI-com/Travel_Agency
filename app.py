"""Chainlit chat UI for the whole travel pipeline.

A thin wrapper only. This file contains no planning logic and knows nothing
about any individual agent. It calls exactly one thing --
orchestrator.plan_trip (orchestrator.py:146) -- and renders what comes back.

There is deliberately NO reference to a stand-in, a fake or a dummy anywhere
below. Whether a given agent is the real one or a deterministic stand-in is
decided one layer down, at the seam (ui/agent_seam.py), by rebinding
orchestrator.get_client. That is what makes "swap in the real agents" a
config change rather than a UI rewrite.

Launch from the repo root:
    chainlit run app.py -w
"""

# truststore MUST be injected before anything can open an HTTPS connection.
# The agents' own modules do this too, but app.py is the process entry point,
# so it has to happen here first. This network intercepts HTTPS with a
# certificate Windows trusts but Python does not; without the injection,
# calls hang ~5 minutes and then fail with no useful error.
import truststore

truststore.inject_into_ssl()

import sys
import traceback
from pathlib import Path

# The orchestrator and the agents use package-absolute imports, which only
# resolve with the repo root on sys.path. Anchor to this file's own location
# so the launch directory does not matter.
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chainlit as cl

from orchestrator import plan_trip
from ui.agent_seam import DIRECT, DUMMY, LABELS, REAL, install_seam
from ui.request_parse import describe, parse_request

WELCOME = (
    "**Travel Planning Assistant**\n\n"
    "Describe the trip you want and the coordinator will run the whole "
    "pipeline: destination, money & customs, flights, restaurants, "
    "activities, then budget.\n\n"
    "Try:\n"
    "- *Plan a week in Aruba from Boston, budget $3000*\n"
    "- *Plan a 4 night trip to Barbados for 2 people who like snorkeling "
    "and seafood, budget $5000*\n\n"
    "Include the destination, where you are leaving from, and a budget -- "
    "each message is planned on its own."
)

THINKING = "Running the pipeline - each agent appears below as it finishes."

ERROR_MESSAGE = (
    "Sorry, something went wrong while planning that trip. Please try again, "
    "or rephrase your request. (Details were written to the terminal.)"
)

EMPTY_MESSAGE = (
    "I did not get a plan back for that. Try naming a destination, where you "
    "are travelling from, and a budget."
)

# How the seam's effective mode is labelled in the step header. The UI knows
# these are labels; it does not know how the seam decides between them.
MODE_LABEL = {
    REAL: "live agent",
    DIRECT: "live tools, no model",
    DUMMY: "sample data",
}


def _as_text(value):
    """Normalise a reply into displayable text.

    plan_trip returns a str today (orchestrator.py:132-143 builds one), but
    an agent reached through a real client can hand back AIMessage.content,
    typed str | list[str | dict]. Rendering that raw would show a Python
    repr to the user.
    """
    if isinstance(value, str):
        return value

    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "\n".join(part for part in parts if part)

    if value is None:
        return ""

    return str(value)


async def _on_agent_done(slot, effective_mode, task, reply):
    """Seam `after` hook: render one finished agent as a Chainlit step.

    The step is opened and closed inside this coroutine rather than spanning
    the agent call, because Flights/Restaurants/Activities run concurrently
    (orchestrator.py:76-80) and Chainlit tracks step nesting in a contextvar
    -- three steps held open across that gather would nest arbitrarily.
    Closing each one here keeps the transcript flat and ordered by
    completion.
    """
    label = LABELS.get(slot, slot.title())
    suffix = MODE_LABEL.get(effective_mode, effective_mode)

    async with cl.Step(name=f"{label} ({suffix})", type="tool") as step:
        step.input = task
        step.output = _as_text(reply)


# Installed once, at import, for the whole process. `before` is left unset:
# the step is emitted on completion (see _on_agent_done).
AGENT_MODES = install_seam(after=_on_agent_done)


def _modes_summary() -> str:
    lines = []
    for slot, label in LABELS.items():
        mode = AGENT_MODES.get(slot, DUMMY)
        lines.append(f"- {label}: {MODE_LABEL.get(mode, mode)}")
    return "\n".join(lines)


@cl.on_chat_start
async def on_chat_start():
    await cl.Message(content=WELCOME).send()
    await cl.Message(
        content="**Agents currently connected**\n\n" + _modes_summary()
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    request = (message.content or "").strip()

    if not request:
        await cl.Message(content=EMPTY_MESSAGE).send()
        return

    # Placeholder doubles as the loading indicator, then becomes the answer.
    reply = cl.Message(content=THINKING)
    await reply.send()

    try:
        # plan_trip takes four separate arguments, not one free-text line
        # (orchestrator.py:146-151), so the request is split here and the
        # split is shown, not hidden -- a bad parse should look like one.
        parsed = parse_request(request)

        async with cl.Step(name="Request parsed", type="tool") as step:
            step.input = request
            step.output = describe(parsed)

        answer = _as_text(
            await plan_trip(
                task=parsed["task"],
                origin_country=parsed["origin_country"],
                destination_country=parsed["destination_country"],
                stated_budget=parsed["stated_budget"],
            )
        ).strip() or EMPTY_MESSAGE
    except Exception:
        # Never let an exception reach the browser as a crashed session.
        traceback.print_exc()
        answer = ERROR_MESSAGE

    reply.content = answer
    await reply.update()
