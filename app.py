"""Chainlit chat UI for the Destination Agent.

A thin wrapper only. All reasoning lives in destination_agent/, and all data
retrieval in destination_data/ - this file adds no logic of its own beyond
transport between the browser and run_destination_agent().

Launch from the repo root:
    chainlit run app.py -w
"""

# truststore MUST be injected before anything can open an HTTPS connection. The
# agent's own modules do this too, but app.py is the process entry point, so it
# has to happen here first. This network intercepts HTTPS with a certificate
# Windows trusts but Python does not; without the injection, calls hang ~5
# minutes and then fail with no useful error.
import truststore

truststore.inject_into_ssl()

import sys
import traceback
from pathlib import Path

# The agent uses package-absolute imports (destination_agent.*,
# destination_data.*), which only resolve with the repo root on sys.path.
# Anchor to this file's own location so the launch directory does not matter.
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chainlit as cl

from destination_agent.destination_agent import run_destination_agent

WELCOME = (
    "**Travel Destination Assistant**\n\n"
    "Tell me what you are looking for and I will suggest a destination, or name "
    "a place and I will give you its typical climate and public holidays.\n\n"
    "Try:\n"
    "- *I want a warm coastal destination in Asia*\n"
    "- *Tell me about Lisbon*\n\n"
    "Each question is answered on its own, so include the place or preferences "
    "in every message."
)

THINKING = "Looking that up - this usually takes 10-15 seconds."

ERROR_MESSAGE = (
    "Sorry, something went wrong while looking that up. Please try again, or "
    "rephrase your question. (Details were written to the terminal.)"
)

EMPTY_MESSAGE = (
    "The assistant did not return an answer for that. Try rephrasing, or name a "
    "specific destination."
)


def _as_text(value):
    """Normalise an agent reply into displayable text.

    run_destination_agent returns AIMessage.content, which is typed as
    str | list[str | dict]. It is a plain string in practice here, but with
    Anthropic models it can arrive as a list of content blocks - rendering that
    raw would show a Python repr to the user.
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


@cl.on_chat_start
async def on_chat_start():
    await cl.Message(content=WELCOME).send()


@cl.on_message
async def on_message(message: cl.Message):
    question = (message.content or "").strip()

    if not question:
        await cl.Message(content=EMPTY_MESSAGE).send()
        return

    # Placeholder doubles as the loading indicator, then becomes the answer.
    reply = cl.Message(content=THINKING)
    await reply.send()

    try:
        # run_destination_agent is synchronous and blocks for ~10-15s.
        # make_async runs it on a worker thread so the event loop stays free.
        raw_answer = await cl.make_async(run_destination_agent)(question)
        answer = _as_text(raw_answer).strip() or EMPTY_MESSAGE
    except Exception:
        # Never let an exception reach the browser as a crashed session.
        traceback.print_exc()
        answer = ERROR_MESSAGE

    reply.content = answer
    await reply.update()
