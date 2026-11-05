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
| `destination_recommender` | 1 | a stray merge commit; the branch is ~7,800 lines *behind* main |
| `worktree-ui-plan` | 1 | planning notes |

Already merged: `climate_timing_joel`, `destination_recommender_alice`,
`flights_Brinda`.

The branch these two files are written on, `ui_chainlit_rohan`, is 34 commits
ahead of `origin/main` and 0 behind, and is the only place all the agents plus
the orchestrator coexist. The `.env.example` therefore documents the whole
pipeline, and each row below says which branch its file comes from.

---

## 2. Variable table

R = required, O = optional. "Branch" is where the read site lives.

| Variable | Agent / component | R/O | What breaks without it | file:line | Branch |
|---|---|---|---|---|---|
| `TRAVELPAYOUTS_TOKEN` | Flights | **R** | **Import-time `KeyError`.** `import flights_agent` fails outright; nothing in the module is reachable **[run]** | `flights_agent.py:29` | main |
| `ANTHROPIC_API_KEY` | Destination | **R** | `ChatAnthropic` is constructed at module level, so failure is at import of the package, not first call **[code]** — the package docstring states this **[code]** | `destination_agent/destination_agent.py:346`; documented `destination_agent/__init__.py:14-16` | main |
| `OPENROUTER_API_KEY` | Flights slot; agentic orchestrator | **R** | The Flights slot runs on an `openrouter:` model slug, as does the agentic orchestrator's default **[code]** | `orchestrator_config.py:46`; `orchestrator_agent.py:42` | main |
| `COHERE_API_KEY` | Money & Customs | **R** | Runtime auth failure at first call, **not** a config error — see §4 | `money_customs_agent.py:24` (setdefault), consumed `:102` | `exchange_rate_emily` |
| `GEOAPIFY_API_KEY` | Destination (Geoapify tools) | O | Silent degradation. Both tools return `{"error": "GEOAPIFY_API_KEY is not configured in the .env file."}`; the agent still answers from its local corpus **[code]** | read `destination_agent/geoapify_data.py:23`, guarded `:56-58`, `:174-176` | main |
| `TRAVEL_UI_AGENTS` | Chainlit UI seam | O | Defaults to stand-ins (`ui/agent_seam.py:93-99`). Setting a slot to `real` makes that agent's credentials required **[code]** | read `ui/agent_seam.py:133`, name `:104` | `ui_chainlit_rohan` |

### Model-selection strings — separate category

None of these are credentials. All are `os.environ.get(NAME, "<default>")`, so
unset is the supported case. Default literals quoted from the code; **whether a
slug still resolves on its provider is unverified** — that needs a live billed
call and is out of scope.

| Variable | Component | In-code default | file:line |
|---|---|---|---|
| `MONEY_AGENT_MODEL` | Money & Customs (wired) | `command-r-plus-08-2024` | `money_customs_agent.py:32` |

### Read by libraries, not by this repo

No file in the repository reads `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` or
`LANGSMITH_PROJECT` — grep finds zero read sites. **[run]** They are consumed
directly by `langsmith`/`langchain` when set. They appear in
`destination_agent/.env.example:3-5`, which is why they are listed (commented out) in the root `.env.example` rather
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

Everything else fails at call time.

---

## 4. Hardcoded placeholder keys — team discussion item

One file sets a credential with `os.environ.setdefault` and a placeholder
string literal at module scope:

| file:line | variable | placeholder |
|---|---|---|
| `money_customs_agent.py:24` | `COHERE_API_KEY` | `"your-actual-cohere-key-here"` |

It is not a real key — it is clearly intended as a placeholder, and the
surrounding comment already recommends `.env` + python-dotenv for shared use
instead (`money_customs_agent.py:18-23`). Raised here for one practical reason
worth a group decision, not as a criticism:

`setdefault` means the variable is never *absent*. So an operator who forgets
the key gets a Cohere **authentication error** on the first model call, rather
than a "key not configured" message at startup. In a multi-agent pipeline where the orchestrator already converts subagent build failures into
prose (`orchestrator_config.py:130`), that difference costs real debugging
time — the itinerary comes back plausible-looking with one section replaced by
an error string.

Worth deciding as a team whether the convention should be `load_dotenv()` plus
an explicit check that raises a clear "key not configured" message at startup.
No files were changed here — this is a documentation PR.

---

## 5. Non-env prerequisites

A key alone is not always enough.

### Built artifacts

- **Self-building at runtime, no step needed:** Money & Customs
  (`money_tools.py:446-500`, fingerprinted and rebuilt on corpus change), and
  the destination corpus (`destination_data/recommend.py:295-332`). **[code]**
- **First-run model downloads.** Chroma's default embedding
  (`all-MiniLM-L6-v2` ONNX) is a ~80 MB download on first use — called out at
  `money_tools.py:429` and `destination_data/recommend.py:9`. Needs network on
  first run even though it needs no API key. **[code]**

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
`resolve_place.py:23`), Nager.Date holidays (`holidays.py:22`), and Travelpayouts'
**autocomplete** endpoint (`flights_agent.py:30`, token-free per the docstring
at `:36-37`). **[code]**

---

## 6. Minimum set to run X

### (i) Orchestrator with deterministic fakes — **zero credentials. Confirmed.**

Your assumption was right, and it is verified rather than reasoned:
`python sandbox/run_pipeline.py` completed with **exit code 0** in a worktree
with **no `.env` file anywhere** (`Get-ChildItem -Recurse -Force -Filter .env`
returned nothing) and **no credential env vars set** (a scan of `Env:` for
`API_KEY|TOKEN|ANTHROPIC|OPENROUTER|COHERE|CEREBRAS|GEOAPIFY|LANGSMITH` matched
nothing relevant). It produced the full itinerary and the gap checks.
**[run]**

Why it costs nothing: every slot is a fixed string (`sandbox/fakes.py`), so
there is no model call at all. **[code]**

The **Chainlit UI** is the same story by construction: `ui/agent_seam.py:MODES`
defaults **every** slot to `dummy`. Its extra cost is packages, not keys — `truststore` and `chainlit` (§5).

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
| Money & Customs | `COHERE_API_KEY` | ~80 MB embedding download; vector index self-builds |

### (iii) Full live pipeline — all three real

Four credentials, minimum:

```
TRAVELPAYOUTS_TOKEN     Flights      (required at import)
ANTHROPIC_API_KEY       Destination  (required at import)
COHERE_API_KEY          Money & Customs
OPENROUTER_API_KEY      Flights slot model
```

Plus, from §5: `truststore` and `chainlit` for the UI; and network access on
first run for the embedding downloads.

`GEOAPIFY_API_KEY` is genuinely optional — Destination degrades quietly without
it rather than failing, which is worth knowing precisely because it degrades
*quietly*.

Not verified, and deliberately so: whether any of the default model slugs still
resolve and bill correctly on their providers. Every one is marked unverified in
`.env.example`. Confirming them means live billed calls across three providers,
which is a separate exercise from documenting what the code reads.
