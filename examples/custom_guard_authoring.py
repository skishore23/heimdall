"""
Custom Guard Authoring Example

Shows how to use the CT-based DSL to write elegant, composable guards
that are more powerful than Invariant-style approaches.
"""

import asyncio
import re

from heimdall import register_factory
from heimdall.author import G, chain, flow
from heimdall.types import Ctx

# === Helper Functions ===

def has_pii(text: str) -> bool:
    """Detect PII in text"""
    patterns = [
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # email
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
        r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # phone
    ]
    return any(re.search(p, text) for p in patterns)


def is_authenticated(ctx: Ctx) -> bool:
    """Check if request is authenticated"""
    return ctx.get("authenticated", False)


def is_external(ctx: Ctx) -> bool:
    """Check if destination is external"""
    return ctx.get("external", False)


# === Example 1: Simple Guards ===

# Basic check using builder
no_pii_guard = G("pii.detected").forbid(
    lambda ctx: has_pii(ctx.get("content", "")),
    "PII detected in content"
).build()

# Require authentication
auth_guard = G("auth.required").require(
    is_authenticated,
    "Authentication required"
).build()


# === Example 2: Dataflow Control ===

# Prevent PII from database to external API
prevent_db_leak = (
    flow("database_query")
    .to("external_api")
    .forbid_if(lambda src: has_pii(str(src)), "PII leaked from database to external API")
    .build("pii.leak.db_to_external")
)

# Prevent PII from user data to email
prevent_email_leak = (
    flow("user_data")
    .to("email_send")
    .forbid_if(has_pii, "PII leaked to email")
    .build("pii.leak.email")
)


# === Example 3: Rate Limiting ===

# Prevent excessive API calls
no_api_loops = G("loop.api_excessive").limit(
    key=lambda ctx: (ctx.get("api_call", ""),),
    calls=3,
    window=30,
    store="memory",
    msg="Too many API retries detected"
).build()

# Database query rate limit
no_db_loops = G("loop.db_excessive").limit(
    key=lambda ctx: (ctx.get("database_query", ""),),
    calls=5,
    window=60,
    store="memory"
).build()


# === Example 4: Conditional Guards ===

# Only check for external requests
external_check = (
    chain(no_pii_guard)
    .when(lambda ctx: ctx.get("external", False))
).build()


# === Example 5: Complex Composition ===

# Sequential: do this, then that
sequential_guard = (
    chain(auth_guard)
    .then(no_pii_guard)
).build()

# Conjunction: all must pass
strict_guard = (
    chain(auth_guard)
    .and_also(no_pii_guard)
    .and_also(no_api_loops)
).build()

# Conditional: only check PII for external requests
conditional_guard = (
    chain(no_pii_guard)
    .when(is_external)
).build()

# Full pipeline: auth → check PII → prevent loops
full_pipeline = (
    chain(auth_guard)
    .then(no_pii_guard)
    .and_also(no_api_loops)
).build()


# === Example 6: Register Custom Guards for Policy Use ===

@register_factory("custom.pii.dataflow", tier="T0", description="Prevent PII dataflow leaks")
def custom_pii_dataflow_guard(**params):
    """Custom guard using composition"""
    return (
        chain(prevent_db_leak)
        .and_also(prevent_email_leak)
    ).build()


@register_factory("custom.secure.pipeline", tier="T1", description="Full security pipeline")
def secure_pipeline_guard(**params):
    """Production-ready security pipeline"""
    auth = G("auth.required").require(is_authenticated, "Must authenticate").build()
    input_pii = G("pii.input").forbid(
        lambda ctx: has_pii(ctx.get("input", "")),
        "PII in input"
    ).build()
    output_pii = G("pii.output").forbid(
        lambda ctx: has_pii(ctx.get("output", "")),
        "PII in output"
    ).build()
    rate_limit = G("api.rate").limit(
        key=lambda ctx: (ctx.get("api_call", ""),),
        calls=3,
        window=30,
        store="memory"
    ).build()

    return (
        chain(auth)
        .then(input_pii)
        .then(output_pii)
        .and_also(rate_limit)
    ).build()


# === Demo ===

async def demo():
    """Demonstrate guard authoring"""
    print("🛡️  Custom Guard Authoring Demo\n")

    # Test 1: Simple guard
    print("1️⃣  Simple PII guard:")
    clean_ctx = {"content": "This is clean text"}
    pii_ctx = {"content": "Contact me at user@example.com"}

    result1 = await no_pii_guard(clean_ctx)
    result2 = await no_pii_guard(pii_ctx)

    print(f"   Clean text: {'✅ PASS' if result1.get('_tag') == 'Right' else '❌ FAIL'}")
    print(f"   PII text: {'✅ PASS' if result2.get('_tag') == 'Right' else '❌ FAIL (expected)'}")
    print()

    # Test 2: Composed guard
    print("2️⃣  Composed guard (auth + PII):")
    ctx_no_auth = {"content": "Clean", "authenticated": False}
    ctx_auth_clean = {"content": "Clean", "authenticated": True}
    ctx_auth_pii = {"content": "Email: test@test.com", "authenticated": True}

    result3 = await sequential_guard(ctx_no_auth)
    result4 = await sequential_guard(ctx_auth_clean)
    result5 = await sequential_guard(ctx_auth_pii)

    print(f"   No auth: {'✅ PASS' if result3.get('_tag') == 'Right' else '❌ FAIL (expected)'}")
    print(f"   Auth + clean: {'✅ PASS' if result4.get('_tag') == 'Right' else '❌ FAIL'}")
    print(f"   Auth + PII: {'✅ PASS' if result5.get('_tag') == 'Right' else '❌ FAIL (expected)'}")
    print()

    # Test 3: Conditional guard
    print("3️⃣  Conditional guard (PII only for external):")
    ctx_internal_pii = {"content": "Email: a@b.com", "external": False}
    ctx_external_pii = {"content": "Email: a@b.com", "external": True}

    result6 = await conditional_guard(ctx_internal_pii)
    result7 = await conditional_guard(ctx_external_pii)

    print(f"   Internal PII: {'✅ PASS' if result6.get('_tag') == 'Right' else '❌ FAIL'}")
    print(f"   External PII: {'✅ PASS' if result7.get('_tag') == 'Right' else '❌ FAIL (expected)'}")
    print()

    print("✨ DSL FTW! ✨")
    print("\nWhy use the DSL:")
    print("  ✅ Clear composition (.then, .and_also, .or_else)")
    print("  ✅ Pure functional (easy to test)")
    print("  ✅ Builder pattern (G, flow, chain)")
    print("  ✅ Explicit configuration (no magic)")
    print("  ✅ One clear way to write guards")


if __name__ == "__main__":
    asyncio.run(demo())

