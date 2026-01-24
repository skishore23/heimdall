#!/usr/bin/env python3
"""
Local test script to verify Guardrails functionality
"""

import asyncio
from pathlib import Path

import pytest

# Test imports
try:
    from heimdall import Left_, Right_, Violation, allOf, is_left, is_right, seq
    print("✓ Heimdall core imports successful")
except ImportError as e:
    print(f"✗ Heimdall core import failed: {e}")
    exit(1)

try:
    from guards.pii.guards import pii_detect, pii_redact
    print("✓ PII guards import successful")
except ImportError as e:
    print(f"✗ PII guards import failed: {e}")
    exit(1)

try:
    from guards.politics.guards import politics_block
    print("✓ Politics guards import successful")
except ImportError as e:
    print(f"✗ Politics guards import failed: {e}")
    exit(1)

try:
    from heimdall_sdk.core import PolicyError, load_policy
    print("✓ SDK core import successful")
except ImportError as e:
    print(f"✗ SDK core import failed: {e}")
    # Don't exit, just skip these tests
    load_policy = None
    PolicyError = None

# Import guard packs to register them
try:
    import guards
    print("✓ Guard packs registered successfully")
except ImportError as e:
    print(f"✗ Guard packs import failed: {e}")
    exit(1)


@pytest.mark.asyncio
async def test_basic_guards():
    """Test basic guard functionality"""
    print("\n🧪 Testing basic guard functionality...")

    # Test PII redaction
    pii_guard = pii_redact(types=["EMAIL"], mode="mask")
    ctx = {"output": "Contact me at john@example.com for details"}
    result = await pii_guard(ctx)

    if is_right(result):
        output = result["right"]["output"]
        if "[EMAIL]" in output and "john@example.com" not in output:
            print("✓ PII redaction working correctly")
        else:
            print(f"✗ PII redaction failed: {output}")
            return False
    else:
        print("✗ PII redaction returned violations unexpectedly")
        return False

    # Test politics blocking
    politics_guard = politics_block(
        patterns_strong=["vote for"],
        threshold=0.3
    )

    # Test violation
    ctx = {"output": "You should vote for the candidate"}
    result = await politics_guard(ctx)
    if is_left(result):
        print("✓ Politics blocking working correctly")
    else:
        print("✗ Politics blocking failed to detect violation")
        return False

    # Test safe content
    ctx = {"output": "This is a normal conversation"}
    result = await politics_guard(ctx)
    if is_right(result):
        print("✓ Politics blocking allows safe content")
    else:
        print("✗ Politics blocking incorrectly blocked safe content")
        return False

    return True


@pytest.mark.asyncio
async def test_policy_loading():
    """Test policy loading and compilation"""
    print("\n🧪 Testing policy loading...")

    try:
        policy_path = Path("policies/simple_test.yaml")
        if not policy_path.exists():
            print(f"✗ Policy file not found: {policy_path}")
            return False

        policy = load_policy(policy_path)
        print(f"✓ Policy loaded: {policy.id}")

        # Test policy execution
        ctx = {
            "phase": "input",
            "messages": [{"role": "user", "content": "Send email to john@example.com"}]
        }

        result = await policy.compiled_guard(ctx)
        if is_right(result):
            print("✓ Policy execution successful")
            return True
        else:
            violations = result["left"]
            print(f"✗ Policy execution failed with {len(violations)} violations")
            for v in violations:
                print(f"  - {v['rule_id']}: {v['message']}")
            return False

    except PolicyError as e:
        print(f"✗ Policy loading failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


@pytest.mark.asyncio
async def test_combinations():
    """Test guard combinations"""
    print("\n🧪 Testing guard combinations...")

    # Test sequential composition
    pii_guard = pii_redact(types=["EMAIL"], mode="mask")
    politics_guard = politics_block(patterns_strong=["vote for"], threshold=0.3)

    combined = seq(pii_guard, politics_guard)

    # Test with safe content
    ctx = {"output": "Contact me at john@example.com for details"}
    result = await combined(ctx)

    if is_right(result):
        output = result["right"]["output"]
        if "[EMAIL]" in output:
            print("✓ Sequential composition working")
        else:
            print("✗ Sequential composition failed")
            return False
    else:
        print("✗ Sequential composition returned violations unexpectedly")
        return False

    # Test parallel composition
    combined = allOf(pii_guard, politics_guard)

    # Test with violating content
    ctx = {"output": "You should vote for john@example.com"}
    result = await combined(ctx)

    if is_left(result):
        violations = result["left"]
        print(f"✓ Parallel composition working - found {len(violations)} violations")
        return True
    else:
        print("✗ Parallel composition failed to detect violations")
        return False


async def main():
    """Run all tests"""
    print("🚀 Starting Guardrails local tests...")

    tests = [
        test_basic_guards,
        test_policy_loading,
        test_combinations,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if await test():
                passed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")

    print(f"\n📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! The system is working correctly.")
        return True
    else:
        print("❌ Some tests failed. Please check the output above.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
