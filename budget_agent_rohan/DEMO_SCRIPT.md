# Demo script — Budget & Cost Agent

Working draft. Core demo is ~4 minutes; the extended beats are there if
there's time or if someone asks.

Run everything from `budget_cost_rohan/` with `.venv` active.
Have two terminals open, and `evaluation/results/local_*.csv` open in a
third window so the fabricated-number transcript is one click away.

---

## Opening — 20 seconds

> Budget agent. It answers one question: can they afford this, and what can
> each part cost?
>
> Data is published U.S. State Department per diem rates — 40 locations,
> 18 countries, committed to the repo so it runs offline with no API key.
> Three tools do the arithmetic in plain Python with 42 tests. The model
> picks a tool and phrases the result. It never computes a number.

Don't explain more than that up front. The rest comes out through the demo.

---

## Beat 1 — It refuses what isn't its job, and that's tested

**Run:**
```
python -m proposed_envelope_agent.agent --task "Recommend me a nice hotel in Nassau"
```

**Expect:** it declines and offers to set a budget instead.

**Say:**
> It doesn't recommend hotels, destinations, restaurants or flights. Other
> agents own those. What matters is that this isn't just an instruction in
> the prompt — it's a scored test case in my evaluation set, so if a prompt
> change ever breaks it, the test catches it rather than a user.

**Why this beat is first:** scope isolation is easy to claim and rarely
verified. Showing it as a test rather than a rule is the point.

---

## Beat 2 — It knows where its own boundary is

**Run:**
```
python -m proposed_envelope_agent.agent --task "5 days in the Maldives, budget 3000"
```

**Expect:** a single refusal naming all 18 covered countries. No retries.

**Say:**
> In Week 1 I had the opposite behaviour. One out-of-scope question
> produced **14 tool calls** — six weather, eight flight — across six
> reasoning turns, with two exact duplicates and five destinations the user
> never mentioned. It was probing to find a boundary nothing had told it
> about.
>
> The fix was in the tool docstring, not the system prompt: state exactly
> what's covered, add an explicit do-not-retry instruction, and repeat the
> coverage inside the failure message so the refusal itself carries the
> information.
>
> After that, over 7 runs: 2, 1, 2, 2, 2, 2, 1 — mean **1.71 calls,
> SD 0.49**. And in 4 of those 7 the tool wasn't called at all: the model
> read the spec and reasoned from it instead of testing it.
>
> Caveat — the before-condition was a single run, so the reduction is
> illustrative. The after-condition is the part with n=7 behind it.

**If asked how the coverage list stays accurate:**
> It's generated from the dataset at import time, not typed by hand. A
> hand-written list would start silently lying the first time the data
> changed.

---

## Beat 3 — The comparison happens once, over exact values

**Run:**
```
python -m proposed_envelope_agent.agent --demo
```

**Point at steps 3 and 4** — a plan that passes, and one that fails.

**Say:**
> The check runs once. There's no second pass, no re-query, no asking the
> model to look again — because the numbers are exact, so looking twice
> can't tell you anything looking once didn't.
>
> And it checks per category rather than totals. This plan is under budget
> overall but the lodging is over its ceiling, so it fails. A total-versus-
> total check would have passed it. Underspending on meals doesn't make an
> unaffordable hotel affordable.

**Point at step 5 — renegotiation:**
> When a ceiling doesn't work, the budget is revised rather than the trip
> refused. Optional categories give way first, the reserve is drawn on only
> after they're empty, and lodging and meals are never reduced. Every
> movement is logged so it can explain what changed and why.

---

## Beat 4 — Where it still fails (the important beat)

**Show the transcript** from `evaluation/results/local_*.csv`:

> "The trip to Barbados for 4 nights with a budget of $2000 for 2 people is
> feasible but constrained. To meet the budget, the nightly lodging cost
> must not exceed $74. **The remaining budget of $952** can be allocated to
> meals and activities."

**Then show the tool output beside it:**
```
lodging $296 · meals $1504 · activities $0 · local_transport $0 · reserve $200
```

**Say:**
> $74 is correct. $952 doesn't exist. No tool produced it, and activities
> were allocated zero.
>
> The tools were right. The arithmetic was right. The number was invented
> when the model wrote the final sentence.
>
> I ran the same question three times. Identical tool output every time.
> One run invented $952, one said activities were funded when they were
> zero, one was completely correct.

**The line to land:**
> So moving the arithmetic into deterministic code fixes the *tool*. It
> doesn't fix the *agent*. And nothing inside the agent's own loop can
> catch this, because every fact it could check against was correct.

---

## Beat 5 — The check that catches it, with no human involved

**Run:**
```
python evaluation/run_jig.py --runs 1
```

**Say:**
> The jig scores three things separately rather than blending them:
> whether the answer was the right kind of thing, whether every dollar
> figure in it traces back to a tool result, and whether the whole answer
> was correct.
>
> That middle one is the automated signal. It parses every number out of
> the final message and checks each against what the tools actually
> returned. The $952 run scores 1.0 on behaviour and 0.0 on grounding —
> right kind of answer, fabricated number. No human in the loop.

**Then the honest limitation — do not skip this:**
> It has a blind spot. In another run the agent said "covers meals and
> activities" when activities were $0, and "without any reserve left" when
> the $200 reserve was untouched. Both false, both invisible to the check,
> because neither contains a number. The signal covers quantitative claims
> and nothing else.

---

## Beat 6 — Confidence in the data changes behaviour

**Point at demo step 6.**

> 17 of my 46 source rows haven't been re-surveyed in 9 to 18 years — one
> still reads $37 a night, effective 2008. The build script flags anything
> older than 8 years.
>
> That flag isn't just logged. A destination priced from a stale row earns
> a larger contingency automatically — 15% instead of 10%. Confidence in
> the data feeds the output rather than sitting in a report.

---

## Beat 7 — What the LLM layer costs (extended)

**Run:**
```
python evaluation/run_jig.py --runs 1 --target "python evaluation/direct_path.py --task {task}" --label direct
```

> Same test set, same tools, no model at all. Direct: 9 of 9, 0.1 seconds
> a query, and it can't vary because it's deterministic. Through the agent:
> 8 of 9, 6.1 seconds, and it demonstrably varies between identical runs.
>
> Small sample, so I'd treat the gap as indicative. But it suggests the LLM
> layer earns its place where the input is genuinely unstructured, and my
> orchestrator already knows the destination and budget because it needs
> them to route.

---

## Close — 20 seconds

> Two weaknesses I'd fix next. My data is a reimbursement ceiling rather
> than a market price, so it runs high — Week 3 I want to wire live hotel
> pricing and measure how far the official ceiling sits from real rates.
> And the grounding check only sees numbers, so qualitative claims are
> still unverified.

---

## Questions worth asking, if there's an opening

- How do you get a confidence signal for qualitative claims, where there's
  no exact value to compare against? Numbers I can verify automatically;
  "activities are covered" I can't.
- If an error is introduced when the model writes the final message rather
  than during retrieval or reasoning, is an external verifier the only
  answer, or is there a self-check design that catches it?

---

## Numbers to have memorised

| | |
|---|---|
| Corpus | 40 locations, 18 countries |
| Tests | 42 |
| Week 1 tool calls | 14 → mean 1.71, SD 0.49, n=7 after |
| Stale rows | 17 of 46, 9–18 years old |
| Jig, agent path | 8/9, grounding 1.0, 6.1s median |
| Jig, direct path | 9/9, 0.1s median |
| Fabricated figure | $952, against actual activities $0 / reserve $200 |
| Variance | 3 runs, same input: 2 wrong, 1 correct |

---

## Before the demo

- [ ] `python -m pytest -q` → 42 passed
- [ ] `python -m proposed_envelope_agent.agent --demo` runs clean
- [ ] Ollama running, one live `--task` warmed up so the first call isn't slow
- [ ] The $952 transcript open in a window
- [ ] `--runs 3` completed if there's time, so variance is a number not an
      anecdote
