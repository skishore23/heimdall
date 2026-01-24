# Demo / Evidence Center

Heimdall's demo showcases the **deterministic policy control plane** in action: Bifröst enforces signed policies, the SDK protects agent tool calls, and Mímir surfaces evidence for every guard decision so you can stop hallucinations with data.

## What the demo does

- **Policy + evidence cards** show the active policy hash, the gateway health, and a running log of guard IDs that fired in each scenario.
- **Prompt deck** runs a curated list of allowed and risky prompts under the selected policy so you can see Heimdall explain each guard decision.
- **Tool guard** lets you test host allow/deny lists and instantly see whether Heimdall blocked or allowed the request.
- **Streaming guard** demonstrates how fast T0 guards can stop suspicious chunks before they reach the model.

Every entry in the evidence feed includes the guard name, tier, guard status, policy ID, and the timestamp recorded by Mímir.

## Setup

1. **Set your secrets** before starting anything:
   ```bash
   export OPENAI_API_KEY=sk-…            # Your upstream key
   export DEFAULT_POLICY_ID=enterprise_default_v1
   export REDIS_URL=redis://localhost:6379   # Optional cache
   ```
2. **Start Bifröst** in the project root:
   ```bash
   ./.venv/bin/python -m bifrost.main
   ```
   The gateway runs on `http://localhost:8000`, loads signed policies from `policies/`, and emits guard metadata and policy hashes for every request.
3. **Start the demo server**:
   ```bash
   python demo/server.py
   ```
   This will open `http://localhost:3000` in your browser and serve the interactive UI.

## Using the interface

- The **Gateway status** card polls `/health` and highlights whether the proxy is online.
- The **Policy selector** keeps the same guard graph across every scenario—changing it updates the Mímir signature and instantly shifts enforcement.
- Every scenario logs a summary of the response, and the **evidence feed** shows all guard metadata (IDs, tiers, statuses, and notes).
- If the gateway is offline or a policy is missing, the UI surfaces the error and keeps the evidence feed updated for easy troubleshooting.

## Policies in the demo

| Policy | Description |
|--------|-------------|
| `enterprise_default_v1` | Full enterprise coverage: PII, politics, toxicity, schema, and tool guards.
| `business_financial_v1` | Financial compliance + business guard set.
| `agent_tool_guard` | Tool argument validation for `open_internal_url`.
| `enterprise_default_v1` | Full enterprise coverage: PII, politics, toxicity, schema, and tool guards.
| `agent_tool_guard` | Tool argument validation for `open_internal_url`.
| `business_financial_v1` | Financial compliance + business guard set.

## Testing scenarios

1. **Prompt deck:** Click *Allowed prompts* for safe instructions or *Risky prompts* for content Heimdall should block. The evidence feed records which guard fired and why.
2. **Allowed tool call:** Use the *Call allowed host* button for `https://trusted.example.com/api` and confirm the guard logs a success.
3. **Blocked tool call:** Use the *Call blocked host* button with `https://evil.example.com/exfiltrate` to see Heimdall stop the agent and log the violation.
4. **Streaming chunk:** Paste suspicious text (`chunk: suspicious phishing link...`) and click *Evaluate chunk*—the evidence feed documents the T0 guard that scanned the chunk.

## Troubleshooting

- **Gateway unreachable?** Make sure Bifröst is running and listening on `:8000`. Check Redis connectivity if policies fail to load.
- **Policy errors?** Validate the YAML with `heimdall policy lint` and ensure the policy ID matches the selector.
- **Evidence empty?** Run any scenario; the evidence feed records up to eight entries and always shows the timestamp, guard ID, and policy hash.

## Next steps

- Dive into the [policy enforcement architecture](../docs/POLICY_ARCHITECTURE.md) to understand guard compilation, tiers, and evidence flow.
- Read the [Guard Authoring Guide](../docs/GUARD_AUTHORING.md) to write deterministic policies that target agents, tool args, and streaming tokens.
- Benchmark the gateway with `scripts/gateway_latency_test.py` to capture p50/p95/p99 latency numbers once Bifröst is running.
