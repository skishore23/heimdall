# Heimdall

**Deterministic policy control plane for agents, tool calls, streaming, and any LLM workflow. Heimdall pairs a gateway (Bifröst), a signing control plane (Mímir), and a self-auditing enforcement stack so you can explain every blocked or passed request.**

[Docs](docs/) • [Demo](demo/demo.html) • [Quickstart](QUICKSTART.md)

---

## TL;DR

- **Policy control plane:** Define guards as data (YAML + lenses) and ship the same graph into the gateway, SDK, streaming proxy, or multi-agent orchestrations without rewriting verification logic.
- **Gateway-first deployment:** Bifröst proxies OpenAI-compatible requests, enforces signed policies, streams guard metadata, and records evidence before the upstream LLM ever sees the content.
- **Self-auditing to stop hallucinations:** Every guard decision is timestamped, signed, and replayable so you can answer “why was this tool call blocked?” with concrete guard metadata instead of guesswork.
- **Agent + tool focus:** Wrap your agents with `heimdall_sdk.wrap_llm`, protect tool arguments with `heimdall_sdk.guard_tool`, and reuse the same signed policy while switching models, streaming chunks, or cross-service tool handoffs.
- **Model-agnostic detectors:** Tier metadata is metadata only—T2 guards can call ONNX, TorchScript, external LLM APIs, or custom runtimes so you can plug whatever model makes sense for your domain.

---

## Why teams pick Heimdall

1. **Deterministic policy boundaries.** Policies can target chat inputs, streaming tokens, tool arguments/results, or orchestration handoffs without branching into new guard sets.
2. **Full audit trail.** OpenTelemetry spans, profiler metrics, SSE traces, and policy signatures (Mímir) record the exact rule, tier, timing, and evidence so compliance teams saw exactly which guard fired and why.
3. **Gateway + SDK parity.** Bifröst enforces guards for every HTTP request and streaming chunk; the SDK applies identical graphs inside agents, scripts, or offline workflows.
4. **Performance-conscious guard packs.** Fast T0/T1 rules run locally, while T2 entries can defer to any pluggable model. Built-in metadata documents budgets so you can balance safety vs. latency without sacrificing determinism.
5. **Designer-friendly docs.** Guard authoring, policy composition, and control plane concepts live in purposeful documentation; the demo surfaces evidence so you can explain stopped hallucinations to stakeholders.

---

## Example policies that ship with Heimdall

### 1. PII sanitization (mask emails/phones, stop leakages)

```yaml
policy_id: pii_sanitization
guards:
  - id: pii.redact
    target: messages[*].content
    with:
      types: ["EMAIL", "PHONE", "SSN", "CREDIT_CARD"]
      mode: mask
compose:
  root: pii_redact
```

- **CLI:** `heimdall policy lint policies/pii_sanitization.yaml`
- **SDK:** `await sdk.wrap_llm(my_llm, policy_id="pii_sanitization")`
- **Value:** sanitize any agent prompt before it hits the LLM and log what was masked.

### 2. Agent tool guard (host allowlist + evidence)

```yaml
policy_id: agent_tool_guard
guards:
  - id: tools.args.validator
    target: tool_args.arguments
    with:
      required_args:
        open_internal_url: ["url"]
      forbidden_patterns:
        open_internal_url:
          - "^(?!https://trusted\.example\.com/).*"
compose:
  tool_args: tools_args_validator
  root: tools_args_validator
```

- **CLI:** `heimdall run --policy policies/agent_tool_guard.yaml --input '{"tool_args": {"function_name": "open_internal_url", "arguments": {"url": "https://evil.example.com"}}}'`
- **SDK:** `await sdk.guard_tool(open_internal_url, "agent_tool_guard", url=target)`
- **Value:** keep multi-agent orchestrations and tool call graphs deterministic and auditable.

### 3. Streaming guard (per-chunk toxicity or policy checks)

```yaml
policy_id: streaming_toxicity
guards:
  - id: toxicity.block
    target: chunk.content
    with:
      categories: ["abuse"]
      threshold: 0.08
compose:
  root: toxicity_block
```

- **CLI:** `heimdall policy compile --policy policies/streaming_toxicity.yaml --output build/stream_policy.json`
- **SDK:** `await stream_sdk.stream_chat_with_guards(messages, policy_id="streaming_toxicity")`
- **Value:** run mid-stream enforcement and cancel the upstream call with precise guard metadata.

---

## Core components

### Heimdall engine
Guards are async functions returning `Left` (violations) or `Right` (success). Compose them with `seq`, `allOf`, `anyOf`, `kOf`, lenses, and builders so guard graphs stay pure data. The compiler produces deterministic graphs that run identically inside the gateway or SDK.

### Bifröst gateway
A FastAPI proxy that:
- Accepts OpenAI-compatible RPCs and streaming chunks
- Loads signed policies from Redis/in-memory cache
- Runs input/output/streaming guards and attaches guard metadata to responses
- Streams evidence through SSE (`/trace`) and records policy hashes for every decision
- Works with external providers (OpenAI, Bedrock, Ollama) without touching your client code

### Mímir control plane
Signs policies (Ed25519/SHA256), versions them, and hot-reloads them so enforcement always runs tamper-proof guard sets. Signed artifacts travel across environments, letting you prove a policy version executed on production with immutable evidence.

### Observability & self-auditing
OpenTelemetry spans, profiler metrics, SSE trace streaming, and policy signing let you show “Stop hallucinations” with data: guard IDs, tiers, durations, tenants, and the exact evidence that triggered the violation. Use the demo (`demo/demo.html`) to explore the evidence panel and trace signed guard executions.

---

## Getting started

1. **Update env** Create `.env` or export: `OPENAI_API_KEY`, `UPSTREAM_BASE_URL` (if using a custom target), `DEFAULT_POLICY_ID` (e.g., `enterprise_default_v1`).
2. **Start Redis** (optional) and Bifröst: `./.venv/bin/python -m bifrost.main` (or `python -m bifrost.main` if your shell already uses the illustrated virtual environment). The gateway logs policy loads and guard metadata on every request.
3. **Point clients to the gateway.** Set `base_url=http://localhost:8000/v1` and the header `x-policy-id` to the policy you signed via Mímir.
4. **Explore the demo.** `demo/demo.html` shows agent/tool flows, evidence for each guard, and the signed policy hash recorded by Mímir.
5. **Onboard policies.** Use `heimdall policy lint`/`compile` or the CLI to sign policies and refresh the gateway cache.

Need step-by-step instructions? See [Quickstart](QUICKSTART.md) and [docs/POLICY_ARCHITECTURE.md].

---

## Documentation & resources

- [Policy Enforcement Architecture](docs/POLICY_ARCHITECTURE.md) — vertical overview + evidence flow for agents, tools, and streaming.
- [Guard Authoring Guide](docs/GUARD_AUTHORING.md) — write deterministic guards with lenses, combinators, and guard packs.
- [Quickstart for Bifröst](docs/QUICKSTART_BIFROST.md) — configuration, Redis, and gateway tuning.
- [Interactive demo](demo/demo.html) — explore the evidence panel, agent flow, tool call guard, and streaming guard while the gateway is running.
- [Scripts](scripts/gateway_latency_test.py) — benchmark Bifröst with configurable bursts and capture p95/p99 latency numbers.

---

## Testing & benchmarking

- `pytest tests/unit` — guard/unit coverage
- `pytest tests/integration` — sample policy flows
- `scripts/gateway_latency_test.py` — run `python scripts/gateway_latency_test.py -n 50 -c 4 --url http://localhost:8000/v1/chat/completions --policy-id enterprise_default_v1` after the gateway is up.
- `heimdall-eval` suites — run red-team suites via `heimdall/eval_harness.py` to capture evidence for every violation.

---

Heimdall is not just another guardrail. It is a policy control plane that enforces deterministic, signed policies across agents, tools, streaming, and every LLM surface so you can stop hallucinations with tangible, auditable evidence.
