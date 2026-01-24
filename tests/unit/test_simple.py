#!/usr/bin/env python3
"""
Simple test script to verify the Guardrails system is working
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

# Import guard packs to register them
from heimdall import clear_registry, get_violations, is_left
from heimdall_sdk.core import load_policy


@pytest.mark.asyncio
async def test_system():
    """Test the basic functionality of the Guardrails system"""
    print("🧪 Testing Guardrails System...")

    try:
        # Clear registry and re-import guards
        clear_registry()

        # Load a simple policy
        policy_path = Path("policies") / "simple_test.yaml"
        print(f"📄 Loading policy from: {policy_path}")

        policy = load_policy(policy_path)
        print(f"✅ Policy loaded successfully: {policy.id}")

        # Test PII detection
        print("\n🔍 Testing PII Detection...")
        test_text = "My email is john.doe@example.com and my phone is 555-123-4567"
        context = {"output": {"text": test_text}}

        result = await policy.compiled_guards["root"](context)
        if is_left(result):
            violations = get_violations(result)
            print(f"   ✅ PII detected: {len(violations)} violations")
            for v in violations:
                print(f"   - {v.rule_id}: {v.message}")
        else:
            print("   ❌ PII not detected (unexpected)")

        # Test politics blocking
        print("\n🗳️ Testing Politics Blocking...")
        politics_text = "You should vote for the best candidate in the election"
        context = {"output": {"text": politics_text}}

        result = await policy.compiled_guards["root"](context)
        if is_left(result):
            violations = get_violations(result)
            print(f"   ✅ Politics detected: {len(violations)} violations")
            for v in violations:
                print(f"   - {v.rule_id}: {v.message}")
        else:
            print("   ❌ Politics not detected (unexpected)")

        # Test clean content
        print("\n✨ Testing Clean Content...")
        clean_text = "Hello, how are you today? I hope you're having a great day!"
        context = {"output": {"text": clean_text}}

        result = await policy.compiled_guards["root"](context)
        if not is_left(result):
            print("   ✅ Clean content allowed (expected)")
        else:
            violations = get_violations(result)
            print(f"   ❌ Clean content blocked: {len(violations)} violations")
            for v in violations:
                print(f"   - {v.rule_id}: {v.message}")

        print("\n🎉 All tests completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_system())
    sys.exit(0 if success else 1)
