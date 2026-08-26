"""Tests for the slot concurrency gate in orchestrator.ask_slot.

The gate exists because a free-tier OpenRouter key reserves credit per in-flight
request, so three parallel deep agents starve whichever arrives last: measured
"asked 2048, could afford 1015" with $4.81 of $5 unused.

Run: python test_concurrency_gate.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import orchestrator

cases = []


def check(name, cond):
    cases.append((name, bool(cond)))


class _Tracker:
    """Records how many calls are in flight at once."""

    def __init__(self, delay=0.02):
        self.live = 0
        self.peak = 0
        self.order = []
        self.delay = delay

    def client(self, slot):
        tracker = self

        class _C:
            async def call(self, task):
                tracker.live += 1
                tracker.peak = max(tracker.peak, tracker.live)
                tracker.order.append(slot)
                await asyncio.sleep(tracker.delay)
                tracker.live -= 1
                return f"{slot} ok, $10 per person"

        return _C()


def run_parallel(max_concurrency):
    """Fire the parallel three at once under a given gate setting."""
    orchestrator.MAX_CONCURRENCY = max_concurrency
    orchestrator._gate_lock = None  # rebuild the gate for this setting
    tracker = _Tracker()
    orchestrator.get_client = tracker.client

    async def main():
        return await asyncio.gather(*(
            orchestrator.ask_slot(s, "t") for s in ("flights", "restaurants", "activities")
        ))

    replies = asyncio.run(main())
    return tracker, replies


# 1 -- default (1) fully serialises
t, replies = run_parallel(1)
check("gate=1: never more than one call in flight", t.peak == 1)
check("gate=1: all three still ran", len(t.order) == 3)
check("gate=1: all three replies returned", len(replies) == 3 and all(replies))

# 2 -- a higher setting allows real parallelism (so the knob does something)
t, _ = run_parallel(3)
check("gate=3: more than one call overlaps", t.peak > 1)
check("gate=3: peak does not exceed the limit", t.peak <= 3)

# 3 -- 2 is respected as a middle setting
t, _ = run_parallel(2)
check("gate=2: peak is at most 2", t.peak <= 2)

# 4 -- disabled means ungated
t, _ = run_parallel(0)
check("gate=0: gate is off", orchestrator._gate() is None)
check("gate=0: all three still ran", len(t.order) == 3)

# 5 -- the gate does not break the secret scrub layered in the same function
orchestrator.MAX_CONCURRENCY = 1
orchestrator._gate_lock = None
import os
os.environ["TRAVELPAYOUTS_TOKEN"] = "c02dab7f91e4471aa9f3d5e8b7c61d02"


class _Leaky:
    async def call(self, task):
        return "failed: token=c02dab7f91e4471aa9f3d5e8b7c61d02"


orchestrator.get_client = lambda slot: _Leaky()
out = asyncio.run(orchestrator.ask_slot("flights", "t"))
check("gate + scrub: credential still redacted", "c02dab" not in out)
check("gate + scrub: names the variable", "TRAVELPAYOUTS_TOKEN" in out)

# 6 -- an unknown slot is still rejected before the gate is taken
try:
    asyncio.run(orchestrator.ask_slot("nope", "t"))
    check("unknown slot raises", False)
except ValueError:
    check("unknown slot raises", True)

passed = sum(1 for _, ok in cases if ok)
for name, ok in cases:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"\n{passed}/{len(cases)} passing")
sys.exit(0 if passed == len(cases) else 1)
