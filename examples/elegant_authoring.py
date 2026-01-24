"""
Guard Authoring Examples - Clean, Composable Runtime Checks

Demonstrates the improved DSL with clear operator names and explicit configurations.
"""

import asyncio
import re

from heimdall.author import G, chain, flow, guard

# === Helper: PII Detector ===

def has_pii(text: str) -> bool:
    """Detect PII patterns in text"""
    if not isinstance(text, str):
        text = str(text)
    patterns = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # email
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{16}\b',  # Credit card
    ]
    return any(re.search(p, text) for p in patterns)


def is_toxic(text: str) -> bool:
    """Simple toxicity check"""
    toxic_words = ['hate', 'attack', 'harm']
    return any(word in text.lower() for word in toxic_words)


# ============================================================================
# Example 1: Simple Guards (Decorator vs Builder)
# ============================================================================

# Decorator style - concise for simple predicates
@guard("pii.check")
def no_pii_decorator(ctx):
    return not has_pii(ctx.get("input", ""))


# Builder style - more explicit
no_pii_builder = G("pii.input").forbid(
    lambda ctx: has_pii(ctx.get("input", "")),
    "Input contains PII"
).build()


# Authentication guard
require_auth = G("auth.required").require(
    lambda ctx: ctx.get("authenticated", False),
    "User must be authenticated"
).build()


# Role check
require_admin = G("role.admin").require(
    lambda ctx: "admin" in ctx.get("roles", []),
    "Admin role required"
).build()


# ============================================================================
# Example 2: Dataflow Control (NEW SYNTAX!)
# ============================================================================

# Prevent PII from flowing database → external services
prevent_leak = (
    flow("db.user_data")
    .to("external.email")
    .forbid_if(has_pii, "PII leak to external email")
    .build("pii.leak")
)

# Multiple destinations
prevent_all_leaks = (
    flow("db.users")
    .to("external.api").forbid_if(has_pii, "PII leak to API")
    .to("external.analytics").forbid_if(has_pii, "PII leak to analytics")
    .to("external.email").forbid_if(has_pii, "PII leak to email")
    .build("pii.multi_leak")
)


# ============================================================================
# Example 3: Rate Limiting (IMPROVED API!)
# ============================================================================

# Simple per-user rate limit
rate_limit_user = G("rate.user").limit(
    key=lambda ctx: (ctx.get("user_id", "unknown"),),
    calls=100,
    window=60,
    store="memory",
    mode="sliding_window"
).build()

# Per-tenant rate limit with burst
rate_limit_tenant = G("rate.tenant").limit(
    key=lambda ctx: (ctx.get("tenant_id", "unknown"),),
    calls=1000,
    window=3600,
    store="redis",
    mode="sliding_window",
    burst=50
).build()

# Combined tenant + user rate limit
rate_limit_combined = G("rate.combined").limit(
    key=lambda ctx: (ctx.get("tenant_id", "unknown"), ctx.get("user_id", "unknown")),
    calls=10,
    window=60,
    store="memory",
    mode="sliding_window"
).build()


# ============================================================================
# Example 4: Composition with Clear Names (NOT SYMBOLS!)
# ============================================================================

# Sequential: auth THEN input check THEN output check
auth_pipeline = (
    chain(require_auth)
    .then(no_pii_builder)
    .then(require_admin)
).build()

# Conjunction: ALL must pass (parallel checks)
content_filter = (
    chain(no_pii_builder)
    .and_also(G("toxic").forbid(lambda ctx: is_toxic(ctx.get("output", "")), "Toxic output").build())
).build()

# Disjunction: at LEAST ONE must pass
flexible_auth = (
    chain(require_admin)
    .or_else(
        G("permission.read").require(
            lambda ctx: ctx.get("has_read_permission", False),
            "Read permission required"
        ).build()
    )
).build()

# Complex composition: (auth THEN validate) AND rate_limit
full_pipeline = (
    chain(require_auth)
    .then(no_pii_builder)
    .and_also(rate_limit_user)
).build()


# ============================================================================
# Example 5: Conditional Guards
# ============================================================================

# Only check PII for external requests
conditional_pii = (
    chain(no_pii_builder)
    .when(lambda ctx: ctx.get("external", False))
).build()

# Only require auth for production
conditional_auth = (
    chain(require_auth)
    .when(lambda ctx: ctx.get("environment") == "production")
).build()


# ============================================================================
# Example 6: Multi-Check Guards (Builder Chaining)
# ============================================================================

# Multiple checks in one guard
security_suite = (
    G("security.full")
    .require(lambda ctx: bool(ctx.get("authenticated")), "Must be authenticated")
    .forbid(lambda ctx: has_pii(ctx.get("input", "")), "Input contains PII")
    .forbid(lambda ctx: has_pii(ctx.get("output", "")), "Output contains PII")
    .forbid(lambda ctx: is_toxic(ctx.get("output", "")), "Toxic output")
    .build()
)


# ============================================================================
# Example 7: Complete Security Stack
# ============================================================================

def build_security_stack():
    """Build a comprehensive security pipeline"""

    # Layer 1: Authentication
    auth = G("auth").require(
        lambda ctx: ctx.get("authenticated", False),
        "User must be authenticated"
    ).build()

    # Layer 2: Authorization
    authz = G("authz").require(
        lambda ctx: "user" in ctx.get("roles", []),
        "Valid role required"
    ).build()

    # Layer 3: Input validation
    input_guard = (
        G("input.validation")
        .forbid(lambda ctx: has_pii(ctx.get("input", "")), "Input PII")
        .forbid(lambda ctx: len(ctx.get("input", "")) > 10000, "Input too long")
        .build()
    )

    # Layer 4: Output validation
    output_guard = (
        G("output.validation")
        .forbid(lambda ctx: has_pii(ctx.get("output", "")), "Output PII")
        .forbid(lambda ctx: is_toxic(ctx.get("output", "")), "Toxic output")
        .build()
    )

    # Layer 5: Rate limiting
    rate_limit = G("rate").limit(
        key=lambda ctx: (ctx.get("user_id", "unknown"),),
        calls=100,
        window=60,
        store="memory",
        mode="sliding_window"
    ).build()

    # Layer 6: Dataflow protection
    dataflow_guard = (
        flow("db.users")
        .to("external.api")
        .forbid_if(has_pii, "PII leak to external API")
        .build("dataflow.pii")
    )

    # Compose into full stack:
    # 1. Auth & authz must pass (sequential)
    # 2. Then validate input
    # 3. Then validate output
    # 4. Rate limit and dataflow checks run in parallel
    return (
        chain(auth)
        .then(authz)
        .then(input_guard)
        .then(output_guard)
        .and_also(rate_limit)
        .and_also(dataflow_guard)
    ).build()


# ============================================================================
# Demo
# ============================================================================

async def demo():
    """Demonstrate the authoring patterns"""
    print("🎨 Guard Authoring Examples\n")
    print("=" * 60)

    # Test 1: Simple guard
    print("\n1️⃣  Simple Guard")
    clean = {"input": "Hello world"}
    dirty = {"input": "Email: test@example.com"}

    r1 = await no_pii_decorator(clean)
    r2 = await no_pii_decorator(dirty)

    print(f"   Clean input: {r1['_tag']}")
    print(f"   Dirty input: {r2['_tag']}")
    if r2['_tag'] == 'Left':
        print(f"   Violation: {r2['left'][0]['message']}")

    # Test 2: Authentication
    print("\n2️⃣  Authentication Guard")
    ctx_authed = {"authenticated": True}
    ctx_unauthed = {"authenticated": False}

    r3 = await require_auth(ctx_authed)
    r4 = await require_auth(ctx_unauthed)

    print(f"   Authenticated: {r3['_tag']}")
    print(f"   Not authenticated: {r4['_tag']}")
    if r4['_tag'] == 'Left':
        print(f"   Violation: {r4['left'][0]['message']}")

    # Test 3: Composition
    print("\n3️⃣  Composed Pipeline (then + and_also)")
    ctx_pass = {
        "authenticated": True,
        "input": "Clean text",
        "roles": ["admin"]
    }
    ctx_fail_pii = {
        "authenticated": True,
        "input": "Email: bad@example.com",
        "roles": ["admin"]
    }

    r5 = await full_pipeline(ctx_pass)
    r6 = await full_pipeline(ctx_fail_pii)

    print(f"   Pass all checks: {r5['_tag']}")
    print(f"   Fail PII check: {r6['_tag']}")
    if r6['_tag'] == 'Left':
        print(f"   Violation: {r6['left'][0]['message']}")

    # Test 4: Conditional guard
    print("\n4️⃣  Conditional Guard (.when)")
    internal = {"input": "Email: test@test.com", "external": False}
    external = {"input": "Email: test@test.com", "external": True}

    r7 = await conditional_pii(internal)
    r8 = await conditional_pii(external)

    print(f"   Internal (skip check): {r7['_tag']}")
    print(f"   External (check PII): {r8['_tag']}")
    if r8['_tag'] == 'Left':
        print(f"   Violation: {r8['left'][0]['message']}")

    # Test 5: Dataflow guard
    print("\n5️⃣  Dataflow Guard (flow().to().forbid_if())")
    ctx_flow = {
        "db": {"user_data": "Email: user@example.com"},
        "external": {"email": "destination"}
    }

    r9 = await prevent_leak(ctx_flow)
    print(f"   Dataflow check: {r9['_tag']}")
    if r9['_tag'] == 'Left':
        print(f"   Violation: {r9['left'][0]['message']}")

    # Test 6: Rate limiting (simulated)
    print("\n6️⃣  Rate Limiting")
    ctx_rate = {"user_id": "user123", "_temporal_chain": None}

    r10 = await rate_limit_user(ctx_rate)
    print(f"   Rate limit check: {r10['_tag']}")

    # Test 7: Complete stack
    print("\n7️⃣  Complete Security Stack")
    stack = build_security_stack()
    ctx_complete = {
        "authenticated": True,
        "roles": ["user"],
        "input": "Normal input",
        "output": "Normal output",
        "user_id": "user123"
    }

    r11 = await stack(ctx_complete)
    print(f"   Complete stack: {r11['_tag']}")

    print("\n" + "=" * 60)
    print("\n✨ Key Improvements:\n")
    print("  ✅ Clear method names (then, and_also, or_else)")
    print("  ✅ Explicit rate limiting (key, store, mode)")
    print("  ✅ Unambiguous dataflow syntax (flow().to().forbid_if())")
    print("  ✅ Well-defined precedence and evaluation rules")
    print("  ✅ Fail-fast by default, composable building blocks")


# ============================================================================
# Comparison with Old Syntax
# ============================================================================

def show_comparison():
    """Show before/after comparison"""
    print("\n" + "=" * 60)
    print("BEFORE/AFTER COMPARISON")
    print("=" * 60)

    print("\n📝 Composition Operators:")
    print("\nBEFORE (symbols):")
    print('  pipeline = (')
    print('      chain(g1) >> chain(g2) & chain(g3)')
    print('  ).build()')

    print("\nAFTER (methods):")
    print('  pipeline = (')
    print('      chain(g1).then(g2).and_also(g3)')
    print('  ).build()')

    print("\n" + "-" * 60)
    print("\n🔄 Dataflow Syntax:")
    print("\nBEFORE (ambiguous):")
    print('  path("db") >> "email" | has_pii')

    print("\nAFTER (explicit):")
    print('  flow("db").to("email").forbid_if(has_pii, "PII leak")')

    print("\n" + "-" * 60)
    print("\n⏱️  Rate Limiting:")
    print("\nBEFORE (underspecified):")
    print('  G("rate").limit(calls=100, window=60)')

    print("\nAFTER (explicit):")
    print('  G("rate").limit(')
    print('      key=lambda ctx: ctx.user_id,')
    print('      calls=100, window=60,')
    print('      store="redis", mode="sliding_window"')
    print('  )')

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
    show_comparison()
