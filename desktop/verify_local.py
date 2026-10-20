"""Real local-model/tool round trip without travel API calls or cloud keys."""

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["TRAVEL_LLM_PROVIDER"] = "local"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_TRACING"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""
os.environ["LANGCHAIN_API_KEY"] = ""

from langchain_core.tools import tool
from local_llm import create_travel_agent, local_model, local_settings

seen = []


@tool
def lookup_test_transport(city: str) -> dict:
    """Look up transport for a fictional test city. This is test data only."""
    seen.append(city)
    return {"city": city, "recommended_transport": "blue shuttle", "fare": 7.25, "currency": "TEST", "source": "local test fixture - not real travel data"}


def verify():
    agent = create_travel_agent(
        model=local_model(max_tokens=2048),
        tools=[lookup_test_transport],
        system_prompt="You are testing a transport tool. You must call lookup_test_transport before answering. Report its exact transport, fare and currency and label them test data. Keep the final answer under 60 words. /no_think",
    )
    result = agent.invoke({"messages": [{"role": "user", "content": "Look up transport in Testville. Use the tool and report the fare."}]}, config={"recursion_limit": 8})
    messages = result["messages"]
    answer = messages[-1].content
    calls = [call["name"] for msg in messages for call in getattr(msg, "tool_calls", [])]
    assert seen and "lookup_test_transport" in calls, "Local model did not execute the tool."
    assert "7.25" in answer and "TEST" in answer, "Local answer did not preserve the tool result."
    assert "test" in answer.lower(), "Local answer did not label test data."
    return {"status": "PASS", "base_url": local_settings()[0], "model": local_settings()[1], "tools_called": calls, "answer": answer, "cloud_llm_used": False}


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
