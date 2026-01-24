# Guard Authoring Guide

Write runtime checks for LLM applications using simple, composable patterns.

---

## Quick Start

```python
from heimdall.author import G, guard, chain

# Simple check (decorator)
@guard("pii.check")
def no_pii(ctx):
    return not has_pii(ctx.input)

# Builder pattern
auth_required = G("auth").require(
    lambda ctx: ctx.authenticated,
    "Must be authenticated"
).build()

# Rate limiting
rate_limit = G("rate").limit(
    key=lambda ctx: ctx.user_id,
    calls=100,
    window=60,
    store="memory"
).build()

# Composition - run checks in sequence or parallel
pipeline = (
    chain(auth_required)
    .then(no_pii)
    .and_also(rate_limit)
).build()
```

---

## Mental Model

**Guards are checks** that examine context and either:
- Pass → return updated context
- Fail → return violation details

**Compose with operators:**
- `then()` = run in sequence (THEN)
- `and_also()` = all must pass (AND)
- `or_else()` = at least one must pass (OR)  
- `when()` = run conditionally (IF)

**Default behavior:** fail-fast (stop on first violation)

---

## Operator Semantics

### Precedence (tightest to loosest)

1. `then()` - sequential composition
2. `and_also()` - conjunction
3. `or_else()` - disjunction

All operators are **left-associative**.

### Evaluation Rules

**Sequential (`then`):**
```python
# g1 runs first; if it passes, g2 runs with updated context
g1.then(g2)
```
- Short-circuits on first failure
- Passes updated context forward
- Use for: pipelines, dependent checks

**Conjunction (`and_also`):**
```python
# Both must pass; runs in parallel if possible
g1.and_also(g2)
```
- Short-circuits by default
- Optional: `and_also(g2, collect=True)` to aggregate all violations
- Use for: independent requirements

**Disjunction (`or_else`):**
```python
# At least one must pass
g1.or_else(g2)
```
- Stops on first pass
- Use for: alternative auth methods, fallback checks

**Conditional (`when`):**
```python
# Only run if condition is true
g1.when(lambda ctx: ctx.external)
```
- Skips guard if condition is false
- Use for: environment-specific checks

---

## Core API: `G()` Builder

### Basic Pattern

```python
guard = G(rule_id).method(params).build()
```

### Methods

#### `require(condition, msg)` - Must be true

```python
auth = G("auth.required").require(
    lambda ctx: ctx.authenticated,
    "User must be authenticated"
).build()
```

#### `forbid(condition, msg)` - Must be false

```python
no_pii = G("pii.input").forbid(
    lambda ctx: has_pii(ctx.input),
    "Input contains PII"
).build()
```

#### `check(path, predicate, msg)` - Check value at path

```python
valid_email = G("email.valid").check(
    "user.email",
    lambda e: "@" in e and "." in e,
    "Invalid email format"
).build()
```

---

## Rate Limiting (Improved API)

**Required parameters:**

```python
rate_limit = G("rate.api").limit(
    key=lambda ctx: (ctx.tenant_id, ctx.user_id),  # Who/what to limit
    calls=100,                                       # Max calls
    window=60,                                       # Time window (seconds)
    store="redis",                                   # Storage backend
    mode="sliding_window",                           # Algorithm
    burst=20                                         # Optional: burst allowance
).build()
```

**Key function:** Return a tuple identifying the rate limit bucket
**Store options:** `"memory"`, `"redis"`, `"postgres"`
**Mode options:** `"fixed_window"`, `"sliding_window"`, `"token_bucket"`

---

## Dataflow Guards

Prevent sensitive data from flowing to unintended destinations.

### API

```python
from heimdall.author import flow

prevent_leak = (
    flow("db.users")               # Source
    .to("external.email")          # Destination
    .forbid_if(has_pii, "PII leak detected")
    .build("pii.leak")
)
```

### Multiple destinations

```python
multi_flow = (
    flow("db.users")
    .to("external.email").forbid_if(has_pii, "Email PII leak")
    .to("external.api").forbid_if(has_pii, "API PII leak")
    .to("analytics").forbid_if(has_pii, "Analytics PII leak")
    .build("pii.multi")
)
```

### How it works

1. **Source:** Path in context where data originates (e.g., `"db.users"`)
2. **Destination:** Path where data flows to (e.g., `"external.email"`)
3. **Predicate:** Check applied to source data before it reaches destination
4. **Runtime binding:** Flows are tracked via context metadata

---

## Context & Types

### Context Protocol

```python
from typing import Protocol, Any, Dict

class Ctx(Protocol):
    """Guard execution context"""
    
    # Required attributes
    input: str              # Input text
    output: str             # Output text (if available)
    authenticated: bool     # Auth state
    user_id: str           # User identifier
    tenant_id: str         # Tenant identifier
    
    # Optional attributes
    external: bool         # External request flag
    roles: list[str]       # User roles
    metadata: Dict[str, Any]  # Additional data
    
    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like access"""
        ...
```

### Violation Schema

```python
from typing import TypedDict, Dict, Any

class Violation(TypedDict):
    rule_id: str              # Guard rule identifier
    message: str              # Human-readable message
    severity: str             # "low", "medium", "high", "critical"
    code: str                 # Machine-readable code (optional)
    details: Dict[str, Any]   # Additional context
    path: str                 # Path in context (optional)
    source: str               # Data source (optional)
    sink: str                 # Data destination (optional)
    remediation: str          # How to fix (optional)
    timestamp: float          # When violation occurred
```

---

## Composition Examples

### Authentication Pipeline

```python
# Check auth, then role, then rate limit
auth_pipeline = (
    chain(G("auth").require(lambda ctx: ctx.authenticated).build())
    .then(G("role.admin").require(lambda ctx: "admin" in ctx.roles).build())
    .and_also(G("rate").limit(
        key=lambda ctx: ctx.user_id,
        calls=1000,
        window=3600,
        store="redis",
        mode="sliding_window"
    ).build())
).build()
```

### Content Filtering

```python
# All filters must pass (parallel)
content_filter = (
    chain(G("pii.input").forbid(lambda ctx: has_pii(ctx.input)).build())
    .and_also(G("pii.output").forbid(lambda ctx: has_pii(ctx.output)).build())
    .and_also(G("toxic").forbid(lambda ctx: is_toxic(ctx.output)).build())
).build()
```

### Conditional Check

```python
# Only check PII for external requests
conditional_pii = (
    chain(G("pii").forbid(lambda ctx: has_pii(ctx.data)).build())
    .when(lambda ctx: ctx.external)
).build()
```

### Flexible Auth

```python
# Admin OR has specific permission
flexible_auth = (
    chain(G("admin").require(lambda ctx: "admin" in ctx.roles).build())
    .or_else(G("permission").require(lambda ctx: ctx.has_permission("read")).build())
).build()
```

---

## Decorator Style

For simple predicates, use the decorator:

```python
@guard("pii.check", severity="critical")
def no_pii(ctx):
    """Check for PII in input"""
    return not has_pii(ctx.get("content", ""))

@guard("auth.required")
def require_auth(ctx):
    """Require authentication"""
    return ctx.get("authenticated", False)

@guard("email.valid")
def valid_email(ctx):
    """Validate email format"""
    email = ctx.get("email", "")
    return "@" in email and "." in email
```

---

## Observability

Guards automatically track:
- **Per-guard timings:** How long each check takes
- **Decision traces:** Which guards passed/failed
- **Correlation IDs:** Track checks across requests
- **Sampled data:** Optional input/output sampling

Access via context:

```python
result = await guard(ctx)
print(result.metadata["timings"])    # Per-guard durations
print(result.metadata["trace"])      # Decision path
print(result.metadata["correlation_id"])  # Request ID
```

---

## Testing Guards

### Unit Tests

```python
import pytest
from heimdall.author import G, guard

@pytest.mark.asyncio
async def test_pii_guard():
    pii_guard = G("pii").forbid(lambda ctx: has_pii(ctx.input)).build()
    
    # Should pass
    clean_ctx = {"input": "Hello world"}
    result = await pii_guard(clean_ctx)
    assert result.get("_tag") == "Right"
    
    # Should fail
    dirty_ctx = {"input": "Email: test@example.com"}
    result = await pii_guard(dirty_ctx)
    assert result.get("_tag") == "Left"
    assert "pii" in result.get("left", [])[0]["rule_id"]
```

### Property Tests

```python
from hypothesis import given
from hypothesis.strategies import text

@given(text())
@pytest.mark.asyncio
async def test_guard_associativity(s):
    """Guards should compose associatively"""
    g1 = G("g1").require(lambda ctx: len(ctx.input) > 0).build()
    g2 = G("g2").require(lambda ctx: ctx.input.isalnum()).build()
    g3 = G("g3").require(lambda ctx: len(ctx.input) < 100).build()
    
    # (g1 >> g2) >> g3  ==  g1 >> (g2 >> g3)
    left = chain(g1).then(g2).then(g3).build()
    right = chain(g1).then(chain(g2).then(g3).build()).build()
    
    ctx = {"input": s}
    r1 = await left(ctx)
    r2 = await right(ctx)
    
    assert r1.tag == r2.tag
```

---

## Complete Example

```python
from heimdall.author import G, guard, chain, flow

# 1. Define predicates
def has_pii(text: str) -> bool:
    """Detect PII patterns"""
    patterns = [r'\b\w+@\w+\.\w+\b', r'\b\d{3}-\d{2}-\d{4}\b']
    return any(re.search(p, text) for p in patterns)

def is_toxic(text: str) -> bool:
    """Detect toxic content"""
    # Use toxicity model
    ...

# 2. Create atomic guards
auth = G("auth").require(
    lambda ctx: ctx.authenticated,
    "User must be authenticated"
).build()

no_input_pii = G("pii.input").forbid(
    lambda ctx: has_pii(ctx.input),
    "Input contains PII"
).build()

no_output_pii = G("pii.output").forbid(
    lambda ctx: has_pii(ctx.output),
    "Output contains PII"
).build()

no_toxicity = G("toxic").forbid(
    lambda ctx: is_toxic(ctx.output),
    "Output is toxic"
).build()

rate_limit = G("rate").limit(
    key=lambda ctx: ctx.user_id,
    calls=100,
    window=60,
    store="redis",
    mode="sliding_window"
).build()

# Dataflow: prevent DB → external leaks
no_leak = (
    flow("db.users")
    .to("external.api")
    .forbid_if(has_pii, "PII leak to external API")
    .build("pii.leak")
)

# 3. Compose into pipeline
security_pipeline = (
    chain(auth)                        # Must be authenticated
    .then(no_input_pii)                # Check input (sequential)
    .then(no_output_pii)               # Check output (sequential)
    .and_also(no_toxicity)             # Check toxicity (parallel)
    .and_also(rate_limit)              # Check rate (parallel)
    .and_also(no_leak)                 # Check dataflow (parallel)
).build()

# 4. Use it
result = await security_pipeline(context)
if result.tag == "left":
    violations = result.value
    for v in violations:
        print(f"{v['severity']}: {v['message']}")
else:
    updated_ctx = result.value
    print("All checks passed")
```

---

## Comparison: Heimdall vs Others

### Simple Check

**Invariant:**
```python
raise "PII detected" if:
    (msg: Message)
    any(pii(msg.content))
```

**Heimdall:**
```python
@guard("pii.check")
def no_pii(ctx):
    return not has_pii(ctx.input)
```

**Comparison:** Similar conciseness, more Pythonic

---

### Dataflow Control

**Invariant:**
```python
raise "PII leak" if:
    (out: ToolOutput) -> (call: ToolCall)
    any(pii(out.content))
    call is tool:send_email
```

**Heimdall:**
```python
prevent_leak = (
    flow("db.users")
    .to("external.email")
    .forbid_if(has_pii, "PII leak")
    .build("pii.leak")
)
```

**Comparison:** More explicit source/destination, clearer intent

---

### Composition

**Invariant:**
```python
# Separate rules (no composition API)
raise "Not authenticated" if: ...
raise "PII detected" if: ...
raise "Rate limit" if: ...
```

**Heimdall:**
```python
pipeline = (
    chain(auth_guard)
    .then(pii_guard)
    .and_also(rate_guard)
).build()
```

**Comparison:** Heimdall provides composable building blocks

---

## Complete Algebra Reference

### Core Combinators (`heimdall.comb`)

```python
from heimdall.comb import seq, allOf, anyOf, kOf, unless, focus, lens

seq(*guards)                     # Sequential: run in order, stop on first failure
allOf(*guards, parallel=False)   # All must pass (parallel execution if parallel=True)
anyOf(*guards)                   # At least one must pass
kOf(k, *guards)                  # At least k of n must pass
unless(condition, guard)         # Run guard unless condition fails
focus(getter, setter, guard)     # Apply guard to focused part of context
lens(jsonpath)                   # Create JSONPath-based lens
```

### Error Handling Composition (`heimdall.kleisli`)

```python
from heimdall.kleisli import (
    identity, kleisli_compose, chain, bind, fmap, lift,
    when, unless_condition, try_guard, filter_violations, merge_violations
)

identity()                                  # Pass-through guard (no-op)
kleisli_compose(f, g)                       # Compose two guards (f then g)
chain(*guards)                              # Chain multiple guards with error propagation
bind(either, f)                             # Apply function to success result
fmap(f)                                     # Transform success value
lift(f)                                     # Convert pure function to guard
when(condition, guard)                      # Conditional execution
unless_condition(condition, guard)          # Negated conditional
try_guard(guard, fallback_guard)            # Try with fallback
filter_violations(predicate)                # Filter violations by predicate
merge_violations(either1, either2)          # Merge two Either results
```

### Budget & Performance (`heimdall.budget`)

```python
from heimdall.budget import (
    GuardBudget, with_timeout, with_retry, with_circuit_breaker,
    with_budget, with_metrics
)

# Timeout enforcement
with_timeout(guard, timeout_ms=100.0)

# Retry with exponential backoff
with_retry(guard, max_retries=3, backoff_ms=100.0)

# Circuit breaker pattern
with_circuit_breaker(guard, guard_id="my_guard", threshold=5, timeout_seconds=60)

# Complete budget enforcement
budget = GuardBudget(
    timeout_ms=100.0,
    max_retries=2,
    retry_backoff_ms=200.0,
    circuit_breaker_threshold=5,
    degradation_mode="skip"  # or "fail", "fallback"
)
with_budget(guard, "guard_id", budget)

# Metrics collection
with_metrics(guard, "guard_id")
```

### Rate Limiting (`heimdall.ratelimit`)

```python
from heimdall.ratelimit import (
    RateLimitConfig, create_rate_limit_guard,
    multi_tenant_key, tenant_isolation_key
)

# Create rate limit configuration
config = RateLimitConfig(
    max_requests=100,
    window_seconds=60,
    burst=20,  # Optional burst allowance
    algorithm="sliding_window",  # or "token_bucket", "fixed_window"
    redis_url="redis://localhost:6379"  # None for in-memory
)

# Create rate limit guard
rate_guard = create_rate_limit_guard(
    key_fn=lambda ctx: (ctx["tenant_id"], ctx["user_id"]),
    config=config,
    rule_id="api_rate_limit"
)

# Multi-tenant key helpers
key = multi_tenant_key("tenant1", "user123", "/api/chat")
tenant_key = tenant_isolation_key("tenant1")
```

### Redaction (`heimdall.redaction`)

```python
from heimdall.redaction import (
    mask_email, mask_phone, mask_ssn, mask_credit_card,
    compose_redactions, apply_pii_redaction,
    RedactionProfile, PROFILE_PII, PROFILE_FINANCIAL,
    redact_at_path, regex_redactor
)

# Individual redaction functions
text, strategy = mask_email("Contact: user@example.com")  # -> "u***@e***.com"
text, strategy = mask_phone("+1-234-567-8900")  # -> "+1-***-***-8900"

# Compose multiple redactions
redact_all = compose_redactions(mask_email, mask_phone, mask_ssn)
redacted_text, strategies = redact_all(sensitive_text)

# Use predefined profiles
redacted, strategy = PROFILE_PII.apply(text)

# Context-aware redaction
new_ctx = redact_at_path(ctx, "input.message", mask_email)

# Custom redactor
custom_redact = regex_redactor(
    pattern=r'\b[A-Z]{3}-\d{6}\b',
    replacement='[REF_REDACTED]',
    strategy_name='reference_mask'
)
```

### Observability (`heimdall.observability`)

```python
from heimdall.observability import (
    initialize_otel, with_tracing, with_structured_logging,
    get_otel_provider
)

# Initialize OpenTelemetry
initialize_otel(
    enabled=True,
    endpoint="http://localhost:4317",
    service_name="heimdall"
)

# Add tracing to guard
traced_guard = with_tracing(guard, guard_id="my_guard")

# Add structured logging
logged_guard = with_structured_logging(guard, guard_id="my_guard", log_level="INFO")
```

### Performance Profiling (`heimdall.profiler`)

```python
from heimdall.profiler import PerformanceProfiler

# Automatic profiling (transparent)
profiler = PerformanceProfiler()
profiled_guard = profiler.wrap_guard("my_guard", guard)

# Get profile after execution
profile = profiler.profile_guard("my_guard")
print(f"Average: {profile.avg_time_ms}ms, Category: {profile.performance_category}")
```

### Dataflow Taxonomy (`heimdall.taxonomy`)

```python
from heimdall.taxonomy import (
    Source, Sink, SourceType, SinkType,
    DataSensitivity, FlowPolicy,
    create_flow_rule, check_flow_allowed
)

# Define sources
user_input = Source(
    id="user_input",
    source_type=SourceType.USER_INPUT,
    sensitivity=DataSensitivity.PII
)

# Define sinks
external_api = Sink(
    id="external_api",
    sink_type=SinkType.EXTERNAL_API,
    trust_level="external"
)

# Create flow policy
policy = FlowPolicy.deny_by_default([
    FlowRule(source="user_input", sink="database", allowed=True),
    FlowRule(source="*", sink="external_api", allowed=False)
])

# Check if flow is allowed
allowed = check_flow_allowed(policy, "user_input", "external_api")
```

### Natural Transformations (`heimdall.natural`)

```python
from heimdall.natural import (
    promote_to_t1, promote_to_t2,
    to_permissive, to_blocking,
    with_timeout, with_retry
)

# Promote guard to different tier (metadata only)
t2_guard = promote_to_t2(my_guard)

# Convert to permissive mode (log violations, don't block)
permissive = to_permissive(strict_guard)

# Convert to blocking mode
blocking = to_blocking(permissive_guard)

# Add timeout
timeout_guard = with_timeout(slow_guard, timeout_ms=100.0)

# Add retry
retry_guard = with_retry(flaky_guard, max_retries=3, backoff_ms=200.0)
```

### Path-Based Access (`heimdall.optics`)

```python
from heimdall.optics import (
    Lens, Prism, Traversal, Iso,
    lens_guard, prism_guard, traversal_guard, iso_guard,
    path_lens, json_prism
)

# Lens - focus on specific path (get/set pair)
content_lens = Lens(
    get=lambda ctx: ctx.get("messages", [{}])[0].get("content", ""),
    set=lambda ctx, val: {**ctx, "messages": [{"content": val}]}
)
guarded = lens_guard(content_lens, some_guard)

# Prism - conditional access (may or may not exist)
json_prism = Prism(
    preview=lambda ctx: ctx.get("json") if ctx.get("format") == "json" else None,
    review=lambda ctx, val: {**ctx, "json": val}
)
guarded = prism_guard(json_prism, validate_json, fallback_guard)

# Traversal - access all elements in a collection
messages_traversal = Traversal(
    get_all=lambda ctx: [m["content"] for m in ctx.get("messages", [])],
    set_all=lambda ctx, vals: {**ctx, "messages": [{"content": v} for v in vals]}
)
guarded = traversal_guard(messages_traversal, content_guard)
```

### Stateful Guards (`heimdall.comonad`)

```python
from heimdall.comonad import (
    history_aware_guard, environment_aware_guard, windowed_guard
)

# History-aware (remembers past contexts)
history_guard = history_aware_guard(
    check=lambda state: len(state.get_history(10)) < 5,
    rule_id="excessive_requests",
    message="Too many recent requests",
    max_history=10
)

# Environment-aware (accesses global config)
env_guard = environment_aware_guard(
    env={"max_tokens": 1000, "allowed_models": ["gpt-4"]},
    check=lambda state, ctx: ctx.get("model") in state.environment["allowed_models"],
    rule_id="model_restriction",
    message="Model not allowed"
)

# Windowed aggregation
window_guard = windowed_guard(
    size=5,
    aggregate=lambda contexts: sum(c.get("tokens", 0) for c in contexts) < 5000,
    rule_id="token_window",
    message="Token budget exceeded in window"
)
```

### Temporal Tracking (`heimdall.temporal`)

```python
from heimdall.temporal import (
    TemporalChain, detect_retry_loop, detect_circular_dependency,
    enforce_rate_limit
)
from datetime import timedelta

chain = TemporalChain()

# Detect retry loops
retry_guard = detect_retry_loop(
    chain,
    max_retries=3,
    window=timedelta(seconds=30),
    call_type="api_call"
)

# Detect circular dependencies
circular_guard = detect_circular_dependency(chain)

# Temporal rate limiting
rate_guard = enforce_rate_limit(
    chain,
    event_type="api_call",
    max_count=100,
    window=timedelta(minutes=1)
)
```

### Dataflow Tracking (`heimdall.flow`)

```python
from heimdall.flow import (
    FlowContext, flow_guard, create_flow_context
)

# Track data flows
prevent_leak = flow_guard(
    from_pattern="db.users",
    to_pattern="external.api",
    predicate=lambda source, dest: has_pii(source),
    rule_id="pii.dataflow",
    message="PII detected flowing to external API"
)
```

---

## Advanced Topics

For composition laws, mathematical foundations, and property-based testing, see the [Advanced Composition Guide](archive/GUARD_AUTHORING_ADVANCED.md).

---

**Ready to build guards?** Start with `G()` for simple guards, or use the full algebra for sophisticated compositions.
