"""ask_agents must actually run slots in parallel, and weaken no guard.

Three live runs on 27 Aug 2026 showed the model would not reliably batch its own
tool calls even when the system prompt asked for it: run 3 finished with slot
wall-clock 100.7s against a 115.3s total -- no overlap at all. Parallelism was a
property of the model's mood. ask_agents makes it a property of the code.

Run: python test_fan_out.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import orchestrator
import orchestrator_agent as oa

cases = []


def check(name, cond):
    cases.append((name, bool(cond)))


class _Tracker:
    def __init__(self):
        self.live = self.peak = 0

    def client(self, slot):
        tracker = self

        class _C:
            async def call(self, task):
                tracker.live += 1
                tracker.peak = max(tracker.peak, tracker.live)
                await asyncio.sleep(0.02)
                tracker.live -= 1
                return f"{slot} answered, $10 per person"

        return _C()


FOUR = ["flights", "restaurants", "activities", "money_customs"]


def run(max_concurrency):
    orchestrator.MAX_CONCURRENCY = max_concurrency
    orchestrator._gate_lock = None
    tracker = _Tracker()
    orchestrator.get_client = tracker.client
    _, ledger, tools = oa._new_run({"travel month": "2026-09"}, "$3000")
    ask_agent, ask_agents, _ = tools
    out = asyncio.run(ask_agents(FOUR, ["t"] * 4))
    return tracker, ledger, out, ask_agent, ask_agents


# 1 -- it actually fans out, and the gate still caps it
t, ledger, out, _, _ = run(4)
check("fans out: more than one slot in flight", t.peak > 1)
check("all four ran", sorted(ledger) == sorted(FOUR))
check("every slot's reply is returned", all(f"=== {s} ===" in out for s in FOUR))

t, _, _, _, _ = run(2)
check("gate still caps concurrency at 2", t.peak <= 2)

t, _, _, _, _ = run(1)
check("gate=1 still fully serialises", t.peak == 1)

# 2 -- the budget ordering guard survives being put in a batch
orchestrator.MAX_CONCURRENCY = 4
orchestrator._gate_lock = None
orchestrator.get_client = _Tracker().client
_, ledger, tools = oa._new_run(None, "$3000")
_, ask_agents, _ = tools
out = asyncio.run(ask_agents(["budget", "flights"], ["t", "t"]))
check("budget in a batch is still refused", "Budget cannot run yet" in out)
check("budget was NOT recorded in the ledger", "budget" not in ledger)
check("its batch-mate still ran", "flights" in ledger)

# 3 -- an unknown slot is rejected, not sent
_, ledger, tools = oa._new_run(None, "")
_, ask_agents, _ = tools
out = asyncio.run(ask_agents(["nope", "flights"], ["t", "t"]))
check("unknown slot rejected inside a batch", "is not an agent" in out)
check("the valid slot in the same batch still ran", "flights" in ledger)

# 4 -- mismatched arguments are reported, not silently zipped short
_, _, tools = oa._new_run(None, "")
_, ask_agents, _ = tools
check("mismatched lengths are reported",
      "Mismatched call" in asyncio.run(ask_agents(["flights", "restaurants"], ["t"])))
check("empty batch is safe", "No slots" in asyncio.run(ask_agents([], [])))

# 5 -- trip facts still reach every slot in a batch
seen = []


def recorder(slot):
    class _C:
        async def call(self, task):
            seen.append(task)
            return "ok"

    return _C()


orchestrator.MAX_CONCURRENCY = 4
orchestrator._gate_lock = None
orchestrator.get_client = recorder
_, _, tools = oa._new_run({"travel month": "2026-09"}, "$3000")
_, ask_agents, _ = tools
asyncio.run(ask_agents(["flights", "restaurants"], ["a", "b"]))
check("trip facts prepended to every task in the batch",
      len(seen) == 2 and all("travel month: 2026-09" in t for t in seen))

passed = sum(1 for _, ok in cases if ok)
for name, ok in cases:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"\n{passed}/{len(cases)} passing")
sys.exit(0 if passed == len(cases) else 1)
