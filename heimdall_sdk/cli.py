"""
CLI for the Heimdall SDK
"""

import argparse
import asyncio
import json
import sys

from .core import PolicyError, load_policy


def validate_policy(args):
    """Validate a policy file"""
    try:
        policy = load_policy(args.policy)
        print(f"✓ Policy '{policy.id}' loaded successfully")
        print(f"  Hash: {policy.hash}")
        print(f"  Guards: {len(policy.metadata.get('guards', []))}")
        return 0
    except PolicyError as e:
        print(f"✗ Policy validation failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"✗ Unexpected error: {e}", file=sys.stderr)
        return 1


def list_guards(args):
    """List available guards"""
    from heimdall.registry import list_guards

    guards = list_guards()
    if not guards:
        print("No guards registered")
        return 0

    print(f"Available guards ({len(guards)}):")
    for guard_id in sorted(guards):
        print(f"  - {guard_id}")

    return 0


def test_policy(args):
    """Test a policy against sample data"""
    try:
        policy = load_policy(args.policy)

        # Load test data
        test_data = {}
        if args.input:
            with open(args.input) as f:
                test_data["input"] = json.load(f)

        if args.output:
            with open(args.output) as f:
                test_data["output"] = json.load(f)

        if not test_data:
            print("No test data provided (use --input or --output)", file=sys.stderr)
            return 1

        # Run policy test
        async def run_test():
            from heimdall import get_violations, is_left

            context = {
                "phase": "test",
                **test_data
            }

            result = await policy.compiled_guard(context)
            if is_left(result):
                violations = get_violations(result)
                print(f"✗ Policy test failed with {len(violations)} violations:")
                for i, violation in enumerate(violations, 1):
                    print(f"  {i}. {violation['rule_id']}: {violation['message']}")
                return 1
            else:
                print("✓ Policy test passed")
                return 0

        return asyncio.run(run_test())

    except PolicyError as e:
        print(f"✗ Policy error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"✗ Test error: {e}", file=sys.stderr)
        return 1


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Heimdall SDK Command Line Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a policy file
  cga-sdk validate policies/enterprise_default_v1.yaml

  # List available guards
  cga-sdk list-guards

  # Test a policy
  cga-sdk test policies/enterprise_default_v1.yaml --input test_input.json --output test_output.json
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate a policy file')
    validate_parser.add_argument('policy', help='Path to policy YAML file')

    # List guards command
    subparsers.add_parser('list-guards', help='List available guards')

    # Test command
    test_parser = subparsers.add_parser('test', help='Test a policy against sample data')
    test_parser.add_argument('policy', help='Path to policy YAML file')
    test_parser.add_argument('--input', help='Path to input test data JSON file')
    test_parser.add_argument('--output', help='Path to output test data JSON file')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Import guard packs to register them

    # Route to appropriate command
    if args.command == 'validate':
        return validate_policy(args)
    elif args.command == 'list-guards':
        return list_guards(args)
    elif args.command == 'test':
        return test_policy(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
