# UI plan — customer path and developer observability

Rohan Shivakumar · ALY6980 capstone · DataWorksAI · written 2026-08-21

**How to read this.** Claim tags follow `integration_audit.md`:
**[V]** verified by reading/running code · **[W]** verified against an external
source, URL and fetch date given · **[I]** inference, reasoning not evidence.

Repo line references are to the merged sandbox tree at
`C:\Users\rohan\Documents\wt-sandbox` (`sandbox-integration` = `origin/main` +
`exchange_rate_emily` + `budget_cost_rohan` + `activities_limeng`). **Nothing in
this plan can be built or tested on `exchange_rate_emily`** — that branch is 65
commits behind `main` and contains none of the agent packages
(`integration_audit.md` §2.2 item 5). Branch to work on: a feature branch off
`main`, or off `sandbox-integration` if you want the unmerged agents live.

---

## 0. Corrections to the brief

Four premises in the task as given are wrong or imprecise. They change the plan,
so they come first.

**0.1 — `make_async` is at `app.py:105`, not `:98`. [V]**
The file is 113 lines as stated. `app.py:98` is the comment
`# Placeholder doubles as the loading indicator, then becomes the answer.`
The single-placeholder-message pattern spans `:99-113`.

**0.2 — `app.py` is Joel's file, not Emily's. [V]**

```
git log --format='%an | %ad | %s' --date=short -- app.py
  Joel Thomas Zachariah | 2026-08-19 | Add Chainlit UI, relative climate
                                       thresholds, non-destructive corpus
                                       build, and agent-layer fixes
```

`orchestrator.py`, `subagent_client.py` and `orchestrator_config.py` are all
`ejmachad` (Emily), 2026-08-18. `orchestrator_config.py` has one later commit
from `vrushhtii`. So the "Emily must approve" boundary covers the orchestrator
seam but **not** the UI file — the UI file needs Joel's sign-off instead. This
matters because the brief's plan assumed one gatekeeper and there are two.

**0.3 — the developer view is blocked by something worse than "no event
stream": there is no call site to attach callbacks to. [V]**

Every agent builds its own graph and calls `.invoke()` *inside its own module*,
and every entry point takes exactly one string:

| agent | entry point | invoke site | takes `config`? |
|---|---|---|---|
| Destination | `destination_agent/destination_agent.py:460` `run_destination_agent(user_query: str) -> str` | `:472` | no |
| Money & Customs | `money_customs_agent.py` `answer(task)` | `:129` | no |
| Money & Customs (dup) | `agent.py` `answer(task)` | `:102` | no |
| Budget (Shashank) | `budget_agent/agent.py` `build_agent()` | called at `orchestrator_config.py:72` | no |
| Budget (Rohan) | `budget_agent_rohan/budget_agent/agent.py:269` | `:292` | no |
| Activities | `activities-agent-limeng/activities_agent.py:249` `answer` (async) | `:255` | no |
| Restaurants | `restaurant_agent/restaurant_agent_ollama.py:316` | `:651` | no |
| Flights | `flights_agent.py:166` — **a dict, not a callable** | graph built at `subagent_client.py:80`, invoked at `:87` | **injectable** |

Consequence: the standard advice ("pass `config={"callbacks":[handler]}` at the
call site") is **not available for five of six agents**, because the orchestrator
never touches their graphs. Flights is the lone exception — it exports
`flights_subagent = {...}` (`flights_agent.py:166`) and the graph is constructed
at the seam by `LocalFunctionClient.from_dict_spec` (`subagent_client.py:78-84`),
so a config *can* be threaded in there.

Per-**agent** telemetry is therefore cheap and non-invasive (§3.1). Per-**tool**
telemetry is not reachable by call-site callbacks at all, and needs
process-global instrumentation (§3.2) — or a signature change in six files owned
by six different people, which is not happening in four weeks.

**0.4 — "tens of seconds" is not a measured number. It is currently unmeasured. [V]**

The audit's end-to-end run used deterministic fakes for five of six slots
(`integration_audit.md` §3.2, `sandbox/fakes.py`), so it produced no wall-clock
figure. The only latency number anywhere in the repo is the human-written string
"this usually takes 10-15 seconds" for Destination alone (`app.py:46`, restated
in the comment at `:103`). Six serial agents at that rate implies roughly 60-90s
**[I]**, and the serial-execution bug (§5.1) means it does not improve with
`asyncio.gather`. But I am not going to design a progress UI around an invented
constant. **Measuring the real per-agent and end-to-end latency is Phase 0 task
0.4, and it is the single most decision-relevant missing number in this plan.**

Two smaller notes, not corrections:

- `chainlit` and `truststore` are indeed absent from `requirements.txt` (all four
  lines: `requests>=2.31.0`, `deepagents>=0.7.5`, `langchain-cohere>=0.4.0`,
  `chromadb>=0.5.0`). **[V]**
- On this machine, `chainlit`, `truststore` and `deepagents` are **not installed**
  in the Python 3.11.5 on `PATH` (`C:\Python311\python`), and there is no `.venv`
  in the sandbox tree. `import chainlit` → `ModuleNotFoundError`. **[V]** The
  existing UI therefore cannot be launched here as-is. This is a Phase 0 blocker,
  not a design problem.

---

## 1. Recommendation

### Customer UI: keep Chainlit. Do not rewrite.

**Decisive reasons.**

1. **It already solves the two genuinely hard problems on this machine.**
   `truststore.inject_into_ssl()` before any HTTPS-touching import
   (`app.py:11-18`) and `cl.make_async` to offload a blocking sync agent off the
   event loop (`app.py:105`). Both were paid for in debugging time. Every
   alternative throws both away and re-earns them.
2. **It is the only candidate purpose-built for a nested step tree**, which is
   exactly the developer view. `cl.Step` nests by context manager — "To nest
   steps, simply create a step inside another step" — and `config.ui.cot`
   globally switches the chain of thought between full / tool-calls-only /
   hidden, which is *one flag* separating the customer view from the developer
   view in the same app. **[W]** https://docs.chainlit.io/api-reference/step-class
   and https://docs.chainlit.io/concepts/step (fetched 2026-08-21)
3. **It has a documented LangChain/LangGraph callback handler already**:
   `cl.LangchainCallbackHandler()`, with a LangGraph example, and the 2.11.1
   changelog shows it was touched for LangChain 1.x ("Check `langchain-core`
   version instead of `langchain` for callback compatibility"). **[W]**
   https://docs.chainlit.io/api-reference/integrations/langchain (fetched 2026-08-21)
4. **Free, Apache-2.0, self-hosted, no paid tier for anything needed here.**
   Persistence no longer requires a paid cloud — there is an official
   Postgres/asyncpg data layer plus community SQLAlchemy and DynamoDB layers.
   **[W]** https://docs.chainlit.io/data-layers/overview (fetched 2026-08-21)
5. `requires-python = ">=3.10,<3.14"` covers 3.11.5, and it does **not** depend on
   `uvloop`, which has no Windows support at all. **[W]** Chainlit
   `backend/pyproject.toml`, fetched 2026-08-21.

### Developer view: Chainlit steps for the demo, **Arize Phoenix for the truth.**

Two surfaces, one instrumentation story, because they answer different questions:

- **In-Chainlit step tree** — per-agent stages with live status, timing and
  degradation, driven by the wrapper in §3.1. This is what you show the sponsor.
- **Phoenix** — full per-tool spans (name, arguments, return value, duration,
  errors) with correct nesting, from `pip install arize-phoenix
  openinference-instrumentation-langchain` + `phoenix serve` +
  `register(auto_instrument=True)`. **No Docker, no account, no network egress,
  and zero changes to any agent or to the orchestrator.** The instrumentor hooks
  `langchain-core`'s callback system underneath everything, so it covers all six
  `deepagents` agents transitively. **[W]**
  https://arize.com/docs/phoenix/integrations/python/langchain/langchain-tracing
  and https://arize.com/docs/phoenix/self-hosting/deployment-options/terminal
  (both fetched 2026-08-21). Phoenix 20.3.0, 2026-08-17;
  `openinference-instrumentation-langchain` 0.1.70, 2026-08-07, Apache-2.0,
  explicitly supports LangChain 1.x. **[W]** PyPI, 2026-08-21.

Phoenix's licence is **Elastic License 2.0 — free to self-host, but not
OSI-approved open source** (it forbids offering Phoenix itself as a hosted
service). **[W]** https://github.com/Arize-ai/phoenix/blob/main/LICENSE, fetched
2026-08-21. For a capstone that self-hosts locally this is a non-issue; state it
in the report rather than calling Phoenix "open source".

### The strongest argument against my own recommendation

**Chainlit is frozen infrastructure, and I am recommending you build the
developer view on the one feature that has a known open bug.**

- The repo's own README carries: *"⚠️ Notice: Chainlit is now
  community-maintained. As of May 1st 2025, the original Chainlit team has
  stepped back from active development… Chainlit SAS provides no warranties on
  future updates."* **[W]**
  https://github.com/Chainlit/chainlit/blob/main/backend/README.md, fetched 2026-08-21.
- Last tagged release **2.11.1, 2026-04-22** — four months stale. **12 commits in
  the last 90 days** (2026-05-23 → 2026-08-21) against **48 open PRs**: a review
  backlog, maintained but not developed. **[W]** GitHub API, fetched 2026-08-21.
- It still hard-pins `literalai==0.1.201` as a core runtime dependency while
  `Chainlit/literalai-python` is **archived** (last push 2025-04-16). **[W]**
  Chainlit `backend/pyproject.toml` + repo state, 2026-08-21.
- **The specific risk to Phase 2:** issue #1077 "Nested steps for tools etc." is
  **still open** (opened 2024-06-14). Nesting itself works, but a commenter
  reports "correct nesting but wrong sequence of outputs", with two follow-up
  requests and no maintainer reply. **[W]**
  https://github.com/Chainlit/chainlit/issues/1077, fetched 2026-08-21. The
  developer view depends on nested steps rendering in the right order.
- `cl.ErrorMessage` exists in the source but is **absent from the docs sitemap**,
  i.e. undocumented and therefore unstable, and has an open persistence bug
  (#2567). **[W]** Do not build the degraded-agent display on it — use a failing
  `cl.Step` with explicit output text instead.

Compare Gradio: **234 commits/90d, 6.25.0 released 2026-08-19** (two days before
this was written), and `ChatMessage.metadata` natively supports `id`/`parent_id`
for nesting plus `status` ("pending"/"done") and **`duration` in seconds** — the
exact three fields the developer view needs, in a maintained library. **[W]**
https://www.gradio.app/guides/agents-and-tool-usage, fetched 2026-08-21.

**Why I still say keep Chainlit:** Phoenix carries the developer view's
*correctness* burden, so the Chainlit step tree only has to be a demo surface. If
#1077 bites, you degrade to flat sibling steps — visually worse, functionally
fine, because the real telemetry lives in Phoenix. Rewriting a working app to
dodge a cosmetic ordering bug costs a week you do not have, and re-earns the
truststore and make_async problems. **Trigger to reverse this: if the Phase 0
spike shows nested step ordering is wrong *and* Phoenix cannot be made to run,
port to Gradio.** That is a decision with a date and a test, not a preference.

**Explicitly not recommended, with reasons:**

- **Streamlit** — its rerun-the-script model means you cannot simply `await` the
  orchestrator, and `st.status` docs say **"don't nest status containers"** — a
  direct collision with the developer view. **[W]**
  https://docs.streamlit.io/develop/api-reference/status/st.status (v1.61.0,
  fetched 2026-08-21). Healthiest repo in the comparison (662 commits/90d) and
  still the wrong tool.
- **LangGraph Studio** — requires a `langgraph.json` + the Agent Server, and
  only inspects graphs *it* launches. It cannot observe an arbitrary orchestrator
  script, so it cannot be used without restructuring `orchestrator.py` into a
  graph entrypoint. Also serves its UI from `smith.langchain.com` and the docs
  present `LANGSMITH_API_KEY` as required. **[W]**
  https://docs.langchain.com/oss/python/langgraph/local-server, fetched 2026-08-21.
- **LangSmith** — works with genuinely zero code (two env vars), and your repo
  already references it (`README.md:124`, `budget_agent_rohan/.env.example:11-13`,
  `destination_agent/.env.example:3-5`). But: **self-hosting is Enterprise-only**,
  the free Developer tier is 1 seat / 5k traces per month / 14-day retention, and
  tracing **ships your prompts and tool I/O to `api.smith.langchain.com`**. **[W]**
  https://www.langchain.com/pricing-langsmith, fetched 2026-08-21. Keep it as an
  optional flag, not the plan of record — on a network that already needs
  `truststore` to complete a TLS handshake, adding mandatory cloud egress to your
  observability story is a bad trade.
- **A2UI / AG-UI** — see §2c. Real, but not for this.

---

## 2. Comparison table

All GitHub commit/issue counts pulled from the GitHub REST API on **2026-08-21**;
"commits 90d" is the window 2026-05-23 → 2026-08-21. PyPI data from
`pypi.org/pypi/{pkg}/json`, same date. Open-issue counts from the repo endpoint
include PRs; split shown where obtainable.

### 2a. UI frameworks

| Framework | Licence | Latest release (date) | Commits 90d | Open issues/PRs | Async + partial streaming | Native nested tool tree | Paid tier needed | Windows | Lock-in |
|---|---|---|---|---|---|---|---|---|---|
| **Chainlit** | Apache-2.0 | **2.11.1 — 2026-04-22** | **12** | 140 (92/48) | Yes, natively async | **Yes** — `cl.Step`, purpose-built; ordering bug #1077 open | No | No `uvloop` dep; `watchfiles` + `nest_asyncio` | Medium |
| **Gradio** | Apache-2.0 | 6.25.0 — 2026-08-19 | 234 | 174 (160/14) | Yes — `async for` + `yield`, documented | **Yes** — `ChatMessage.metadata` `id`/`parent_id`/`status`/`duration` | No | Fine; never install `uvloop` | Low-med |
| **Panel** | BSD-3 | 1.9.4 — 2026-08-17 | 93 | 1116 | Yes, async + `stream()` | **Yes** — `ChatStep` pending/running/**success/failed** | No | None found | Low-med |
| **NiceGUI** | MIT | 3.16.0 — 2026-08-12 | 153 | 72 | Yes, async-native | **No** built-in step tree | No | None found | Low |
| **Streamlit** | Apache-2.0 | 1.62.0 — 2026-08-19 | 662 | 1183 (978/205) | **Weakest** — sync rerun model | **No** — "don't nest status containers" | No | Port auto-increment fixed in 1.61.0 | Low-med |
| **FastAPI + JS** | MIT/BSD | n/a | n/a | n/a | Yes, fully (SSE/WS) | You build it | No | Clean | Lowest, highest effort |

Ruled out and why: **Reflex** (alive, but needs a Node ≥20.19 / Bun toolchain —
real Windows friction for zero gain); **Mesop** (Google handed it off,
`google/mesop` now 404s, only 10 commits/90d — smallest bus factor);
**Open WebUI** (licence is `NOASSERTION`: BSD-3 **plus a branding clause** since
v0.6.6, not OSI-approved, and it wants an OpenAI-compatible endpoint);
**Agent Chat UI** (MIT, but it is a Next.js client for a *LangGraph server* —
does not apply unless the orchestrator becomes a LangGraph deployment). Sources:
https://reflex.dev/docs/getting-started/installation/ ·
https://github.com/mesop-dev/mesop · https://docs.openwebui.com/license/ ·
https://github.com/langchain-ai/agent-chat-ui — all fetched 2026-08-21.

Note both Chainlit and Gradio *are* FastAPI apps underneath, so custom routes can
be mounted on either — most of the "roll your own" escape hatch, for free.

### 2b. Observability backends

| Option | Licence | Latest (date) | Self-host free? | Windows install | Zero code change? | Per-tool args/returns/duration | Egress |
|---|---|---|---|---|---|---|---|
| **Phoenix + OpenInference** | **ELv2** (not OSI) | phoenix 20.3.0 — 2026-08-17; instrumentor 0.1.70 — 2026-08-07 (Apache-2.0) | Yes, "no feature gates" | **`pip install` + `phoenix serve`, no Docker** | Yes — `register(auto_instrument=True)` | Yes; duration from OTel span start/end | **None** |
| **Langfuse** | MIT core; `ee/` dirs under separate EE licence | SDK 4.14.4 — 2026-08-11; server 4.16.0 — 2026-08-21 | Yes, core features | **Docker Compose required** — no pip server | No — `CallbackHandler` per call site | Yes | Local |
| **LangSmith** | proprietary SaaS | n/a | **No — Enterprise only** | n/a (cloud) | **Yes — 2 env vars** | Yes, best-in-class LangGraph rendering | **Yes, to `api.smith.langchain.com`** |
| **LangGraph Studio** | proprietary | `langgraph-cli` 0.4.31 — 2026-07-10 | Local run, cloud UI | `pip install "langgraph-cli[inmem]"` | **No — needs `langgraph.json`** | n/a here | UI served from cloud |

Sources: https://arize.com/docs/phoenix/self-hosting ·
https://github.com/Arize-ai/phoenix/blob/main/LICENSE ·
https://langfuse.com/pricing-self-host · https://langfuse.com/self-hosting ·
https://github.com/langfuse/langfuse/blob/main/LICENSE ·
https://www.langchain.com/pricing-langsmith ·
https://docs.langchain.com/oss/python/langgraph/local-server — all fetched 2026-08-21.

Langfuse footnote: its `LICENSE` copyright line now reads **"ClickHouse, Inc."**
**[W]** — worth knowing before adopting it, though it does not change the MIT
grant on the core.

### 2c. The "A2UI" question — you were right to make me check, and the name is real

| | What it is | Licence | Status | Verdict |
|---|---|---|---|---|
| **A2UI** (Google) | Declarative JSON UI format — agent picks from a client-held catalogue of pre-approved components. Announced 2025-12-15 at spec v0.8; repo `a2ui-project/a2ui` (`google/A2UI` redirects there); 16,182★ | Apache-2.0 | v0.9.1 stable, **v1.0 RC**; README says **"early stage public preview… Expect changes."** v1.0 + stability guarantees targeted **Q4 2026**. **LangGraph support is listed as "💡 Proposed"** | **Not a foundation.** It is a rendering format, not a chat framework; Python SDK `a2ui-agent-sdk` 0.5.0 (2026-07-31) depends on `google-adk`/`google-genai` |
| **AG-UI** (CopilotKit) | Agent↔UI event protocol over SSE/WebSocket; repo's primary language is **Python**; 15,477★; releases multiple times a week (latest `release/2026-08-20`) | **MIT** | `ag-ui-protocol` 0.1.20 (2026-08-14); **`ag-ui-langgraph` 0.0.43 (2026-04-10)**; official LangChain docs page for CopilotKit + FastAPI | **The viable one of the three** — but it presumes a React frontend and a LangGraph-server-shaped backend |
| **A2A** (Google → Linux Foundation) | Agent-to-**agent** RPC. **Not** agent-to-UI. 25,447★; spec v1.0 2026-04-09; `a2a-sdk` 1.1.2 | Apache-2.0 | Mature. Reportedly moving under the Agentic AI Foundation (2026-08-17, Axios — body returned 403, **unverified**) | Different problem. Relevant only to the `SlimSubagentClient` stub (`subagent_client.py:101-182`), not to the UI |

Sources: https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/ ·
https://a2ui.org/roadmap/ · https://raw.githubusercontent.com/a2ui-project/a2ui/main/README.md ·
https://pypi.org/pypi/a2ui-agent-sdk/json · https://github.com/ag-ui-protocol/ag-ui ·
https://pypi.org/pypi/ag-ui-langgraph/json ·
https://docs.langchain.com/oss/python/langchain/frontend/integrations/copilotkit ·
https://github.com/a2aproject/A2A — all fetched 2026-08-21.

**So: A2UI exists, and my caution about the name was unnecessary — but the
conclusion still holds.** Adopting it means React + AG-UI transport + the
CopilotKit runtime, on a spec whose own README says "expect changes" and whose
LangGraph support is *proposed*, to render a trip itinerary that is currently a
single markdown string. That is a multi-week frontend project to replace 113
working lines. If the sponsor wants the A2UI box ticked, note that A2UI rides on
top of AG-UI/CopilotKit, so it is addable later without re-architecting — a
stretch goal in a "future work" section, not Phase 1.

One thing I could not settle: whether a CopilotKit `publicApiKey` is *mandatory*
for a purely self-hosted LangGraph deployment. The relevant docs URLs
(`docs.copilotkit.ai/guides/self-hosting`, `docs.ag-ui.com/integrations/langgraph`)
returned 404. The OSS packages are MIT and the pricing page's free "Developer"
tier is $0, so it is probably fine — but **unverified**, and it would be the
first thing to check before betting on that stack.

---

## 3. Architecture sketch

### 3.1 The seam: rebind `orchestrator.get_client`

This is the load-bearing idea in the whole plan, and **it is already proven
working in this repo.**

`orchestrator.py:30` does `from orchestrator_config import get_client`. That
binds `get_client` as an *attribute of the `orchestrator` module*, so it can be
replaced from outside without editing the file. `sandbox/run_pipeline.py:56` does
exactly this — `orchestrator.get_client = _get_client` — and its own docstring
(`:6-9`) states: *"Nothing in the orchestrator or in any agent is modified. The
only intervention is monkeypatching `orchestrator.get_client`."* **[V]** It runs
the full six-slot `plan_trip` pipeline that way today.

`RecordingClient` at `run_pipeline.py:33-42` is already the right shape. For the
UI it needs to delegate to the *real* client instead of a fake, and push events
onto an `asyncio.Queue` that the UI drains:

```
UI process (one Chainlit session)
├── app_trip.py            @cl.on_message → install instrumentation, drain queue
├── ui_instrumentation.py  install(queue) → orchestrator.get_client = factory
│                          InstrumentedClient.call():
│                            emit stage_start(slot, task)
│                            t0 = perf_counter()
│                            result = await real.call(task)     ← unchanged
│                            emit stage_end(slot, result, dt, degraded?)
└── orchestrator.plan_trip(...)   ← UNTOUCHED
        └── the six agents         ← UNTOUCHED

Out-of-band, same process:
└── Phoenix (phoenix serve, localhost:6006)
        ← OpenInference auto-instrumentation of langchain-core
        → per-tool spans for all six agents, no code in any agent
```

**Files this design touches:**

| File | New or changed | Owner | Needs whose approval |
|---|---|---|---|
| `ui/app_trip.py` | **new** | Rohan | nobody |
| `ui/ui_instrumentation.py` | **new** | Rohan | nobody |
| `ui/ui_events.py` | **new** | Rohan | nobody |
| `ui/README.md` | **new** | Rohan | nobody |
| `.chainlit/config.toml` | **new** (generated by Chainlit) | Rohan | nobody |
| `requirements.txt` | **changed** — add `chainlit`, `truststore`, `arize-phoenix`, `openinference-instrumentation-langchain` | Emily (`ejmachad`) | **Emily** |
| `app.py` | **unchanged** — left as Joel's single-agent demo | Joel | — |
| `orchestrator.py` | **unchanged** | Emily | — |
| `subagent_client.py` | **unchanged** | Emily | — |
| `orchestrator_config.py` | **unchanged** | Emily / Vrushti | — |
| any agent module | **unchanged** | six owners | — |

**One existing file changes, and it is a requirements list.** That is the whole
point of this design. `app.py` is deliberately left alone rather than extended —
Joel's single-agent demo keeps working, and the orchestrator UI is a separate
entry point (`chainlit run ui/app_trip.py`). Two entry points is cheaper than one
contested file.

### 3.2 Two event sources, and why both

| | Source | Granularity | Invasiveness | Gives duration? |
|---|---|---|---|---|
| **Stage events** | `get_client` rebinding (§3.1) | per **agent**: slot name, outbound task string, reply, wall-clock, degraded flag | zero files changed | yes — you time it |
| **Tool events** | Phoenix / OpenInference OTel auto-instrumentation | per **tool**: name, args, return value, errors, nesting | zero files changed | yes — OTel span start/end |

Neither requires a call-site `config`, which is what makes them work despite
§0.3. They are complementary: stage events are what the *customer* progress UI
needs (and they are exactly at the granularity the serial pipeline actually
executes at); tool events are what the *developer* view needs.

**Can one event stream drive both UIs?** Partly, and the honest answer matters.
Stage events can, trivially — same queue, different rendering. For tool events,
the theoretically clean answer is to register a **custom in-process OTel span
processor** alongside the Phoenix exporter, so the same spans that go to Phoenix
also land on the UI queue and can be rendered as nested `cl.Step`s. That would
give one unified stream. **I have not verified that this works** — specifically,
whether OpenInference span attributes carry tool arguments and return values in a
form a custom processor can read directly, and whether span end callbacks fire
early enough to render live rather than after the run. **Phase 0 task 0.5 is to
verify or kill that idea.** If it fails, the fallback is unambiguous and still
fine: stage events drive the Chainlit UI, Phoenix is a second browser tab, and
you cross-reference by timestamp.

### 3.3 Detecting a degraded agent — string matching is *not* the only option

The brief asks whether string-matching `[subagent error]` / `[X unavailable]` is
the only way. It is not, and the better way falls out of §3.1 for free.

Because the wrapper *replaces* `get_client` entirely, it controls client
construction. Two precise handles exist:

1. **Build failures.** `orchestrator_config.get_client` swallows build exceptions
   into `_BrokenClient` (`orchestrator_config.py:106-124`). But the wrapper can
   call `orchestrator_config._BUILDERS[name]()` itself and catch the real
   `ImportError`/`KeyError` — getting the exception type, message and traceback
   instead of a formatted string. **[V]** `_BUILDERS` is defined at
   `orchestrator_config.py:91-98`.
2. **Call failures.** `LocalFunctionClient.call` swallows exceptions at
   `subagent_client.py:97-98`. But the wrapper holds the client object and can
   reach `client._answer_fn` (`subagent_client.py:64-65`) and invoke *that*
   inside its own `try`, catching the genuine exception. **[V]**

That eliminates string matching for both failure classes and gives real
tracebacks for the developer view.

**The catch, stated plainly:** both handles depend on private names
(`_BUILDERS`, `_answer_fn`). They are strictly more precise than string matching
but strictly more coupled — if Emily renames either, this breaks loudly at
startup rather than silently mis-reporting. **Design decision: do both.** Use the
private-attribute path as primary, keep a string-match on
`^\[.*(error|unavailable)\]` as a defence-in-depth fallback, and have the wrapper
log which mechanism fired. String matching alone is brittle in a specific way
worth naming: an agent that *legitimately* quotes the phrase, or a future error
format change, both silently defeat it — and there is precedent for legitimate
refusal text being mistaken for failure, since Rohan's Budget agent already
returns a well-formed refusal that is not an error (`integration_audit.md` §3.4).

### 3.4 Streaming options assessed (the brief's section B)

| # | Option | Modifies orchestrator/agents? | Gives | Verdict |
|---|---|---|---|---|
| 1 | **Rebind `get_client`** (§3.1) | **No** — zero files | per-agent stage progress, timing, failures | **Do this.** Not in the brief's list; proven at `run_pipeline.py:56` |
| 2 | **Phoenix/OpenInference auto-instrumentation** | **No** — zero files | per-tool detail, nested, with durations | **Do this too**, for the developer view |
| 3 | Chainlit `cl.Step` nesting | No, it is UI-side | rendering for 1 and 2 | Do it — but see #1077 |
| 4 | LangChain callback handler via `config=` | **Yes** — six agent files, six owners | per-tool events in-process | **Not viable.** §0.3: there is no call site |
| 5 | `stream_events(version="v3")` | **Yes** — needs the graph object | best structured events: `tool_calls`, `tool-started`/`tool-finished`/`tool-error`, `subgraphs` with `graph_name` | Right answer in a world where the agents exposed their graphs. They do not. **Viable for Flights only** (`subagent_client.py:80`) |
| 6 | LangSmith env vars | No | everything, in the cloud | Optional flag; not the plan (§1) |
| 7 | Refactor `plan_trip` into an async generator | **Yes** — `orchestrator.py`, Emily's file | true intra-stage streaming | **Propose to Emily, do not assume.** §6. Option 1 gets ~80% of the benefit at 0% of the negotiation cost |

On option 5, for the record since it is the textbook answer:
`create_deep_agent` returns a `CompiledStateGraph` and `.with_config()` on a
Pregel returns a *copy*, not a `RunnableBinding`, so the full streaming surface
survives — `.astream_events()`, `.stream_events(version="v3")`, and
`.astream(stream_mode=...)`. **[W]**
`langchain-ai/deepagents/libs/deepagents/deepagents/graph.py` and
`langgraph/pregel/main.py`, read 2026-08-21. v3 exposes `stream.tool_calls` and a
raw `tools` channel emitting `tool-started` / `tool-output-delta` /
`tool-finished` / `tool-error`, plus `stream.subgraphs` with `graph_name`. **[W]**
https://docs.langchain.com/oss/python/langgraph/event-streaming, fetched
2026-08-21. All of it is unreachable here because no caller ever holds the graph.

Two facts that constrain any of these:

- **Durations are in no event payload.** Neither `astream_events` nor v3 event
  streaming documents a duration field; you time it yourself or let a tracing
  backend derive it from span start/end. **[W]** Same sources, 2026-08-21. This is
  a direct argument for Phoenix over hand-rolled callbacks.
- **`stream_mode` subgraph propagation is not automatic** — `subgraphs=True` is
  required or nested agents' events are dropped. **[W]** 
  https://docs.langchain.com/oss/python/langgraph/streaming, fetched 2026-08-21.

---

## 4. Phased plan

Effort figures are **rough estimates in Rohan-hours, not commitments**, and they
assume the Phase 0 environment work lands first.

### Phase 0 — spike: prove the seam and the environment (~4-6h)

Nothing here is UI work. It exists because three things in §0 are unverified or
broken, and building on them unmeasured is how you lose a week.

| # | Task | Files | Done when |
|---|---|---|---|
| 0.1 | Create a real venv and pin it. `py -3.11 -m venv .venv`; install `requirements.txt` + `chainlit` + `truststore`; record exact versions | `requirements.txt`, new `requirements-ui.txt` | `python -c "import chainlit, truststore, deepagents"` exits 0 on this machine |
| 0.2 | Launch the existing app unmodified: `chainlit run app.py -w` | none | Browser renders the welcome message and one real Destination answer returns |
| 0.3 | Resolve the `budget_agent` name collision (§5.4) explicitly, and write down which one wins | `ui/README.md` | A one-line documented `sys.path` decision, not an accident |
| 0.4 | **Measure latency.** Instrument the §3.1 wrapper, run `plan_trip` once with every available real agent, print per-slot wall-clock and the total | `ui/ui_instrumentation.py` | A table of six real numbers exists. **This replaces the invented "tens of seconds"** |
| 0.5 | Spike the two open technical questions: (a) do nested `cl.Step`s render in the correct order (#1077)? (b) can a custom OTel span processor read tool args/returns off OpenInference spans live (§3.2)? | throwaway scripts | Both answered yes/no in writing. (a) no → plan flat steps. (b) no → Phoenix is a second tab |
| 0.6 | `pip install arize-phoenix openinference-instrumentation-langchain`; `phoenix serve`; run one agent with `register(auto_instrument=True)` | none | Phoenix UI at `localhost:6006` shows tool spans with arguments and durations for at least one real agent |

**Acceptance criterion for the phase:** you can state, from measurement, how long
the pipeline takes and which agents are available on your machine; and the
`get_client` rebinding demonstrably reports six stage events for a real run.

**Gate:** if 0.5(a) and 0.6 both fail, stop and reconsider Gradio before Phase 1.

### Phase 1 — customer UI (~1-1.5 days)

| # | Task | Files | Done when |
|---|---|---|---|
| 1.1 | New Chainlit entry point wrapping `plan_trip`, with `truststore` injection first and `REPO_ROOT` on `sys.path` — copy the pattern from `app.py:11-29` verbatim, it is correct | `ui/app_trip.py` (new) | `chainlit run ui/app_trip.py` returns a full itinerary |
| 1.2 | Slot-filling for the four `plan_trip` parameters. `plan_trip` has no structured slots and no origin *city* at all (`orchestrator.py:146-151`; audit Gap 2), so the UI must collect origin, destination, dates, party size, budget itself — via `cl.AskUserMessage` or a `cl.ChatSettings` form | `ui/app_trip.py` | A traveller can complete a request without knowing the parameter names |
| 1.3 | Progress rendering from stage events: one `cl.Step` per agent, updating live as each of the six completes, with the measured 0.4 numbers used for an honest ETA | `ui/app_trip.py`, `ui/ui_events.py` | Six steps appear and resolve in sequence; no blank spinner for >5s |
| 1.4 | Degraded-agent display using the §3.3 detector: a failed agent renders as a visibly failed step with a plain-English cause, and the itinerary still assembles from the rest | `ui/ui_instrumentation.py`, `ui/app_trip.py` | With `TRAVELPAYOUTS_TOKEN` unset (Flights raises `KeyError` at import — audit §2.2 item 2), the UI shows "Flights unavailable" and still returns the other five sections |
| 1.5 | Render the assembled itinerary readably — split `_assemble_itinerary`'s `=== Section ===` output (`orchestrator.py:132-143`) into per-section markdown rather than one code-fenced blob | `ui/app_trip.py` | Sections render as headings |
| 1.6 | Update `requirements.txt` and open the PR to Emily | `requirements.txt` | PR open, one-file diff |

**Acceptance criteria:** a traveller with no knowledge of the codebase types a
request, sees continuous progress, and gets an itinerary — and when an agent is
unavailable, they are told which one and still get the rest.

### Phase 2 — developer view (~1-2 days)

| # | Task | Files | Done when |
|---|---|---|---|
| 2.1 | Developer mode toggle. Prefer `config.ui.cot` for the built-in customer/developer split; add a `cl.ChatSettings` switch for the extra panels | `.chainlit/config.toml`, `ui/app_trip.py` | One toggle hides/shows all internals |
| 2.2 | Per-stage detail: outbound task string, reply, duration, degraded flag, and *which* detection mechanism fired | `ui/app_trip.py` | Every stage expands to show exactly what it received and returned |
| 2.3 | Nested tool calls inside each stage — via the 0.5(b) custom span processor if it worked, otherwise flat siblings | `ui/ui_events.py` | Tool name, args, return, duration visible per agent |
| 2.4 | Phoenix side-by-side: a documented two-command launch, and a link from the UI | `ui/README.md` | A teammate reproduces the developer view from the README alone on a clean machine |
| 2.5 | Optional LangSmith flag, off by default, documented as cloud egress | `ui/README.md` | `LANGSMITH_TRACING=true` works and is labelled |
| 2.6 | Surface the serial-execution finding in the UI itself: show the three "parallel" agents' actual sequential timings | `ui/app_trip.py` | The screen makes audit §2.3 self-evident — a demo asset, not just a bug |

**Acceptance criteria:** for one real run, a developer can answer — without
reading code — which agents ran, in what order, with what arguments, for how
long, which tools each called, and which degraded and why.

---

## 5. Risks

**5.1 — Serial execution makes the pipeline ~3x slower than the code implies.**
`subagent_client.py:94-98` declares `async def call` but never awaits, so
`asyncio.gather` at `orchestrator.py:76-80` runs the three "parallel" agents
sequentially (audit §2.3). *Mitigation:* the UI does not try to hide it. Stage
events are emitted at exactly the granularity execution happens, so progress is
*honest* — six sequential steps, each with a measured ETA from Phase 0.4. Then
make it a finding: task 2.6 renders the serial timings as the evidence. The fix
(`await asyncio.to_thread(self._answer_fn, task)`, one line at
`subagent_client.py:96`) is Emily's call — §6, question E3. **Do not let the UI
depend on that fix landing.**

**5.2 — Invisible failure: a crashed agent is a `str`, same as success.**
`subagent_client.py:98` and `orchestrator_config.py:120-122` (audit §1.9: "the
single most consequential design fact in the system"). Without handling, the UI
cheerfully renders `[subagent error] KeyError: 'TRAVELPAYOUTS_TOKEN'` as an
itinerary section. *Mitigation:* §3.3 — catch real exceptions via the private
handles, keep string matching as fallback, log which fired. Accept the coupling
to `_BUILDERS`/`_answer_fn` and pin it with a test that fails loudly if either
name disappears.

**5.3 — Chainlit is community-maintained and #1077 is open.** *Mitigation:* pin
the version exactly (`chainlit==2.11.1`); assume no upstream fixes; put the
developer view's *correctness* burden on Phoenix, not on Chainlit's step tree;
Phase 0.5(a) decides nested vs flat before any UI code is written; Gradio is the
documented fallback with a stated trigger (§1).

**5.4 — Two different packages both named `budget_agent`.** `orchestrator_config.py:68`
does `from budget_agent.agent import build_agent`, and on the merged tree that
resolves to whichever of Shashank's (repo root) or Rohan's
(`budget_agent_rohan/budget_agent/`) is first on `sys.path` — verified
empirically in the audit (§2.2 item 4). A UI that manipulates `sys.path` (which it
must, per `app.py:27-29`) can silently change *which Budget agent runs*.
*Mitigation:* Phase 0.3 — make the choice explicit and documented in one place,
and have the UI *display* which module resolved (`module.__file__`) in developer
mode. Turning an invisible collision into a visible label is most of the fix.

**5.5 — Several agents are unavailable on any given machine (missing API keys).**
Flights raises `KeyError` at import without `TRAVELPAYOUTS_TOKEN`; Destination
builds its graph at module import (`destination_agent/destination_agent.py:355`),
so a missing key fails at import time, not call time. **[V]** *Mitigation:* Phase
1.4 makes this the *demo* rather than the failure mode — a preflight check on
`@cl.on_chat_start` that probes each of the six builders and shows a
"5 of 6 agents available" banner up front, so degradation is visible before the
user waits 90 seconds for it.

**5.6 — `truststore` must be injected before any HTTPS-touching import.**
Without it, calls hang ~5 minutes then fail with no useful error
(`app.py:11-18`, comment). *Mitigation:* copy `app.py:11-29` verbatim as the
first lines of `ui/app_trip.py` and add a comment saying why the import order is
load-bearing, so nobody "tidies" it. Add a startup assertion that
`ssl.SSLContext` has been patched.

**5.7 — Phoenix is ELv2, not OSI open source.** *Mitigation:* say so in the
capstone report; it is free for local self-hosting, which is the only use here.
If a hard OSI requirement appears, Langfuse (MIT core) is the swap — at the cost
of requiring Docker Desktop and per-call-site handler attachment.

**5.8 — Version drift.** `deepagents` 0.7.8 (2026-08-20) requires
`langchain-core>=1.6.0`; the sandbox has 1.5.4, and `requirements.txt` says only
`deepagents>=0.7.5`. **[V/W]** An unpinned `pip install` can move the whole agent
stack under you mid-capstone. *Mitigation:* Phase 0.1 pins exact versions in
`requirements-ui.txt` and commits a `pip freeze`.

**5.9 — The itinerary may be unusable regardless of how good the UI is.** Audit
§3.3-3.4: the destination never propagates to the downstream three, no origin
city exists, and the user's task never reaches Budget — which made the real
Budget agent *refuse*. A beautiful UI over that pipeline renders a beautiful
refusal. *Mitigation:* out of scope for this plan, but Phase 1.2's slot-filling
partly compensates by collecting structured inputs the UI can fold into the task
string itself — without touching `orchestrator.py`. Flag the rest to Emily (§6).

---

## 6. Open questions for the team

### Must be answered by Emily (owner of `orchestrator.py`, `subagent_client.py`, `orchestrator_config.py`)

- **E1.** May I add `chainlit`, `truststore`, `arize-phoenix` and
  `openinference-instrumentation-langchain` to `requirements.txt`? This is the
  only existing file my plan changes. Would you prefer a separate
  `requirements-ui.txt` so the agent stack stays untouched?
- **E2.** Do you object to the UI rebinding `orchestrator.get_client` at runtime
  (§3.1)? It changes no file, but it depends on `orchestrator.py:30` staying an
  `from … import` (not `import orchestrator_config` + qualified calls). **If you
  ever change that line, my UI breaks.** Can we agree it is a stable seam, or
  would you rather expose an official hook?
- **E3.** The one-line serial-execution fix — `return await
  asyncio.to_thread(self._answer_fn, task)` at `subagent_client.py:96`. Your
  file, your call. I am **not** blocking on it; I want to know whether to plan
  for ~3x or ~1x wall-clock.
- **E4.** May the UI depend on `orchestrator_config._BUILDERS` and
  `LocalFunctionClient._answer_fn` (§3.3) to get real exceptions instead of
  string-matching error text? Both are private. If you would rather keep them
  private, I fall back to string matching and accept the brittleness.
- **E5.** Longer term: would you accept a proposal to make `plan_trip` an async
  generator yielding stage events (brief option 3)? Not needed for Phases 0-2. I
  would rather not, and the reason is that §3.1 gets most of the value with none
  of the coupling — but it is your design call.
- **E6.** `plan_trip` has no origin-city parameter and no structured slots
  (audit Gaps 2 and 4). Should the UI fold collected slots into the free-text
  `task` string (works today, no change to your file), or do you want to add
  parameters?

### I can answer myself, or the team can

- **T1.** Two entry points (`app.py` for Joel's single agent, `ui/app_trip.py`
  for the orchestrator) or one merged app? I recommend two — it avoids a
  contested file. **Joel's call**, since `app.py` is his.
- **T2.** How much of the developer view should be visible in the sponsor demo?
  My recommendation: the stage timings, yes (they make audit §2.3 self-evident);
  raw tool arguments, no — that is Phoenix's job.
- **T3.** Does anyone already have a LangSmith key with quota, and is the team
  comfortable with prompts and tool I/O leaving the network? If not, Phoenix
  covers it locally with no egress.
- **T4.** Who owns the `budget_agent` naming collision fix (§5.4) — is that
  Shashank's, Rohan's, or Emily's to resolve?
- **T5.** Does the sponsor specifically want A2UI in the deliverable? If yes it
  belongs in "future work" (§2c), and someone should confirm the CopilotKit
  self-hosting key question first.

---

## 7. What I could not verify

Stated plainly, as in the audit.

**About this repo:**

1. **End-to-end latency, and per-agent latency.** No measured number exists
   anywhere in the repo. Everything in §0.4 above the 10-15s Destination string is
   inference. Phase 0.4 exists to fix this.
2. **That the existing Chainlit app runs.** I could not launch it —
   `chainlit`, `truststore` and `deepagents` are all absent from the Python on
   `PATH` here, and there is no venv in the sandbox tree. I verified the code by
   reading it; I did not see it work. Joel presumably ran it on 2026-08-19.
3. **Which agents actually work on any given machine.** The audit's end-to-end
   run used fakes for five of six slots. I have not run the real six-agent
   pipeline, so I do not know how many of the six are currently functional.
4. **That nested `cl.Step` rendering is correct for this workload** — issue
   #1077 says it may not be. Untested here (see 2).
5. **Whether Chainlit's `nest_asyncio` usage causes trouble on Windows
   specifically.** The open loop issues I found are Python-3.14-specific (#2767)
   or involve `instrument_openai` + `make_async` from a background thread
   (#1868). Neither obviously applies at 3.11.5, but I could not reproduce or
   rule them out on Windows.

**About external facts:**

6. **Whether a custom in-process OTel span processor can read tool arguments and
   return values off OpenInference spans, live** (§3.2). This is the pivot for
   "one event stream drives both UIs" and it is an assumption, not a finding.
   Phase 0.5(b).
7. **Whether Phoenix explicitly claims LangGraph support.** Its LangChain tracing
   page does not say so. Coverage *follows* from the instrumentor hooking
   `langchain-core` callbacks, and `deepagents` sits on `create_agent`/LangGraph —
   but that is my inference, not their documentation. Phase 0.6 tests it directly.
8. **Whether tool spans in Phoenix carry latency explicitly.** Implied by OTel
   spans having start and end times; not stated on the page I read.
9. **Whether `astream_events` v2 has a tool-error event type.** None is listed.
   If not, callbacks capture tool errors more cleanly than v2 events — moot here,
   since neither is reachable (§0.3).
10. **Whether the `LANGCHAIN_*` env aliases are formally deprecated** in favour of
    `LANGSMITH_*`. Both appear functional; no first-party deprecation notice found.
    Your repo uses `LANGSMITH_*` already, which is the currently documented form.
11. **Whether LangGraph Studio is still free** in Aug 2026. The sources asserting
    it are 2024-era and likely stale; the current pricing page lists Studio under
    no plan. Moot — it is ruled out on architecture (§1).
12. **Whether a CopilotKit `publicApiKey` is mandatory** for a purely self-hosted
    AG-UI + LangGraph deployment. The two relevant docs URLs 404'd.
13. **The licence of the `a2ui-agent-sdk` PyPI package specifically** — the
    metadata licence field is unpopulated. The A2UI repo is Apache-2.0; whether
    that extends to the SDK package is unconfirmed.
14. **Whether Langfuse offers a Python auto-instrumentation path** that avoids
    per-call-site handler attachment. If it does, it would be more competitive
    with Phoenix than §2b suggests.
15. **The Axios report that A2A is moving to the Agentic AI Foundation**
    (2026-08-17) — the article body returned HTTP 403. Headline only.
