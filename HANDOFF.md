# Handoff — UI over the orchestrator, tracing, and what's next

**Author:** Rohan Shivakumar · **Date:** 2026-08-22 · **Branch:** `ui_chainlit_rohan`
**Base it needs:** `sandbox-integration` (both pushed to `origin`)

Written as a handoff so someone else — or me next week — can pick this up cold.
Companion docs, all on `ui_chainlit_rohan`:

| Doc | What it's for |
|---|---|
| [`RUNNING_THE_UI.md`](RUNNING_THE_UI.md) | **Start here to run it.** Setup, switching your agent on, reading failures |
| [`UI_STATUS.md`](UI_STATUS.md) | Status against the requirement; what is and isn't tested |
| [`UI_BUILD_REPORT.md`](UI_BUILD_REPORT.md) | Deep build detail, acceptance evidence, findings |
| [`ENVIRONMENT.md`](ENVIRONMENT.md) | Every env var the pipeline reads, with `file:line` |
| `UI_PLAN.md` on `origin/worktree-ui-plan` | The tooling research this doc's §5 summarises |

---

## 1. Where things stand in one paragraph

The Chainlit UI drives the whole orchestration. One chat line runs `plan_trip`,
all six agent slots fire, each appears as its own step with input and output as it
finishes, and the assembled itinerary comes back. It runs with **no API keys** and
nothing installed but `chainlit` + `truststore`. **Every agent is currently a
stand-in** — the wiring is tested across all six, the agents themselves are not,
because four need dependencies installed and the rest need keys. The single
cheapest thing that would change that is a Travelpayouts token for Flights.

---

## 2. What was built

Extends Joel's Chainlit UI from PR #10, which supplied the Chainlit surface and
the Destination wiring. Before: `app.py` drove one agent. Now: the whole pipeline
through `plan_trip` (`orchestrator.py:146`, invoked at `app.py:151`).

Three additions, all under `ui/`:

- **`ui/request_parse.py`** — `plan_trip` takes four arguments (`task`,
  `origin_country`, `destination_country`, `stated_budget`), not one free-text
  line. A chat box gives one line, so this splits it with deterministic regex, no
  model. The split renders as its own step so a bad parse *looks* like a bad parse.
- **`ui/agent_seam.py`** — the real-vs-stand-in seam. The UI never chooses; it
  calls `plan_trip` and nothing else. One rebind of `orchestrator.get_client`
  decides per slot. **`orchestrator_config.py` is not rewritten** — when a slot is
  `real`, the seam calls its existing public `get_client()`.
- **`ui/verify_seam.py`** — headless proof of the seam's guarantees, no browser.

### Why the seam exists

The layers below have two error-string escape hatches:
`"[{name} unavailable] …"` (`orchestrator_config.py:130`) and
`"[subagent error] …"` (`subagent_client.py:98`). Unabsorbed, those land in the
browser as text that reads like a crash. `Flights: sample data` reads as
not-wired-yet; `Flights: [subagent error] No module named 'deepagents'` reads as
broken. The seam catches both shapes, substitutes that slot's stand-in, and logs
the real cause to the terminal.

### The one thing most likely to mislead someone

**Seeing a plan does not mean an agent ran.** If an agent can't start, the seam
substitutes sample data and the itinerary still renders and still looks plausible.
The step label (`(live agent)` vs `(sample data)`) and the `[seam]` line in the
terminal are the only real signals. This is `RUNNING_THE_UI.md` §4 and it is the
section to point people at.

---

## 3. Changes made in this session, and why

### 3a. Renamed `budget_agent_rohan/budget_agent/` → `proposed_envelope_agent/`

Commit `2e9073b`. Two different agents shared the import name `budget_agent`:
Shashank's repo-root RAG cost estimator, and my per-diem envelope proposer.
`import budget_agent` resolved to whichever landed in `sys.modules` first — so
**import order, not intent, picked the agent.** Only mine has `corpus.py`, so once
the root package won, the envelope path died on
`No module named 'budget_agent.corpus'` and silently degraded to sample data for
the rest of the process.

`evaluation/direct_path.py:32` inserting its own parent at `sys.path[0]` hid this:
it works right up until the root package is already imported, at which point
`sys.path` is irrelevant. That's why it looked intermittent and survived so long.

Verified by reproducing the failing sequence — import the root package *first*,
then call the envelope path — and confirming it renders a real allocation.

### 3b. Removed the envelope agent from the orchestrator's options

Commit `6b6c567`. The budget slot used to default to a third mode, `direct`, which
ran the envelope proposer with no model and no key. That agent is **proposed future
work**, so it should not be presented as part of the pipeline.

The mode was **removed, not merely defaulted off** — leaving `direct` selectable
would let a stray `TRAVEL_UI_AGENTS` value put unreleased work in front of a user.
`budget=direct` now resolves to `dummy`.

The budget slot's `real` path is **Shashank's** repo-root RAG agent. That needed no
code change (`budget_agent/agent.py:86` returns an `.invoke()`-able agent matching
the call shape); what it lacked was a record of what going live takes — deps, a
key, **and** a built Chroma vectorstore. Now noted at the builder.

**Consequence worth restating: budget was the only partly-real slot, so the honest
count of live agents in the UI is now zero.**

Two judgment calls in that commit, flagged for review:
- `sandbox/run_pipeline.py` also routed an orchestrator run to the envelope path.
  Its purpose is capturing outbound task strings, which don't depend on reply
  content, so budget uses a stand-in there too. No orchestrator run anywhere
  reaches the envelope agent now.
- `verify_seam.py` Case 3 asserted the envelope agent's refusal prose. No longer a
  UI guarantee, so dropped rather than moved; acceptance evidence `#5b` in the
  build report says so instead of being deleted.

The envelope agent is otherwise untouched and still runs standalone
(`budget_agent_rohan/`, `sandbox/run_envelope_test.py`).

### 3c. Docs

`RUNNING_THE_UI.md` (new, commits `dc3eb5b` + `c6882bd`), `UI_STATUS.md` (new),
and updates to `UI_BUILD_REPORT.md` / `ENVIRONMENT.md` / `.env.example`.

---

## 4. How it was verified

Not a mock — a real server, driven over Chainlit's own socket.io protocol
(`client_message` in, `new_message`/`update_message` out), i.e. the exact events a
browser receives.

| Case | Result |
|---|---|
| Default run, *"Plan a week in Aruba from Boston, budget $3000"* | `GET /` 200, `/project/settings` 200, **7 steps** in completion order, all labelled, one assembled plan with all five `=== … ===` sections, zero error strings |
| **All six forced to `real`** while unconnected | Six clean stand-in steps in the browser; terminal logged all six causes; both error shapes (`[… unavailable]` ×5, `[subagent error]` ×1) occurred naturally and both were absorbed |
| Unparseable input `asdkjfh ????` | No crash; parse step shows `_not detected_`; Money & Customs correctly **skipped** (6 steps, per `orchestrator.py:158`) |
| `budget=direct` after removal | Resolves to `dummy` — mode is genuinely gone |
| `python ui/verify_seam.py` | All checks pass |
| `sandbox/run_pipeline.py`, `sandbox/run_envelope_test.py` | Both exit 0 |

The forced-`real` terminal output, which doubles as the current blocker list:

```
[seam] destination:    [destination unavailable] No module named 'deepagents'
[seam] restaurants:    [subagent error] No module named 'deepagents'
[seam] budget:         [budget unavailable] No module named 'langchain'
[seam] money_customs:  [money_customs unavailable] No module named 'langchain_cohere'
[seam] flights:        [flights unavailable] 'TRAVELPAYOUTS_TOKEN'
[seam] activities:     [activities unavailable] No module named 'activities_agent'
```

**Not verified:** `budget_agent_rohan/tests/` — `pytest` is not installed in this
venv. Imports resolve and it byte-compiles, but the assertions are unexercised.

**Test-harness note:** driving the socket from Python needed `pip install
websocket-client`. That is a *test* dependency only — the browser needs nothing
extra and it was not added to any requirements file.

---

## 5. Tooling — the alternatives, and what I'd pick

Emily asked that the orchestrator also **trace the agent workflows**. Splitting
that into what exists and what's missing:

**Exists today.** The workflow is already traced at the *agent* level: every call
goes through a hook reporting `(slot, effective_mode, task, reply)`, rendered as a
per-agent step showing exactly what that agent received and returned. Fallbacks
are logged with their cause. `sandbox/run_pipeline.py` captures every outbound task
string, which is the tool to reach for when an agent works standalone but
misbehaves in the pipeline.

**Missing.** Real spans — timing, nesting, token counts, and any visibility
*inside* an agent (which tool, what arguments, what returned).

### 5a. Observability backends

Research and dates from `UI_PLAN.md` on `origin/worktree-ui-plan` (all figures
fetched 2026-08-21 — **re-check before quoting**).

| Option | Licence | Self-host free? | Windows install | Zero code change? | Egress |
|---|---|---|---|---|---|
| **Phoenix + OpenInference** ← *recommended* | **ELv2, not OSI** | Yes, no feature gates | **`pip install` + `phoenix serve`, no Docker** | **Yes** — `register(auto_instrument=True)` | **None** |
| Langfuse | MIT core; `ee/` separate | Yes, core | **Docker Compose required** | No — `CallbackHandler` per call site | Local |
| LangSmith | proprietary SaaS | **No — Enterprise only** | n/a (cloud) | Yes — 2 env vars | **Yes**, to `api.smith.langchain.com` |
| LangGraph Studio | proprietary | Local run, cloud UI | `pip install "langgraph-cli[inmem]"` | **No** — needs `langgraph.json` | UI from cloud |

**Recommendation: Arize Phoenix with the OpenInference LangChain instrumentor.**
`pip install arize-phoenix openinference-instrumentation-langchain`, then
`phoenix serve` and `register(auto_instrument=True)`. No Docker, no account, no
network egress, and **zero changes to any agent or to the orchestrator** — it hooks
`langchain-core`'s callback system underneath everything, so it covers all six
agents at once. Full per-tool spans with arguments, return values, durations,
errors.

⚠️ **Correction to something I nearly recommended.** I earlier floated LangSmith
as a cheap "zero-code" option because its env vars are already in
`.env.example` and no repo code reads them (langchain picks them up when set).
That is true but incomplete: **self-hosting is Enterprise-only**, the free
Developer tier is 1 seat / 5k traces per month / 14-day retention, and tracing
**ships prompts and tool I/O to `api.smith.langchain.com`**. On a network that
already needs `truststore` to complete a TLS handshake, making mandatory cloud
egress part of the observability story is a bad trade. Keep it as an optional
flag, not the plan of record.

State Phoenix's licence honestly in the report: ELv2 is free to self-host but
**not** OSI-approved open source. Fine for a capstone; just don't call it "open
source".

### 5b. UI frameworks — why Chainlit stays

| Framework | Licence | Async + streaming | Native nested tool tree |
|---|---|---|---|
| **Chainlit** ← *current* | Apache-2.0 | Yes, natively async | **Yes** — `cl.Step`, purpose-built (ordering bug #1077 open) |
| Gradio | Apache-2.0 | Yes | **Yes** — `ChatMessage.metadata` parent/child |
| Panel | BSD-3 | Yes | **Yes** — `ChatStep` with success/failed |
| NiceGUI | MIT | Yes | No built-in step tree |
| Streamlit | Apache-2.0 | **Weakest** — sync rerun model | **No** — docs say don't nest status containers |

Chainlit's release cadence is the slowest of these (12 commits/90d) and step
ordering bug #1077 is open. **The mitigation is Phoenix**: if the nested step tree
misbehaves, the Chainlit view degrades to flat sibling steps — visually worse,
functionally fine, because the real telemetry lives in Phoenix. Rewriting a
working app to dodge a cosmetic ordering bug is not a good use of the remaining
weeks. Documented reversal trigger: *if nested step ordering is wrong **and**
Phoenix cannot be made to run, port to Gradio.*

### 5c. A2UI / AG-UI — the stretch goal

A2UI is real (Google, Apache-2.0, repo `a2ui-project/a2ui`). But it is a
declarative **rendering format**, not a chat framework, and its own README says
"early stage public preview… expect changes" with v1.0 targeted Q4 2026 and
LangGraph support only *proposed*. AG-UI (CopilotKit, MIT) is the viable transport
of the three, but presumes a React frontend and a LangGraph-server-shaped backend.

**Verdict: future work, not Phase 1.** Adopting it means React + AG-UI transport +
the CopilotKit runtime to render an itinerary that is currently a single markdown
string. A2UI rides on top of AG-UI, so it's addable later without
re-architecting. Note for whoever picks it up: **Joel already hit an endpoint issue
with ag-ui in Week 1** — ask him before starting. One thing unverified in the
research: whether a CopilotKit `publicApiKey` is mandatory for a purely
self-hosted deployment (the relevant docs URLs 404'd).

### 5d. Agent communication — the architecture question

For Vrushti's open question about whether A2A is still the agreed protocol:

- **Today it is not A2A.** `orchestrator_config.py` imports each agent's callable
  and wraps it in `LocalFunctionClient` — all six agents in one process, one venv.
  The diagrams' A2A label is correct as a *target*, not as a description. Worth
  marking target-vs-current on the board.
- The split is settled: **MCP = agent↔tools, A2A = agent↔agent.**
  Orchestrator↔domain-agent is squarely A2A.
- **A2A deliberately keeps credential provisioning out of scope** — each agent
  obtains its own credentials out-of-band. That is the property that *removes* our
  keys problem rather than managing it.
- Microsoft's multi-agent reference architecture says agents-as-services fits
  exactly our shape (multiple teams, divergent stacks, separate ownership) — but
  also recommends **starting as a modular monolith and extracting later**, to avoid
  over-engineering. So in-process was the right call; we're now hitting the
  pressure that signals extraction.
- Anthropic's orchestrator-worker pattern is essentially what `plan_trip` does.
  Their test for justifying multi-agent is that the task decomposes into
  independent parallel threads — ours does for Flights/Restaurants/Activities, and
  **doesn't for Budget**, which runs downstream. That supports the "some of these
  are tools, not agents" argument. Their reported ~15× token cost over a single
  chat is the number that makes the tradeoff concrete.

⚠️ Don't quote the claim that "A2A uses 3.1× fewer tokens and cuts cost 39%" —
it traces to a single paper relayed through vendor blogs and the primary source
was not read.

---

## 6. Next steps, in the order I'd do them

1. **Get a Travelpayouts token** (@Brinda). Highest value per unit effort on the
   whole list. Flights' deps are already satisfied; it fails only on
   `TRAVELPAYOUTS_TOKEN`. One token turns six stand-ins into one genuinely live
   agent and makes everything downstream — tracing included — mean something.
2. **Fix the Activities import path.** `orchestrator_config.py:53` imports
   `activities_agent`, which matches neither on-disk copy
   (`activities/local_activity_docs/`, `activities-agent-limeng/`). Needs the team
   to settle on one copy and one path. Cheap once decided.
3. **Stand up Phoenix against that one live agent.** Only worth doing after step 1
   — tracing stand-ins produces spans of fixed strings. `pip install` +
   `phoenix serve` + `register(auto_instrument=True)`, no agent or orchestrator
   edits.
4. **Decide the LLM provider** (open question, Vrushti's). Four providers are in
   play; standardising collapses four credential problems into one. This is also
   the decision that makes a full-pipeline demo assemblable.
5. **Decide where the UI lands.** `app.py` imports `orchestrator`, which does not
   exist on `main` — merging as-is would break `main` at import for everyone. Needs
   a base downstream of the orchestrator. Also needs a decision on whether
   `sandbox-integration` becomes *the* integration branch (see §7).
6. **Extract one agent as a real A2A service**, if time allows. Flights is the
   candidate — thin REST wrapper, no vector store. Gives measured in-process vs
   A2A numbers on the same pipeline, which is a far better writeup than six
   imports and directly answers the accuracy-vs-cost tradeoff the summary slide
   asks for.
7. **A2UI** — future-work section only. See §5c.

Smaller items: `pip install pytest` and run `budget_agent_rohan/tests/`; fix the
envelope agent's unreachable `covered=False` refusal before it is ever wired in;
resolve the stale model strings listed in `UI_BUILD_REPORT.md` §7.

---

## 7. Open decisions that are not mine to make

- **Is `sandbox-integration` the integration branch?** It is a *local* integration
  merge I made to get a working tree — it combines the orchestrator, budget and
  activities branches and is ~31 commits ahead of `main`. It is pushed because the
  UI cannot run without it. Whether it becomes the team's integration branch is a
  team call, not mine.
- **Where does the UI merge to?** See §6.5.
- **Which observability backend**, if the team disagrees with Phoenix.
- **Which LLM provider.**
- **Whether Budget should be an agent at all**, given it runs downstream and its
  work is arithmetic.

---

## 8. Known gotchas that will waste someone's afternoon

1. **A stale `TRAVEL_UI_AGENTS` in your shell** persists for the whole session and
   silently changes what you see.
   `Remove-Item Env:TRAVEL_UI_AGENTS -ErrorAction SilentlyContinue`
2. **Without `-w`**, Chainlit does not pick up edits. You will edit, see nothing
   change, and doubt yourself.
3. **No `.env` exists** — only `.env.example`. One `.env` at the repo root covers
   every agent (each calls `load_dotenv()`, which walks up; verified).
4. **Per-person `.env` doesn't compose.** Every agent is imported into one process,
   so an all-live run needs all six keys on one machine. Per-slot is the daily
   workflow; all-slots is for a rehearsed demo only.
5. **Chainlit pops `sys.path[0]`** after loading `app.py`
   (`chainlit/config.py:592` inserts, `:624` pops unconditionally). That is why
   `ui/agent_seam.py` *appends* paths and re-checks them before every call.
6. **Six stacks in one venv will keep conflicting** for reasons nobody caused —
   e.g. the Chroma embedding-function mismatch Vrushti found
   (`all-MiniLM-L6-v2` vs Chroma's default; collections built with different
   embedding functions cannot share an index).

---

## 9. State at handoff

- Working tree **clean**; everything committed and pushed.
- `origin/ui_chainlit_rohan` — the UI, all docs, this handoff.
- `origin/sandbox-integration` — the merged base it needs.
- `origin/main` **untouched** at `ec22c5c`. No PR opened, nothing merged.
- Both local Chainlit test servers stopped; no background processes left running.

Slack status has been posted through the questions/blockers list. Still unsent at
time of writing: the reply to Vrushti on A2A (§5d is the content) and the reply to
Emily on tracing (§5a) — **including the LangSmith correction above, which the
draft she'd otherwise receive did not have.**

---

## Appendix — unsent Slack drafts, kept so they aren't lost

### A. Correction to the setup block already posted

Slack mangled it; it currently reads `pip install chai` and the branch sentence
broke apart. Worth a follow-up:

> Correction on the setup block above — Slack ate it:
> ```
> git fetch origin
> git checkout ui_chainlit_rohan
> pip install chainlit truststore
> chainlit run app.py -w
> ```
> And the branch note: `ui_chainlit_rohan` has the UI, `sandbox-integration` is
> the merged tree it sits on (orchestrator + budget + activities). You need the
> second for the first to run. `sandbox-integration` is a local integration merge
> I made to get a working tree, not a team-agreed merge — the UI can't run without
> it, but whether it becomes *the* integration branch is a team call.

### B. Reply to Emily — orchestrator progress + tracing

Content is §5a. Key points: pipeline runs end to end; every agent is a stand-in;
agent-level tracing already exists (per-agent steps with input/output, `[seam]`
cause logging, `run_pipeline.py` outbound task capture); what's missing is real
spans; recommend Phoenix + OpenInference (pip only, no Docker, no account, no
egress, zero agent/orchestrator edits); state the ELv2 licence honestly; **LangSmith
carries Enterprise-only self-hosting, a 1-seat/5k-trace free tier, and cloud
egress — mention it as an optional flag, not the plan**; and note tracing only
becomes meaningful once one agent is live, which points back at the token.

### C. Reply to Vrushti — is A2A still the agreed protocol?

Content is §5d. Frame it as "yes as intent, no as implementation" — the diagram
label is ahead of the code, not wrong. Today it's `LocalFunctionClient` imports in
one process. Suggest marking target-vs-current on the board. Then: MCP↔tools vs
A2A↔agents; A2A keeps credentials out of scope, which removes our keys problem;
Microsoft's guidance that in-process-first then extract is correct, so we're at
the extraction signal rather than having built it wrong; the seam already makes
this a client swap (`SeamClient` and `LocalFunctionClient` share
`await call(task) -> str`, and `SlimSubagentClient` is stubbed). Propose extracting
Flights only, as a proof.

Two cautions carried over: **check with Brinda before proposing the Flights
extraction publicly**, and **don't quote the 3.1×/39% A2A figure** (single source,
primary not read).
