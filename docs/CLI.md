# Heimdall CLI

The Heimdall CLI provides a unified command-line interface for all Heimdall operations: policy management, local guard execution, gateway control, and diagnostics.

## Installation

### From Source (Recommended)

```bash
# Clone repository
git clone https://github.com/heimdall-ai/heimdall.git
cd heimdall

# Install CLI
uv venv
uv pip install -e ".[cli]"

# Install with ONNX support
uv pip install -e ".[cli,onnx]"

# Install everything (CLI + ONNX + dev tools)
uv pip install -e ".[cli,onnx,dev]"
```

### From PyPI (Future)

```bash
pip install "heimdall-guardrails[cli]"
pip install "heimdall-guardrails[cli,onnx]"
```

## Configuration

The CLI automatically discovers `heimdall.yaml` in the current directory or parent directories.

**Example `heimdall.yaml`:**

```yaml
# Directory paths
policies_dir: ./policies
build_dir: ./build
models_dir: ./models

# Bifröst gateway URL (optional)
bifrost_url: http://localhost:8080

# Default values
defaults:
  policy: enterprise_default_v1
  model: openai:gpt-4o

# Timeouts
timeout: 30.0
guard_timeout: 0.2

# Environment
env: development
tenant: default
```

## Command Reference

### Global Flags

- `--json` - Output as JSON (machine-readable)
- `--quiet` - Suppress non-essential output
- `--no-color` - Disable colored output
- `--timeout SECONDS` - Request timeout (default: 30)

### Exit Codes

- `0` - Success
- `1` - General error
- `2` - Policy error (lint/compile failure)
- `3` - Guard violation
- `4` - Environment error (missing config/API key)
- `5` - Network error (Bifröst unreachable)
- `6` - ONNX error (model load/inference failure)

## Commands

### `heimdall run`

Run guards locally (SDK mode) without a gateway.

```bash
# Run from stdin
echo "Hello world" | heimdall run -p policies/enterprise_default_v1.yaml -m openai:gpt-4o

# Run from file
heimdall run -p policies/enterprise_default_v1.yaml --input prompt.txt

# Run guards only (no LLM call)
heimdall run -p policies/enterprise_default_v1.yaml --input test.txt --no-llm

# With context variables
heimdall run -p policies/enterprise_default_v1.yaml --vars user_id=42 --vars tenant=acme

# JSON output for CI
heimdall run -p policy.yaml --input test.txt --json > result.json
```

### `heimdall policy`

Policy management commands.

#### `heimdall policy lint`

Validate policy YAML schema and composition.

```bash
heimdall policy lint policies/enterprise_default_v1.yaml
heimdall policy lint policies/enterprise_default_v1.yaml --json
```

#### `heimdall policy compile`

Compile policy to signed envelope.

```bash
# Compile without signing
heimdall policy compile -p policies/enterprise_default_v1.yaml -o build/policy.json

# Compile with Ed25519 signing
heimdall policy compile \
  -p policies/enterprise_default_v1.yaml \
  -o build/policy.json \
  --signing-key <base64-key> \
  --version "v1.2.3"
```

#### `heimdall policy verify`

Verify policy envelope signature and schema.

```bash
heimdall policy verify build/policy.json
heimdall policy verify build/policy.json --verify-key <base64-key>
```

#### `heimdall policy graph`

Export policy composition graph.

```bash
# JSON format
heimdall policy graph policies/enterprise_default_v1.yaml -f json

# Graphviz DOT format
heimdall policy graph policies/enterprise_default_v1.yaml -f dot -o policy.dot
```

#### `heimdall policy fmt`

Format policy YAML with consistent ordering.

```bash
# Format in place
heimdall policy fmt policies/enterprise_default_v1.yaml

# Check only (CI mode)
heimdall policy fmt policies/enterprise_default_v1.yaml --check
```

#### `heimdall policy keygen`

Generate Ed25519 signing keypair for Mímir.

```bash
heimdall policy keygen

# Output:
# ✓ Generated Ed25519 keypair
# 
# Signing Key (keep secret!):
#   <base64-encoded-signing-key>
# 
# Verify Key (distribute to gateways):
#   <base64-encoded-verify-key>
```

### `heimdall models`

ONNX model management.

#### `heimdall models list`

List ONNX models in models directory.

```bash
heimdall models list
heimdall models list --models-dir ./custom-models
heimdall models list --json
```

#### `heimdall models info`

Show detailed model information.

```bash
heimdall models info models/toxicity_detoxify.onnx
heimdall models info models/toxicity_detoxify.onnx --json
```

#### `heimdall models verify`

Verify model checksum and validity.

```bash
heimdall models verify models/toxicity_detoxify.onnx
heimdall models verify models/toxicity_detoxify.onnx --sha256 <expected-hash>
```

#### `heimdall models warmup`

Warm up model and measure performance.

```bash
# CPU warmup
heimdall models warmup models/toxicity_detoxify.onnx --provider CPU -n 10

# GPU warmup (if available)
heimdall models warmup models/toxicity_detoxify.onnx --provider CUDA -n 100

# With quantization
heimdall models warmup models/toxicity_detoxify.onnx --provider CPU --quant int8
```

### `heimdall bifrost`

Bifröst gateway control (requires running gateway).

#### `heimdall bifrost status`

Check gateway status.

```bash
heimdall bifrost status
heimdall bifrost status --url http://production:8080
heimdall bifrost status --json
```

#### `heimdall bifrost reload`

Hot-reload a policy envelope.

```bash
heimdall bifrost reload build/policy.json
heimdall bifrost reload build/policy.json --url http://production:8080
```

#### `heimdall bifrost trace`

View decision traces.

```bash
# Show recent traces
heimdall bifrost trace -n 50

# Stream live traces
heimdall bifrost trace --follow

# Filter by guard
heimdall bifrost trace --guard pii.email --follow

# Filter by decision
heimdall bifrost trace --decision block --follow

# JSON output
heimdall bifrost trace --follow --json
```

### `heimdall eval`

Evaluation and benchmarking.

#### `heimdall eval suite`

Run eval suites against a policy.

```bash
# Single suite
heimdall eval suite -p policies/enterprise_default_v1.yaml -s suites/pii.yaml

# Multiple suites
heimdall eval suite \
  -p policies/enterprise_default_v1.yaml \
  -s suites/pii.yaml \
  -s suites/jailbreak.yaml

# Save results
heimdall eval suite \
  -p policies/enterprise_default_v1.yaml \
  -s suites/pii.yaml \
  -o results/pii.json
```

#### `heimdall eval bench`

Micro-benchmark a guard.

```bash
heimdall eval bench --guard safety.toxicity.local_onnx -n 200
heimdall eval bench --guard pii.email -n 1000 --json
```

### `heimdall doctor`

Environment diagnostics.

```bash
heimdall doctor
heimdall doctor --json

# Checks:
# - Python version
# - Dependencies
# - Environment variables
# - ONNX providers
# - Directory structure
```

### `heimdall version`

Show version information.

```bash
heimdall version
```

### `heimdall completion`

Generate shell completion script.

```bash
# Bash
heimdall completion bash > ~/.local/share/bash-completion/completions/heimdall

# Zsh
heimdall completion zsh > ~/.zfunc/_heimdall

# Fish
heimdall completion fish > ~/.config/fish/completions/heimdall.fish
```

## Quickstart Examples

### Local SDK Mode (No Gateway)

```bash
# 1. Lint policy
heimdall policy lint policies/enterprise_default_v1.yaml

# 2. Run locally
echo "Write a friendly welcome email" | \
  heimdall run -p policies/enterprise_default_v1.yaml -m openai:gpt-4o
```

### With Bifröst Gateway

```bash
# 1. Compile policy (with signing)
heimdall policy compile \
  -p policies/enterprise_default_v1.yaml \
  -o build/policy.json \
  --signing-key $HEIMDALL_SIGNING_KEY

# 2. Start gateway (separate terminal)
heimdall-gateway

# 3. Check status
heimdall bifrost status

# 4. Hot-reload policy
heimdall bifrost reload build/policy.json

# 5. Watch live traces
heimdall bifrost trace --follow
```

### CI/CD Integration

```bash
#!/bin/bash
set -e

# Lint all policies
for policy in policies/*.yaml; do
  heimdall policy lint "$policy" --json || exit 2
done

# Compile production policy
heimdall policy compile \
  -p policies/production_v1.yaml \
  -o build/production.json \
  --signing-key "$SIGNING_KEY" \
  --version "$CI_COMMIT_SHA"

# Verify envelope
heimdall policy verify build/production.json --verify-key "$VERIFY_KEY"

# Run eval suites
heimdall eval suite \
  -p policies/production_v1.yaml \
  -s suites/pii.yaml \
  -s suites/jailbreak.yaml \
  -o results/eval.json

echo "✓ All checks passed"
```

## Environment Variables

The CLI respects these environment variables:

- `HEIMDALL_POLICIES_DIR` - Policies directory (default: `./policies`)
- `HEIMDALL_BUILD_DIR` - Build output directory (default: `./build`)
- `HEIMDALL_MODELS_DIR` - ONNX models directory (default: `./models`)
- `HEIMDALL_BIFROST_URL` - Bifröst URL (default: `http://localhost:8080`)
- `HEIMDALL_DEFAULT_POLICY` - Default policy ID
- `HEIMDALL_DEFAULT_MODEL` - Default model (default: `openai:gpt-4o`)
- `HEIMDALL_MIMIR_SIGNING_KEY` - Mímir signing key (base64)
- `HEIMDALL_MIMIR_VERIFY_KEY` - Mímir verify key (base64)
- `HEIMDALL_TIMEOUT` - Request timeout (default: 30.0)
- `HEIMDALL_GUARD_TIMEOUT` - Guard timeout (default: 0.2)
- `HEIMDALL_ENV` - Environment name (default: `development`)
- `HEIMDALL_TENANT` - Tenant ID (default: `default`)
- `HEIMDALL_JSON` - Enable JSON output (default: `false`)
- `HEIMDALL_QUIET` - Enable quiet mode (default: `false`)
- `HEIMDALL_NO_COLOR` - Disable colors (default: `false`)
- `OPENAI_API_KEY` - OpenAI API key (required for OpenAI models)
- `ANTHROPIC_API_KEY` - Anthropic API key (required for Claude models)

## Troubleshooting

### `ModuleNotFoundError: heimdall_cli`

Ensure you've installed the CLI extra:

```bash
pip install -e ".[cli]"
```

### `onnxruntime` conflicts

Uninstall both and reinstall the correct one:

```bash
pip uninstall onnxruntime onnxruntime-gpu
pip install onnxruntime  # CPU
# OR
pip install onnxruntime-gpu  # GPU
```

### Bifröst commands fail

Verify Bifröst is running and URL is correct:

```bash
# Check in heimdall.yaml or set explicitly
export HEIMDALL_BIFROST_URL=http://localhost:8080

# Test connection
curl http://localhost:8080/health
```

### Policy verify fails

Recompile the policy with the correct signing key:

```bash
heimdall policy compile \
  -p policies/my_policy.yaml \
  -o build/policy.json \
  --signing-key $HEIMDALL_SIGNING_KEY
```

## Next Steps

- [Guard Authoring Guide](GUARD_AUTHORING.md)
- [Policy Composition](GUARD_AUTHORING.md#composition)
- [Bifröst Gateway Setup](POLICY_ARCHITECTURE.md#bifröst-gateway)
- [Mímir Control Plane](archive/COMPONENTS.md#mímir-control-plane)
