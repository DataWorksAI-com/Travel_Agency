# Environment and prerequisites

Companion to the root `.env.example`. What every environment variable gates,
what breaks without it, and what the system needs that is *not* an environment
variable at all.

Scope of the audit: every `.py` file in the tree, plus the tips of the five
remote branches not yet merged to `main`. Discovery was by grep for
`os.getenv`, `os.environ.get`, `os.environ[`, `os.environ.setdefault` and
`load_dotenv`, extended by hand to the keys that provider SDKs read implicitly
(`ChatAnthropic`, `ChatCohere`, `init_chat_model`) since those never appear in
a grep but are just as required.

Each claim is tagged **[run]** (verified by executing it), **[code]** (read at
the cited line), or **[inf]** (inference, stated as such).

> Produced with AI assistance (Claude Code), reviewed by Rohan Shivakumar.

---

## 1. Where the code actually lives

This matters before the table makes sense.

`origin/main` (78 files) does **not** yet contain the orchestrator, the UI, or
the Money & Customs agent. Two open PRs bring them: **[run]**
(`gh pr list --state open`; `git ls-tree -r --name-only origin/main | wc -l`)

| PR | branch | brings |
|---|---|---|
| **#21** | `ui_chainlit_rohan` | `orchestrator.py`, `orchestrator_agent.py`, `orchestrator_config.py`, `subagent_client.py`, `ui/`, `sandbox/`, `evaluation/`, root `.env.example` — **and** Emily's `money_customs_agent.py` + `money_tools.py`, since this branch carries her work as an ancestor |
| **#22** | `exchange_rate_emily` | `money_customs_agent.py`, `money_tools.py`, `agent.py` |

An earlier version of this section said the orchestrator "arrives with
`exchange_rate_emily`". That was true of the original shell, which Emily
designed and handed over, and it is no longer true of the code: the
orchestrator, the seam and the UI are owned and developed here, on
`ui_chainlit_rohan`, and nothing in `orchestrator*.py`, `subagent_client.py` or
`ui/` imports anything that exists only on her branch. The dependency is
historical attribution, not a code path. **[run]**
(`grep -rniE "emily|exchange_rate" --include=*.py .` returns no import from a
branch-specific module)

Remote branches still ahead of `origin/main`: **[run]**

| branch | commits ahead | note |
|---|---|---|
| `ui_chainlit_rohan` | 56 | PR #21, open |
| `sandbox-integration` | 19 | fully contained in `ui_chainlit_rohan`; no separate merge needed |
| `exchange_rate_emily` | 11 | PR #22, open |
| `budget_cost_rohan` | 7 | `budget_agent_rohan/` — now `proposed_envelope_agent/`, wired to no slot |
| `destination_recommender` | 1 | a stray merge commit; the branch is ~7,800 lines *behind* main |
| `worktree-ui-plan` | 1 | planning notes |

`activities_limeng` and `activities_jainam` are merged (PRs #20 and earlier);
so are `budget-agent-shashank`, `climate_timing_joel`,
`destination_recommender_alice`, `flights_Brinda` and
`restaurant_finder_vrushti`.

Already merged: `budget-agent-shashank`, `climate_timing_joel`,
`destination_recommender_alice`, `flights_Brinda`, `restaurant_finder_vrushti`.

The branch these two files are written on, `ui_chainlit_rohan`, is 34 commits
ahead of `origin/main` and 0 behind, and is the only place all six agents plus
the orchestrator coexist. The `.env.example` therefore documents the whole
pipeline, and each row below says which branch its file comes from.

---

## 2. Variable table

R = required, O = optional. "Branch" is where the read site lives.

| Variable | Agent / component | R/O | What breaks without it | file:line | Branch |
|---|---|---|---|---|---|
| `TRAVELPAYOUTS_TOKEN` | Flights | **R** | **Import-time `KeyError`.** `import flights_agent` fails outright; nothing in the module is reachable **[run]** | `flights_agent.py:29` | main |
| `ANTHROPIC_API_KEY` | Destination | **R** | `ChatAnthropic` is constructed at module level, so failure is at import of the package, not first call **[code]** — the package docstring states this **[code]** | `destination_agent/destination_agent.py:346`; documented `destination_agent/__init__.py:14-16` | main |
| `ANTHROPIC_API_KEY` | Budget (Shashank) | O | Optional *if* `OPENROUTER_API_KEY` is set. With neither, `load_settings()` raises `RuntimeError` at first `build_agent()` **[run]** | `budget_agent/config.py:30`, raise at `:43-49` | main |
| `OPENROUTER_API_KEY` | Budget (Shashank) | O | Fallback provider. See row above | `budget_agent/config.py:31` | main |
| `OPENROUTER_API_KEY` | Budget (Rohan) | **R** | Default model slug is `openrouter:…`, so the provider SDK has no credential; runtime auth failure at first model call **[inf]** | `budget_agent_rohan/proposed_envelope_agent/agent.py:260`, default at `:232`, used at `:265` | `budget_cost_rohan` |
| `OPENROUTER_API_KEY` | Activities | **R** | Same shape — `DEEP_AGENT_MODEL` defaults to an `openrouter:` slug **[inf]** | `activities/local_activity_docs/activities_agent.py:187`; `activities-agent-limeng/activities_agent.py:78` | both Activities branches |
| `OPENROUTER_API_KEY` | Restaurants | O | Only if you override the model to an `openrouter:` slug; the default is local Ollama **[code]** | `restaurant_agent/.env.template:1-4` | main |
| `COHERE_API_KEY` | Money & Customs | **R** | Runtime auth failure at first call, **not** a config error — see §4 | `money_customs_agent.py:24` (setdefault), consumed `:102` | `exchange_rate_emily` |
| `GEOAPIFY_API_KEY` | Destination (Geoapify tools) | O | Silent degradation. Both tools return `{"error": "GEOAPIFY_API_KEY is not configured in the .env file."}`; the agent still answers from its local corpus **[code]** | read `destination_agent/geoapify_data.py:23`, guarded `:56-58`, `:174-176` | main |
| `OPENTRIPMAP_API_KEY` | Activities (tier-3 fallback) | O | Silent degradation. Tool returns `{"error": "OPENTRIPMAP_API_KEY is not set in the environment."}`; tiers 1–2 unaffected **[code]** | `activities/local_activity_docs/mcp_opentripmap_server.py:15`, guarded `:39-40`; forwarded to subprocess at `activities_agent.py:200`. Limeng's copy: `activities-agent-limeng/mcp_opentripmap_server.py:27` **[code]** | Activities branches |
| `CEREBRAS_API_KEY` | *(unwired)* `agent.py` | — | Nothing. See §5 | `agent.py:23` | `exchange_rate_emily` |
| `RESTAURANT_AGENT_LIVE_EXPANSION` | Restaurants | O | Defaults ON. Set to `0/false/no/off` and an uncovered city degrades to the coverage refusal instead of a live fetch **[code]** | `restaurant_agent/restaurant_finder.py:544-545` | main |
| `TRAVEL_UI_AGENTS` | Chainlit UI seam | O | Defaults to stand-ins (`ui/agent_seam.py:93-99`). Setting a slot to `real` makes that agent's credentials required **[code]** | read `ui/agent_seam.py:133`, name `:104` | `ui_chainlit_rohan` |

### Model-selection strings — separate category

None of these are credentials. All are `os.environ.get(NAME, "<default>")`, so
unset is the supported case. Default literals quoted from the code; **whether a
slug still resolves on its provider is unverified** — that needs a live billed
call and is out of scope.

| Variable | Component | In-code default | file:line |
|---|---|---|---|
| `MONEY_AGENT_MODEL` | Money & Customs (wired) | `command-r-plus-08-2024` | `money_customs_agent.py:32` |
| `MONEY_AGENT_MODEL` | `agent.py` (unwired) | `gpt-oss-120b` | `agent.py:31` |
| `BUDGET_AGENT_MODEL` | Budget (Rohan) | `openrouter:openai/gpt-oss-20b:free` | read `budget_agent_rohan/proposed_envelope_agent/agent.py:260`, literal `:232`; also `check_model.py:22` |
| `ANTHROPIC_MODEL` | Budget (Shashank) | `claude-sonnet-4-6` | `budget_agent/config.py:35` |
| `OPENROUTER_MODEL` | Budget (Shashank) | `anthropic/claude-sonnet-4.5` | `budget_agent/config.py:40` |
| `RESTAURANT_AGENT_MODEL` | Restaurants | `ollama:lfm2.5` | `restaurant_agent/restaurant_agent_ollama.py:96` |
| `DEEP_AGENT_MODEL` | Activities (both variants) | `openrouter:z-ai/glm-5.2` | `activities/local_activity_docs/activities_agent.py:187`; `activities-agent-limeng/activities_agent.py:78` |
| `OLLAMA_EMBED_MODEL` | Activities (Jainam) | `nomic-embed-text` | `activities/local_activity_docs/activities_agent.py:61`; `build_vector_index.py:22` |

One collision worth knowing: **`MONEY_AGENT_MODEL` is one name serving two
agents on two different providers.** Setting it affects whichever module is
imported, and a Cohere slug in a Cerebras agent (or vice versa) will fail at
the provider, not at config time. **[code]**

### Read by libraries, not by this repo

No file in the repository reads `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` or
`LANGSMITH_PROJECT` — grep finds zero read sites. **[run]** They are consumed
directly by `langsmith`/`langchain` when set. They appear in
`destination_agent/.env.example:3-5` and `budget_agent_rohan/.env.example:9-13`,
which is why they are listed (commented out) in the root `.env.example` rather
than dropped silently.

### Hardcoded model slugs — no variable, no override

Two model choices are not configurable at all: `flights_agent.py:192`
(`openrouter:anthropic/claude-sonnet-4.5`) and `subagent_client.py:81` (same
slug, as a `spec.get` default). **[code]** Changing either needs a code edit.
Destination is a third — `destination_agent/destination_agent.py:347` pins
`claude-haiku-4-5` with no env override. **[code]**

---

## 3. Import-time hard failures

Variables whose absence breaks `import`, not the first call. These are the ones
that bite in integration, because the orchestrator's lazy-build guard
(`orchestrator_config.py:111-133`) turns them into a `"[<slot>
unavailable] …"` string rather than a visible crash — the failure is
swallowed and shows up as a degraded itinerary.

1. **`TRAVELPAYOUTS_TOKEN`** — `flights_agent.py:29`,
   `TP_TOKEN = os.environ["TRAVELPAYOUTS_TOKEN"]`. A bare subscript at module
   scope. **Verified by running** in a shell with no `.env` and no key set:

   ```
   File "flights_agent.py", line 29, in <module>
       TP_TOKEN = os.environ["TRAVELPAYOUTS_TOKEN"]
   KeyError: 'TRAVELPAYOUTS_TOKEN'
   ```

   **This is the only bare-subscript env read in the entire tree.** Grep for
   `os.environ[` across all `*.py` returns exactly this one site, on `main` and
   on all five unmerged branch tips. **[run]**

2. **`ANTHROPIC_API_KEY`** — not a subscript, but structurally the same
   problem: `destination_agent/destination_agent.py:346` constructs
   `ChatAnthropic` at module level, and `destination_agent/__init__.py:19-20`
   imports that module, so `from destination_agent import answer` (what
   `orchestrator_config.py:26` does) executes it. The package docstring
   confirms the intent: *"importing this package … constructs ChatAnthropic and
   the deep agent at module level. That needs ANTHROPIC_API_KEY"*
   (`__init__.py:13-16`). **[code]** Whether `ChatAnthropic` itself raises on a
   missing key, versus deferring to the first request, is library behaviour I
   could not verify here — `langchain_anthropic` is not installed in this
   worktree's venv. Flagged as **[inf]**, not asserted.

Everything else fails at call time: `budget_agent/config.py:43` raises
`RuntimeError` from inside `load_settings()`, which `build_agent()` calls
(`budget_agent/agent.py:94`) — **verified by running** `load_settings()` with no
keys, which raised `RuntimeError: No API key found.` **[run]**

---

## 4. Hardcoded placeholder keys — team discussion item

Two files set a credential with `os.environ.setdefault` and a placeholder
string literal at module scope:

| file:line | variable | placeholder |
|---|---|---|
| `money_customs_agent.py:24` | `COHERE_API_KEY` | `"your-actual-cohere-key-here"` |
| `agent.py:23` | `CEREBRAS_API_KEY` | `"KEYKEYKEY_THISISWHEREITGOES"` |

Neither is a real key — both are clearly intended as placeholders, and the
surrounding comments in both files already recommend `.env` + python-dotenv for
shared use instead (`money_customs_agent.py:18-23`, `agent.py:17-22`). Raised
here for one practical reason worth a group decision, not as a criticism:

`setdefault` means the variable is never *absent*. So an operator who forgets
the key gets a Cohere/Cerebras **authentication error** on the first model
call, rather than a "key not configured" message at startup. In a six-agent
pipeline where the orchestrator already converts subagent build failures into
prose (`orchestrator_config.py:130`), that difference costs real debugging
time — the itinerary comes back plausible-looking with one section replaced by
an error string.

Worth deciding as a team whether the convention should be `load_dotenv()` plus
an explicit check, matching what `budget_agent/config.py:43-49` already does
(it raises with the signup URLs in the message, which is the clearest failure
mode in the repo). No files were changed here — this is a documentation PR.

Related: `budget_agent/config.py:34` and `:39` treat a key that still starts
with its placeholder prefix (`sk-ant-your-key-here`, `sk-or-your-key-here`) as
absent. Copying `.env.example` to `.env` and forgetting to edit it therefore
produces the correct error rather than a bad-auth one. **[code]** That is the
pattern the other agents could adopt.

---

## 5. Variables read only by unwired code

`CEREBRAS_API_KEY` (`agent.py:23`) and `agent.py`'s `MONEY_AGENT_MODEL` default
(`agent.py:31`) are read only by `agent.py`, an earlier Cerebras-based Money &
Customs variant. **Nothing imports it.** `orchestrator_config.py:79` wires
Money & Customs through `from money_customs_agent import answer`, and grep
finds no other `import agent` anywhere in the tree. **[run]**

This matters because `CEREBRAS_API_KEY` was the *only* variable documented in
the previous root `.env.example` — the one thing the team had written down was
for a module the pipeline does not use. It is retained in the new file under an
explicit "not wired into the pipeline" heading rather than deleted, since the
read site is real and someone running `agent.py` directly still needs it.

**Removed from the old `.env.example`:** nothing. Both of its entries
(`CEREBRAS_API_KEY`, `MONEY_AGENT_MODEL`) survive, relabelled and moved to the
unwired section with the reason stated inline.

---

## 6. Non-env prerequisites

A key alone is not enough for four of the six agents.

### Local services

- **Ollama** — Restaurants' default chat model is `ollama:lfm2.5`
  (`restaurant_agent/restaurant_agent_ollama.py:96`; `:99` names
  `ollama:granite4.1:3b` as a lighter alternative). Activities (Jainam's
  variant) needs an embedding model pulled locally; the build script says so
  directly: `ollama pull nomic-embed-text`
  (`activities/local_activity_docs/build_vector_index.py:5-6`, model name at
  `:22`). **[code]** Neither agent works offline without Ollama running.

### Built artifacts

- **Budget (Shashank) — build required, enforced.** `budget_agent/tools/rag_tools.py:33-37`
  raises `RuntimeError: Vector store not found at … Run
  `python scripts/build_vectorstore.py` first.` Build script:
  `budget_agent/scripts/build_vectorstore.py`, persisting to
  `budget_agent/chroma_db` (`:33`). **[code]**
- **Activities (Jainam) — build required.** `python build_vector_index.py`
  writes `activities/local_activity_docs/vector_index` (`:20`), read back at
  `activities_agent.py:89-90`. Note `:19` computes `DOCS_DIR` as
  `<script dir>/local_activity_docs` while the script already lives in
  `activities/local_activity_docs/`, so the JSON files may not be found from
  that path — worth checking with Jainam before relying on this step. **[code]**
- **Activities (Limeng) — build required.** `python build_vector_db.py`
  (`activities-agent-limeng/build_vector_db.py:41`) writes `./chroma_db`
  (`:22`) — a path **relative to the current working directory**, and
  `activities_agent.py:73` reads it the same relative way, so both must be run
  from the same directory. **[code]**
- **Self-building at runtime, no step needed:** Restaurants
  (`restaurant_finder.py:166-181`, `get_or_create_collection`), Money & Customs
  (`money_tools.py:446-500`, fingerprinted and rebuilt on corpus change), and
  the destination corpus (`destination_data/recommend.py:295-332`). **[code]**
- **First-run model downloads.** Chroma's default embedding
  (`all-MiniLM-L6-v2` ONNX) is a ~80 MB download on first use — called out at
  `restaurant_agent/restaurant_finder.py:11`, `money_tools.py:429` and
  `destination_data/recommend.py:9`. Budget (Shashank) pulls
  `sentence-transformers/all-MiniLM-L6-v2` via HuggingFace
  (`budget_agent/tools/rag_tools.py:23`). Needs network on first run even
  though neither needs an API key. **[code]**

### Subprocesses

- **Activities MCP stdio server.** Both variants spawn
  `python mcp_opentripmap_server.py` as a stdio MCP subprocess —
  `activities/local_activity_docs/activities_agent.py:191-204` and
  `activities-agent-limeng/activities_agent.py:203-209`. **[code]** Requires
  `python` resolvable on `PATH` (the command is the literal string `"python"`,
  not `sys.executable`, so a venv-only interpreter will not be found). Jainam's
  version forwards `OPENTRIPMAP_API_KEY` into the child environment explicitly
  (`:198-201`); Limeng's does not pass an `env` at all and relies on
  inheritance. Limeng's wraps the whole thing in `try/except` and continues
  with local tools only on failure (`:211-212`); Jainam's does not.

### Packages that gate the entry point

- **`truststore`** — `app.py:22-24` injects it into `ssl` before any import
  that could open HTTPS, with the reason in the comment: on this network,
  without it, "calls hang ~5 minutes and then fail with no useful error."
  **[code]** The UI will not import without the package present.
- **`chainlit`** — the UI is launched as `chainlit run app.py -w`
  (`app.py:14`). **[code]**

### Keyless external APIs

Worth recording so nobody hunts for a key that does not exist: Frankfurter
(`money_tools.py:88`), World Bank (`:660`), Open-Meteo geocoding/marine/archive
(`destination_data/build_corpus.py:39-41`, `climate.py:27`,
`resolve_place.py:23`), Nager.Date holidays (`holidays.py:22`), Overpass and
Nominatim (`restaurant_agent/restaurants_live.py:46`, `:92`), and Travelpayouts'
**autocomplete** endpoint (`flights_agent.py:30`, token-free per the docstring
at `:36-37`). **[code]**

---

## 7. Minimum set to run X

### (i) Orchestrator with deterministic fakes — **zero credentials. Confirmed.**

Your assumption was right, and it is verified rather than reasoned:
`python sandbox/run_pipeline.py` completed with **exit code 0** in a worktree
with **no `.env` file anywhere** (`Get-ChildItem -Recurse -Force -Filter .env`
returned nothing) and **no credential env vars set** (a scan of `Env:` for
`API_KEY|TOKEN|ANTHROPIC|OPENROUTER|COHERE|CEREBRAS|GEOAPIFY|LANGSMITH` matched
nothing relevant). It produced the full six-slot itinerary and the gap checks.
**[run]**

Why it costs nothing: every slot is a fixed string (`sandbox/fakes.py`, plus a
budget stand-in defined in `run_pipeline.py`), so there is no model call at all.
Budget used to run the envelope agent's real no-LLM path here; that agent is no
longer wired to any slot. **[code]**

The **Chainlit UI** is the same story by construction: `ui/agent_seam.py:MODES`
defaults **every** slot to `dummy`. Its extra cost is packages, not keys — `truststore` and `chainlit` (§6).

One caveat that cost me a moment: **`TRAVEL_UI_AGENTS` was already set to
`money_customs=real`** in the shell I audited from. **[run]** That does not
affect `run_pipeline.py` (it monkeypatches `orchestrator.get_client` directly
and never consults the seam), but it *would* silently make the UI require
`COHERE_API_KEY`. If the UI asks for a key you did not expect, check that
variable in your shell first.

### (ii) Each agent individually

| Agent | Credentials | Also needs |
|---|---|---|
| Flights | `TRAVELPAYOUTS_TOKEN` (or it will not even import) | — |
| Destination | `ANTHROPIC_API_KEY`; `GEOAPIFY_API_KEY` for the Geoapify tools | ~80 MB embedding download on first corpus query |
| Restaurants | **none** | Ollama running with `lfm2.5`; ~80 MB embedding download. Add `OPENROUTER_API_KEY` only if you override the model |
| Budget (Shashank) | `ANTHROPIC_API_KEY` **or** `OPENROUTER_API_KEY` | `python scripts/build_vectorstore.py` first — hard `RuntimeError` otherwise |
| Budget (Rohan) — *not wired; proposed future work* | `OPENROUTER_API_KEY` | none for the no-LLM path |
| Activities | `OPENROUTER_API_KEY`; `OPENTRIPMAP_API_KEY` for tier 3 | vector build step; `python` on `PATH` for the MCP subprocess; Ollama + `nomic-embed-text` for Jainam's variant |
| Money & Customs | `COHERE_API_KEY` | ~80 MB embedding download; vector index self-builds |

### (iii) Full live pipeline — all six real

Five credentials, minimum:

```
TRAVELPAYOUTS_TOKEN     Flights      (required at import)
ANTHROPIC_API_KEY       Destination  (required at import)
COHERE_API_KEY          Money & Customs
OPENROUTER_API_KEY      Activities + Budget (Rohan) — also covers Budget (Shashank)
OPENTRIPMAP_API_KEY     Activities tier-3 fallback (skip and lose uncovered cities)
```

Plus, from §6: Ollama running for Restaurants; the Budget and Activities vector
builds; `python` on `PATH`; `truststore` and `chainlit` for the UI; and network
access on first run for the embedding downloads.

`GEOAPIFY_API_KEY` is genuinely optional — Destination degrades quietly without
it rather than failing, which is worth knowing precisely because it degrades
*quietly*.

Not verified, and deliberately so: whether any of the default model slugs still
resolve and bill correctly on their providers. Every one is marked unverified in
`.env.example`. Confirming them means live billed calls across four providers,
which is a separate exercise from documenting what the code reads.
