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
from abc import ABC, abstractmethod
from typing import Callable


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
    def from_dict_spec(cls, spec: dict):
        """Build a LocalFunctionClient from a plain subagent spec dict
        (Flights' current shape: {"name", "description", "system_prompt",
        "tools"}), by constructing a deep agent from it on the fly.

        TODO: this is a stopgap specifically for Flights' current dict
        contract. If the group decides to align Flights to expose its own
        build_agent()/answer() like every other subagent, this method
        becomes unnecessary and Flights can be wrapped the normal way.
        """
        from deepagents import create_deep_agent

        agent = create_deep_agent(
            model=spec.get("model", "openrouter:anthropic/claude-sonnet-4.5"),
            tools=spec["tools"],
            system_prompt=spec["system_prompt"],
        )

        def _answer(task: str) -> str:
            result = agent.invoke({"messages": [{"role": "user", "content": task}]})
            message = result["messages"][-1]
            content = getattr(message, "content", message)
            return content if isinstance(content, str) else str(content)

        return cls(_answer)

    async def call(self, task: str) -> str:
        try:
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
