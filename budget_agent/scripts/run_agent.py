#!/usr/bin/env python3
"""
Hello World check for the Budget Cost Aggregator Agent.

Simulates what the orchestrator would send: a task string containing
priced line items from Flights/Restaurants/Activities, plus a budget.

Run with:
    python scripts/run_agent.py

Then try an interactive chat loop:
    python scripts/run_agent.py --chat
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from budget_agent.agent import build_agent  # noqa: E402


SAMPLE_TASK = """\
Destination: Cancun
Trip length: 4 days
User's stated budget: $700 total

Estimate the total trip cost for this destination and check whether \
it's feasible within the stated budget.
"""


def print_response(result: dict) -> None:
    messages = result.get("messages", [])
    if not messages:
        print("(no response)")
        return
    last = messages[-1]
    content = getattr(last, "content", last)
    print(f"\nAgent: {content}\n")


def run_hello_world() -> None:
    print("Building Budget Agent (this may take a few seconds)...")
    agent = build_agent()

    print(f"\nOrchestrator task:\n{SAMPLE_TASK}")
    result = agent.invoke({"messages": [{"role": "user", "content": SAMPLE_TASK}]})
    print_response(result)
    print("Hello World Budget Agent ran successfully. Your setup works!")


def run_chat() -> None:
    print("Building Budget Agent (this may take a few seconds)...")
    agent = build_agent()
    print("Chat with the Budget Agent. Paste a task string, or type 'exit' to stop.\n")

    history = []
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})
        result = agent.invoke({"messages": history})
        history = [
            {
                "role": m.type if hasattr(m, "type") else m["role"],
                "content": m.content if hasattr(m, "content") else m["content"],
            }
            for m in result["messages"]
        ]
        print_response(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Budget Cost Aggregator Agent")
    parser.add_argument("--chat", action="store_true", help="Start an interactive chat loop")
    args = parser.parse_args()

    if args.chat:
        run_chat()
    else:
        run_hello_world()
