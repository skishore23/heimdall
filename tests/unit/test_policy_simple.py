#!/usr/bin/env python3
"""
Simple policy test to debug import issues
"""

# Import guard packs to register them
import asyncio

import pytest

from heimdall import get_violations, is_left
from heimdall_sdk.core import load_policy


@pytest.mark.asyncio
async def test_enterprise_policy():
    """Test enterprise policy functionality"""
    print("🧪 Testing enterprise policy...")

    try:
        policy = load_policy("policies/enterprise_default_v1.yaml")
        print(f"✅ Policy loaded: {policy.id}")
        print(f"   Compiled guards: {list(policy.compiled_guards.keys())}")

        # Test toxicity blocking
        output_guard = policy.compiled_guards.get("output")
        if output_guard:
            context = {
                "phase": "output",
                "output": "You are such a fucking idiot"
            }

            result = await output_guard(context)
            if is_left(result):
                violations = get_violations(result)
                print(f"✅ Toxicity blocked: {len(violations)} violations")
                for v in violations:
                    print(f"   - {v['rule_id']}: {v['message']}")
            else:
                print("❌ Toxicity NOT blocked - this is the issue!")

        # Test PII redaction
        input_guard = policy.compiled_guards.get("input")
        if input_guard:
            context = {
                "phase": "input",
                "messages": [{"role": "user", "content": "My email is john@example.com"}],
                "model": "gpt-3.5-turbo"
            }

            result = await input_guard(context)
            if not is_left(result):
                from heimdall import get_context
                updated_context = get_context(result)
                message_content = updated_context["messages"][0]["content"]
                if "[EMAIL]" in message_content:
                    print("✅ PII redaction working")
                else:
                    print(f"❌ PII NOT redacted: {message_content}")
            else:
                print("❌ PII redaction failed with violations")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

@pytest.mark.asyncio
async def test_toxicity_guard_direct():
    """Test toxicity guard directly"""
    print("\n🧪 Testing toxicity guard directly...")

    from guards.toxicity.guards import toxicity_block

    guard = toxicity_block(categories=["profanity", "harassment"], threshold=0.3)
    context = {"output": "You are such a fucking idiot"}

    result = await guard(context)
    if is_left(result):
        violations = get_violations(result)
        print(f"✅ Direct toxicity test passed: {len(violations)} violations")
        for v in violations:
            print(f"   - {v['rule_id']}: {v['message']} (score: {v.get('score', 'N/A')})")
    else:
        print("❌ Direct toxicity test failed - no violations detected")

async def main():
    """Run all tests"""
    print("🚀 Starting policy tests...\n")

    await test_toxicity_guard_direct()
    await test_enterprise_policy()

    print("\n✅ Tests completed!")

if __name__ == "__main__":
    asyncio.run(main())
