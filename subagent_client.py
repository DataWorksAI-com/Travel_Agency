"""
subagent_client.py -- transport-agnostic interface for calling a subagent.

Same principle used throughout this project (get_exchange_rate's direct-REST-
call-today, MCP-wrapper-later design): the orchestrator's routing/sequencing/
assembly logic should not need to change depending on *how* a subagent is
reached. Only this layer changes.

Two implementations today:

  LocalFunctionClient -- calls a subagent's existing Python callable
      directly (build_agent()/answer(), or Flights' plain dict spec).
      This is what actually runs right now, since every subagent in the
      repo currently lives as a plain Python function, not a separately
      running service.

  SlimSubagentClient -- real SLIM/A2A transport, per agntcy_app_sdk /
      slima2a. This is a STUB: it shows the real wiring shape (based on
      the agntcy/app-sdk and agntcy/slim-a2a-python docs), but it is NOT
      tested here -- it needs a running SLIM node (slim_url) and each
      subagent actually exposed as an A2A server, which is not true yet
      for any subagent in this repo. Fill in once that's ready.

Both implement the same tiny interface: `await client.call(task: str) -> str`.
The orchestrator only ever talks to that interface -- never to a transport
directly -- so swapping Local -> Slim for one subagent, or all of them,
is a one-line change in orchestrator_config.py, not a rewrite.
"""

import asyncio
import inspect
import os
from abc import ABC, abstractmethod
from typing import Callable

# Output ceiling applied to every subagent this seam constructs. See
# LocalFunctionClient.from_dict_spec for why this is the orchestrator's problem
# and not each agent's. Raise it with TRAVEL_UI_MAX_TOKENS if a slot ever
# genuinely needs longer output.
DEFAULT_MAX_TOKENS = int(os.getenv("TRAVEL_UI_MAX_TOKENS", "2048"))


def content_text(content) -> str:
    """Flatten a final message's content down to readable text.

    Lives here, at the lowest layer, because THREE separate places pulled the
    last message off an agent and assumed `.content` was a string. It is not,
    once the model has thinking enabled -- it is a list of content blocks:

        [{"type": "thinking", "thinking": "", "signature": "CAISigIKjgEIERgC..."},
         {"type": "text",     "text": "# Cancun -- 5 nights..."}]

    Each site failed differently on 27 Aug 2026, which is why this took two
    passes to find:

      orchestrator_agent  did str(content) -> a base64 signature was printed at
                          the top of the traveller's itinerary.
      orchestrator_config returned content unchanged -> the seam received a
                          list where it expected a string and reported the
                          Budget slot as "the agent returned an empty reply",
                          which read as the AGENT being broken. It was not.
      subagent_client     did str(content) -> same repr leak as the first, for
                          any dict-spec slot.

    One helper, three callers, so the next model change breaks none of them.

    Only `type == "text"` blocks are kept, in order. Thinking blocks are
    dropped: their text is empty under the default display setting, and the
    reasoning is not the answer. Anything unrecognised falls back to str()
    rather than raising -- these are the functions that must return a reply
    no matter what came back.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if isinstance(block, dict):
                text = block.get("text") or "" if block.get("type") == "text" else ""
            else:
                text = getattr(block, "text", "") if getattr(block, "type", "") == "text" else ""
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)

        # Blocks present, none of them text. Falling through to str() below put
        # the block list's Python repr -- thinking signatures and all -- into the
        # traveller's itinerary, which is the leak this function exists to stop,
        # and the seam did not catch it: _looks_like_error only matches a bracket
        # tag it recognises, so a repr was presented as a genuine reply. Returning
        # "" instead would be caught, but it discards the one diagnostic there is.
        #
        # So: the module's own error shape (see LocalFunctionClient.call), naming
        # the block types and nothing else. The seam reports it as NOT CONNECTED
        # with a readable cause, and no signature blob reaches the reader.
        kinds = ", ".join(
            (b.get("type") if isinstance(b, dict) else getattr(b, "type", "")) or "?"
            for b in content
        ) or "none"
        return f"[subagent error] final message carried no text blocks (only: {kinds})"

    return str(content)


class SubagentClient(ABC):
    """Anything the orchestrator can send one task string to and get one
    self-contained message back from, regardless of transport."""

    @abstractmethod
    async def call(self, task: str) -> str:
        """Send one task string, return one self-contained message.

        Must never raise for an ordinary subagent failure -- subagents in
        this repo already follow a 'never raise, return a message
        describing the problem' contract; a transport-level failure here
        (SLIM unreachable, subagent process down) should be caught and
        turned into a similarly plain-text problem description, not an
        exception the orchestrator has to catch everywhere it calls a
        subagent.
        """
        raise NotImplementedError


class LocalFunctionClient(SubagentClient):
    """Wraps a subagent that already lives as a Python callable in this repo.

    Covers both conventions found across the group's branches:
      - build_agent()/answer(task) style (Budget, Restaurants, Activities)
      - a plain dict spec (Flights' `flights_subagent = {...}`) -- see
        `from_dict_spec()` below for that case, until/unless Flights is
        aligned to the callable convention like everyone else (open
        decision -- see ORCHESTRATOR_DESIGN.md).
    """

    def __init__(self, answer_fn: Callable[[str], str]):
        self._answer_fn = answer_fn

    @classmethod
    def from_dict_spec(cls, spec: dict, model: str = ""):
        """Build a LocalFunctionClient from a plain subagent spec dict
        (Flights' current shape: {"name", "description", "system_prompt",
        "tools"}), by constructing a deep agent from it on the fly.

        Args:
            spec: the subagent's own dict.
            model: optional override, applied over spec["model"]. Which model
                a slot runs on is a deployment decision -- it depends on this
                system's budget, latency and determinism needs, not on the
                agent -- so the orchestrator can set it without editing the
                agent's file. Passed from orchestrator_config.

        TODO: this is a stopgap specifically for Flights' current dict
        contract. If the group decides to align Flights to expose its own
        build_agent()/answer() like every other subagent, this method
        becomes unnecessary and Flights can be wrapped the normal way.
        """
        from deepagents import create_deep_agent

        model = model or spec.get("model", "openrouter:anthropic/claude-sonnet-4.5")

        # max_tokens is capped HERE, not in any subagent's spec.
        #
        # Passing the model as a bare string leaves init_chat_model's own
        # default in place (16384 for most providers). On a free-tier
        # OpenRouter key the affordable max_tokens scales with REMAINING
        # CREDIT, so that default eventually exceeds what the key can afford
        # and the slot dies with "requested up to 16384 tokens, but can only
        # afford 16382". It is a cliff, not a bug: the slot works until
        # cumulative spend crosses a threshold, then stops, and it reads as a
        # broken agent.
        #
        # That is a property of how WE deploy these agents, not of anyone's
        # agent, so it belongs in the orchestrator's seam. The first version of
        # this fix put "max_tokens": 2048 in Flights' own spec, which meant the
        # next slot with the same problem would need another owner's file
        # edited. Every dict-spec slot now gets the cap for free, and a spec
        # can still override it if one genuinely needs longer output.
        #
        # DEFAULT_MAX_TOKENS is generous for this system: every subagent here
        # is asked for a short itinerary-ready message, not an essay.
        from langchain.chat_models import init_chat_model

        model = init_chat_model(
            model, max_tokens=spec.get("max_tokens", DEFAULT_MAX_TOKENS)
        )

        agent = create_deep_agent(
            model=model,
            tools=spec["tools"],
            system_prompt=spec["system_prompt"],
        )

        def _answer(task: str) -> str:
            result = agent.invoke({"messages": [{"role": "user", "content": task}]})
            message = result["messages"][-1]
            return content_text(getattr(message, "content", message))

        return cls(_answer)

    async def call(self, task: str) -> str:
        try:
            # Activities' answer() is a native coroutine function; every
            # other subagent's is an ordinary blocking function. Await the
            # first directly, and push the second to a worker thread so a
            # slow subagent doesn't stall the event loop the other parallel
            # calls are sharing.
            #
            # The coroutine branch is not just a tidiness fix: wrapping an
            # async answer() in asyncio.run() (as orchestrator_config used
            # to) raises RuntimeError when a loop is already running, which
            # is always true here -- _run_parallel_subagents() calls this
            # from inside asyncio.gather().
            if inspect.iscoroutinefunction(self._answer_fn):
                return await self._answer_fn(task)
            return await asyncio.to_thread(self._answer_fn, task)
        except Exception as exc:  # a transport-agnostic client never raises
            return f"[subagent error] {exc}"


class SlimSubagentClient(SubagentClient):
    """STUB -- real SLIM/A2A transport. Not wired to a live subagent yet.

    Based on the agntcy_app_sdk / slima2a client pattern:

        from a2a.client import ClientFactory, minimal_agent_card
        from a2a.types import Message, Part, Role, TextPart
        from slima2a import setup_slim_client
        from slima2a.client_transport import (
            ClientConfig as SRPCClientConfig,
            SRPCTransport,
            slimrpc_channel_factory,
        )

    This needs, at minimum:
      - a running SLIM node (`slim_url`, e.g. http://localhost:46357)
      - the target subagent actually running as its own A2A server,
        registered under `identity` (e.g. "agntcy/travel/flights-agent")
      - a shared secret both sides agree on

    None of that infrastructure exists for this project yet -- every
    subagent is still a plain Python function in the same repo (see
    LocalFunctionClient above). Fill this in once/if the group actually
    stands subagents up as separate services.
    """

    def __init__(self, identity: str, slim_url: str, shared_secret: str):
        self.identity = identity
        self.slim_url = slim_url
        self.shared_secret = shared_secret
        self._client = None  # built lazily on first call

    async def _ensure_client(self):
        if self._client is not None:
            return self._client

        # --- real wiring, per agntcy_app_sdk docs -- UNTESTED, fill in ---
        # from a2a.client import ClientFactory, minimal_agent_card
        # from slima2a import setup_slim_client
        # from slima2a.client_transport import (
        #     ClientConfig as SRPCClientConfig,
        #     SRPCTransport,
        #     slimrpc_channel_factory,
        # )
        #
        # service, slim_app, local_name, conn_id = await setup_slim_client(
        #     namespace="agntcy",
        #     group="travel",
        #     name="orchestrator",
        #     slim_url=self.slim_url,
        # )
        # config = SRPCClientConfig(
        #     supported_transports=["slimrpc"],
        #     slimrpc_channel_factory=slimrpc_channel_factory(slim_app, conn_id),
        # )
        # client_factory = ClientFactory(config)
        # client_factory.register("slimrpc", SRPCTransport.create)
        # card = minimal_agent_card(self.identity, ["slimrpc"])
        # self._client = client_factory.create(card=card)

        raise NotImplementedError(
            "SlimSubagentClient is a design stub -- no SLIM node or A2A "
            "server exists for this subagent yet. Use LocalFunctionClient "
            "until the group actually deploys subagents as separate "
            "services."
        )

    async def call(self, task: str) -> str:
        try:
            client = await self._ensure_client()
            # --- real send, per agntcy_app_sdk docs -- UNTESTED, fill in ---
            # from a2a.types import Message, Part, Role, TextPart
            # request = Message(
            #     role=Role.user,
            #     message_id="msg-001",
            #     parts=[Part(root=TextPart(text=task))],
            # )
            # async for event in client.send_message(request):
            #     ...  # extract final text from the event stream
            raise NotImplementedError
        except Exception as exc:
            return f"[subagent unreachable over SLIM] {exc}"
