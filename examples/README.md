# Guardrails Examples

Heimdall can protect everything from single-agent prompts to multi-tool orchestration. The examples here keep the focus on agentic flows—wrap LLMs, guard tool calls, and tunnel requests through Bifröst without tying every demo to PII or toxicity.

## 1. `examples/quickstart.py` — Wrap an LLM call
**Best for:** In-process control, embedded SDK enforcement

```python
from heimdall_sdk import HeimdallSDK

sdk = HeimdallSDK()
await sdk.load_policy("policies/enterprise_default_v1.yaml")

# Wrap your LLM call
guarded_llm = lambda **kwargs: sdk.wrap_llm(call_llm, "enterprise_default_v1", **kwargs)

# Use it
response = await guarded_llm(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Summarize the latest release notes."}]
)
```

## 2. `examples/gateway.py` — Proxy any client
**Best for:** Zero code changes—point your OpenAI client at Bifröst

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="http://localhost:8000/v1",
    api_key=os.getenv("OPENAI_API_KEY")
)

response = await client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Perform a policy review in bullet points."}],
    extra_headers={"x-policy-id": "enterprise_default_v1"}
)
```

## 3. `examples/agent_tool_flow.py` — Guard tool calls
**Best for:** Agents invoking internal tools/hooks

```bash
python examples/agent_tool_flow.py
```

This example loads `policies/agent_tool_guard.yaml`, lets you call `open_internal_url`, and shows both allowed and blocked tool calls while highlighting how `guard_tool` uses the same policy as the gateway.

## Run the demos

```bash
# Start gateway if you want to exercise HTTP proxy examples
python -m bifrost.main

# Run examples
python examples/quickstart.py
python examples/gateway.py
python examples/agent_tool_flow.py
```

## Policy files referenced

- `enterprise_default_v1.yaml` — Safe defaults for chat plus analytics
- `business_financial_v1.yaml` — Financial checklist
- `permissive_v1.yaml` — Minimal policy for quick iteration
- `agent_tool_guard.yaml` — Agent-focused tool guard (new)

## Pick a flow

- Need a guarded SDK call? → `examples/quickstart.py`
- Need zero code changes? → `examples/gateway.py`
- Need tool or agent assurances? → `examples/agent_tool_flow.py`
