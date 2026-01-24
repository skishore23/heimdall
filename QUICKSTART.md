# Quickstart

Get Heimdall running with a gateway, an example policy, and an agent/tool guard in under 5 minutes.

## 1. Install

```bash
pip install -e .[gateway,cli,streaming]
```

> Need ML-backed detectors? Install additional extras: `pip install heimdall[onnx]` or plug your own runtime (ONNX, TorchScript, or an HTTP/LLM API).

## 2. Configure environment

Create a `.env` (or export) with values you already manage:

```bash
OPENAI_API_KEY=sk-…          # Your upstream key (OpenAI, Azure, Bedrock, etc.)
DEFAULT_POLICY_ID=enterprise_default_v1  # The policy you will enforce
REDIS_URL=redis://localhost:6379         # Optional cache for signed policies
UPSTREAM_BASE_URL=https://api.openai.com  # Optional override if proxying elsewhere
```

Do **not** commit secrets. Heimdall will fail fast if `OPENAI_API_KEY` is missing.

## 3. Start the gateway

```bash
./.venv/bin/python -m bifrost.main
```

Bifröst loads signed policies, enforces input/output/streaming guards, and streams guard metadata for every request. While the gateway runs, the evidence panel in [`demo/demo.html`](demo/demo.html) shows the same guard decisions and Mímir signatures recorded for every explainable block.

## 4. Call the gateway

Point any OpenAI-compatible client to Bifröst and pass the policy header:

```python
from openai import AsyncOpenAI
client = AsyncOpenAI(base_url="http://localhost:8000/v1", api_key="any-value")
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Summarize the plan"}],
    extra_headers={"x-policy-id": "enterprise_default_v1"}
)
```

The gateway attaches guard metadata under `response.guardrails` and returns violations before the downstream LLM sees the content.

## 5. Wrap agents & tool calls

In a scripted or agentic flow, load your policy once and guard tools deterministically:

```python
from heimdall_sdk import HeimdallSDK
sdk = HeimdallSDK()
await sdk.load_policy("policies/enterprise_default_v1.yaml")
await sdk.guard_tool(my_open_internal_url, "agent_tool_guard", url="https://trusted.example.com/api")
```

Use `wrap_llm` for chat completions and `stream_chat_with_guards` for streaming flows—the same policy graph applies everywhere.

## 6. Explore streaming enforcement

Build a policy that targets `chunk.content` (see `policies/streaming_toxicity.yaml`). Compile it via:

```bash
heimdall policy compile --policy policies/streaming_toxicity.yaml --output build/stream_policy.json
```

Feed the compiled policy into the streaming proxy or SDK to cancel on-violation chunks.

## 7. Next steps

- [Policy architecture](docs/POLICY_ARCHITECTURE.md) explains the guard graph, tiers, and evidence flow.
- [`demo/demo.html`](demo/demo.html) showcases agent plans, policy switching, and guard evidence from Mímir.
- `scripts/gateway_latency_test.py` lets you benchmark Bifröst with configurable bursts.

When you are ready to open source, the README and docs describe your agent-first positioning, the evidence trail, and how the control plane stops hallucinations.
