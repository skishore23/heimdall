# Advanced Guard Authoring

This companion dives into **real-world scenarios** that demand the more advanced constructs in Heimdall: composable sequencing, natural transformations, Kleisli chaining, and property-based validation. If `docs/GUARD_AUTHORING.md` feels dense, start here for concrete policies and explanation before you explore the algebra.

## 1. Composition in practice

**Scenario:** You run a regulated customer support bot that must (a) redact PII, (b) enforce a policy that forbids financial promises, and (c) allow schema-validated commands only when a rate limiter allows it.

```python
from heimdall import seq, allOf, lens, G
from heimdall.comb import focus
from heimdall.optics import path_lens

pii_guard = focus(path_lens('messages[*].content'), G('pii.redact').require(...))
assurance_guard = G('business.financial_compliance').require(...)
schema_guard = G('schema.validate_command').require(...)
rate_guard = G('temporal.rate_limit').require(...)

policy = seq(
    pii_guard,
    allOf(assurance_guard, schema_guard),
    rate_guard
)
```

- `seq` enforces the fail-fast ordering: PII redaction runs first, ensuring later guards only see sanitized data. `allOf` keeps the financial and schema guards parallel, but both must pass before the rate limiter executes.
- Because these operators obey composition laws (identity, associativity), you can distribute them across reusable policy templates.

## 2. Natural transformations with policy versions

**Scenario:** You still want the same guard (`business.block_hosts`) across environments, but production should block with enforcement while staging should log violations without blocking.

```python
from heimdall.natural import to_permissive, to_blocking
from heimdall import G

block_hosts = G('business.block_hosts').require(...)
permissive_guard = to_permissive(block_hosts)
blocking_guard = to_blocking(permissive_guard)
```

- `to_permissive` wraps the guard so it returns violations (Left) but continues downstream, perfect for shadow mode. `to_blocking` can wrap the same guard when the environment flips to strict enforcement.
- You can also `promote_to_t1` or `promote_to_t2` for tier hints without altering semantics, so dashboards know the budget remains the same.

## 3. Kleisli chains for tooling workflows

**Scenario:** Tool calls often return context (tool name, args, evidence). Use Kleisli composition so each guard sees the enriched context only when the previous step succeeded.

```python
from heimdall.kleisli import chain
from heimdall import G, Left_, Right_

def enrich(ctx):
    return Right_({**ctx, 'tool_metadata': {...}})

tool_guard = G('tools.args.validator').require(...)
combined = chain(enrich, tool_guard)
```

- `chain` feeds the `Right` context from `enrich` into `tool_guard`. If a violation happens, the flow short-circuits, ensuring downstream guards never run on dirty data.
- This style mirrors real-world agents that add telemetry before running policy enforcement.

## 4. Property-based testing the control plane

Heimdall ships Hypothesis-driven suites under `tests/property/`. A sample invariant might be:

```python
@given(build_policy())
def test_guards_preserve_context(policy):
    ctx = {'messages': [...]}
    result = policy['root'](ctx)
    assert 'messages' in ctx
```

- Hypothesis introduces thousands of random policies/messages so you can prove statements (e.g., “input guards never mutate unrelated fields” or “tool validators always include `evidence` metadata”).
- Run `pytest tests/property` as part of your CI to guard the algebra as you evolve guard packs.

## 5. Real-world policy pattern

**Policy:** Multi-tenant agent guard

- Input guard: lens into `tool_args.arguments.url`, check against allow list plus signature metadata from Mímir. Uses `focus` + `lens_guard` + `G('business.block_hosts')`.
- Sequenced guard: run `pii.redact` before any tool validation so no secrets escape.
- Streaming guard: attach `kOf(2, streamingGuardA, streamingGuardB)` to require both heuristic and ML detectors for T0/T2 coverage.

This pattern ensures you can reuse a single YAML policy for chat, tool, and streaming surfaces.

---

Whenever the algebra feels abstract, return here for the practical map: the code blocks above are how actual enterprise policies look in Heimdall. Keep iterating on them in conjunction with the control plane so every guard is traceable, signed, and auditable via Mímir.
