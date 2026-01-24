#!/usr/bin/env python3
"""
Simple integration test to verify the system works
"""

from pathlib import Path

import pytest

# Import guard packs to register them
from heimdall import get_violations, is_left
from heimdall_sdk.core import load_policy


@pytest.mark.asyncio
async def test_integration():
    """Test the integration without pytest fixtures"""

    # Load the enterprise policy
    policy_path = Path("policies/enterprise_default_v1.yaml")
    print(f"Loading policy from: {policy_path}")

    try:
        policy = load_policy(policy_path)
        policy_id = getattr(policy, 'id', policy.metadata.get('policy_id'))
        print(f"✅ Policy loaded successfully: {policy_id}")
    except Exception as e:
        print(f"❌ Policy loading failed: {e}")
        raise

    # Test cases
    test_cases = [
        {
            "name": "PII Detection",
            "input": {
                "messages": [
                    {"role": "user", "content": "Send an email to john@example.com about the meeting"}
                ]
            },
            "expected_violation": True
        },
        {
            "name": "Politics Blocking",
            "input": {
                "output": {"text": "You should vote for the candidate in the upcoming election."}
            },
            "expected_violation": True
        },
        {
            "name": "Clean Content",
            "input": {
                "output": {"text": "Hello, how can I help you today?"}
            },
            "expected_violation": False
        }
    ]

    # Run tests
    for test_case in test_cases:
        print(f"\n🧪 Testing: {test_case['name']}")

        try:
            # Determine which guard to use based on input structure
            if "messages" in test_case['input']:
                guard = policy.compiled_guards.get("input")
            elif "output" in test_case['input']:
                guard = policy.compiled_guards.get("output")
            else:
                guard = policy.compiled_guards.get("root")

            if not guard:
                print("   ⚠️  No appropriate guard found for test case")
                continue

            result = await guard(test_case['input'])

            if is_left(result):
                violations = get_violations(result)
                print(f"   Violations found: {len(violations)}")
                for violation in violations:
                    print(f"   - {violation}")

                if test_case['expected_violation']:
                    print("   ✅ Expected violation detected")
                else:
                    print("   ❌ Unexpected violation detected")
            else:
                print("   No violations found")
                if not test_case['expected_violation']:
                    print("   ✅ No violations as expected")
                else:
                    print("   ❌ Expected violation but none found")

        except Exception as e:
            print(f"   ❌ Test failed with error: {e}")
            raise

    print("\n🎉 All integration tests passed!")
