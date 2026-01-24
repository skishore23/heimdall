"""
CLI for evaluation harness

Usage:
    heimdall eval \
        --policy policies/enterprise_default_v1.yaml \
        --suite suites/pii.yaml suites/jailbreak.yaml \
        --out results/eval.json
"""

import argparse
import asyncio
from pathlib import Path

from heimdall.eval_harness import run_eval


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        prog="heimdall-eval",
        description="Heimdall Evaluation Harness - Evaluate guard policies against red-team suites"
    )

    parser.add_argument(
        "--policy",
        required=True,
        help="Path to policy YAML file"
    )

    parser.add_argument(
        "--suite",
        action="append",
        required=True,
        help="Path to test suite YAML (can be specified multiple times)"
    )

    parser.add_argument(
        "--out",
        help="Output JSON file for results"
    )

    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.05,
        help="Performance regression tolerance (default: 5%%)"
    )

    args = parser.parse_args()

    # Validate paths
    policy_path = Path(args.policy)
    if not policy_path.exists():
        print(f"❌ Policy file not found: {policy_path}")
        return 1

    suite_paths = []
    for suite_path_str in args.suite:
        suite_path = Path(suite_path_str)
        if not suite_path.exists():
            print(f"❌ Suite file not found: {suite_path}")
            return 1
        suite_paths.append(str(suite_path))

    # Run evaluation
    print(f"🚀 Evaluating policy: {policy_path}")
    print(f"📊 Test suites: {len(suite_paths)}")

    scoreboards = asyncio.run(
        run_eval(str(policy_path), suite_paths, args.out)
    )

    # Check for regressions (if baseline exists)
    if args.out:
        baseline_path = Path(args.out).parent / "baseline.json"
        if baseline_path.exists():
            print("\n🔍 Checking for performance regressions...")
            # Would implement baseline comparison here

    # Exit with error if any suite has < 100% accuracy
    total_passed = sum(s.passed for s in scoreboards)
    total_tests = sum(s.total_tests for s in scoreboards)

    if total_passed < total_tests:
        print(f"\n⚠️  Warning: {total_tests - total_passed} test(s) failed")
        return 1

    print("\n✅ All tests passed!")
    return 0


if __name__ == "__main__":
    exit(main())

