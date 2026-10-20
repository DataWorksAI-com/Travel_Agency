import urllib.request,json,asyncio
from local_llm import create_travel_agent, local_model
from langchain_core.tools import tool
from orchestrator import plan_trip

with urllib.request.urlopen('http://127.0.0.1:8000/',timeout=10) as r: assert r.status==200
with urllib.request.urlopen('http://127.0.0.1:8000/project/translations?language=zh-CN',timeout=10) as r:
    translated=json.load(r)
    assert translated['translation']['common']['actions']['cancel']=='Cancel'
print('PASS: HTTP and English translations',flush=True)
seen=[]
@tool
def lookup_test_transport(city: str) -> dict:
    """Return fictional transport test data, never real travel information."""
    seen.append(city)
    return {'transport':'blue shuttle','fare':7.25,'currency':'TEST'}
agent=create_travel_agent(model=local_model(max_tokens=350),tools=[lookup_test_transport],system_prompt='Call lookup_test_transport before answering. Report its fare and currency as fictional test data. Keep the final answer under 40 words. /no_think')
result=agent.invoke({'messages':[{'role':'user','content':'Look up transport in Testville and report the fare.'}]})
answer=result['messages'][-1].content
assert seen and '7.25' in answer and 'TEST' in answer,answer
print('PASS: local model/tool round trip: '+answer,flush=True)
async def check():
    from desktop.dining_policy import UNAVAILABLE
    assert await plan_trip('Recommend a restaurant in New Hampshire')==UNAVAILABLE
    print('PASS: restaurant guard',flush=True)
    result=await plan_trip('Colorado')
    assert 'unverified' in result.lower(),result
    assert '=== Flights ===' not in result,result
    assert 'unavailable' not in result.lower(),result
    print('PASS: uncovered city introduction: '+result,flush=True)
asyncio.run(check())
