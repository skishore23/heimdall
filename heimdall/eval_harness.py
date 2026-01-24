"""
Evaluation Harness for Guard Policies

Runs red-team test suites against policies and produces performance scorecards.
"""

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .compiler import compile_policy_from_file
from .types import Guard, get_violations, is_left


@dataclass
class TestCase:
    """Single test case"""
    id: str
    input: dict[str, Any]
    expected: str  # "pass" or "block"
    category: str
    severity: str = "med"
    description: str = ""


@dataclass
class TestSuite:
    """Collection of test cases"""
    name: str
    description: str
    cases: list[TestCase]


@dataclass
class EvalResult:
    """Result of running a test case"""
    test_id: str
    passed: bool
    expected: str
    actual: str
    duration_ms: float
    violations: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass
class Scoreboard:
    """Evaluation scoreboard"""
    policy_id: str
    suite_name: str
    total_tests: int
    passed: int
    failed: int
    true_positives: int  # Correctly blocked
    true_negatives: int  # Correctly allowed
    false_positives: int  # Incorrectly blocked
    false_negatives: int  # Incorrectly allowed
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    coverage: float  # Percentage of test categories covered

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "suite_name": self.suite_name,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "accuracy": self.passed / self.total_tests if self.total_tests > 0 else 0,
            "true_positives": self.true_positives,
            "true_negatives": self.true_negatives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": self.true_positives / (self.true_positives + self.false_positives)
                        if (self.true_positives + self.false_positives) > 0 else 0,
            "recall": self.true_positives / (self.true_positives + self.false_negatives)
                     if (self.true_positives + self.false_negatives) > 0 else 0,
            "latency": {
                "avg_ms": self.avg_latency_ms,
                "p50_ms": self.p50_latency_ms,
                "p95_ms": self.p95_latency_ms,
                "p99_ms": self.p99_latency_ms,
            },
            "coverage": self.coverage,
        }

    def print_summary(self) -> None:
        """Print human-readable summary"""
        print(f"\n{'='*60}")
        print(f"Evaluation Results: {self.suite_name}")
        print(f"Policy: {self.policy_id}")
        print(f"{'='*60}")
        print(f"\nAccuracy: {self.passed}/{self.total_tests} ({100*self.passed/self.total_tests:.1f}%)")
        print("\nConfusion Matrix:")
        print(f"  True Positives:  {self.true_positives:3d} (correctly blocked)")
        print(f"  True Negatives:  {self.true_negatives:3d} (correctly allowed)")
        print(f"  False Positives: {self.false_positives:3d} (incorrectly blocked)")
        print(f"  False Negatives: {self.false_negatives:3d} (incorrectly allowed)")

        precision = self.true_positives / (self.true_positives + self.false_positives) \
                   if (self.true_positives + self.false_positives) > 0 else 0
        recall = self.true_positives / (self.true_positives + self.false_negatives) \
                if (self.true_positives + self.false_negatives) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        print("\nMetrics:")
        print(f"  Precision: {precision:.3f}")
        print(f"  Recall:    {recall:.3f}")
        print(f"  F1 Score:  {f1:.3f}")

        print("\nLatency:")
        print(f"  Average: {self.avg_latency_ms:.2f}ms")
        print(f"  P50:     {self.p50_latency_ms:.2f}ms")
        print(f"  P95:     {self.p95_latency_ms:.2f}ms")
        print(f"  P99:     {self.p99_latency_ms:.2f}ms")

        print(f"\nCoverage: {self.coverage:.1f}%")
        print(f"{'='*60}\n")


class EvalHarness:
    """Evaluation harness for guard policies"""

    def __init__(self, policy_path: str):
        """
        Initialize eval harness

        Args:
            policy_path: Path to policy YAML file
        """
        self.policy_path = policy_path
        self.guards: dict[str, Guard] | None = None
        self.metadata: dict[str, Any] | None = None

    async def initialize(self) -> None:
        """Load and compile policy"""
        self.guards, self.metadata = compile_policy_from_file(self.policy_path)
        self.policy_id = self.metadata.get('policy_id', Path(self.policy_path).stem)

    async def run_test_case(self, test: TestCase) -> EvalResult:
        """Run a single test case"""
        start = time.perf_counter()

        try:
            # Run root guard
            root_guard = self.guards.get("root")
            if not root_guard:
                raise ValueError("Policy has no 'root' composition")

            result = await root_guard(test.input)

            duration_ms = (time.perf_counter() - start) * 1000

            # Determine actual outcome
            if is_left(result):
                actual = "block"
                violations = get_violations(result)
            else:
                actual = "pass"
                violations = []

            # Check if matches expected
            passed = (actual == test.expected)

            return EvalResult(
                test_id=test.id,
                passed=passed,
                expected=test.expected,
                actual=actual,
                duration_ms=duration_ms,
                violations=violations
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return EvalResult(
                test_id=test.id,
                passed=False,
                expected=test.expected,
                actual="error",
                duration_ms=duration_ms,
                error=str(e)
            )

    async def run_suite(self, suite: TestSuite) -> Scoreboard:
        """Run a full test suite"""
        # Run all test cases
        results = []
        for test in suite.cases:
            result = await self.run_test_case(test)
            results.append(result)

        # Calculate metrics
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed

        # Confusion matrix
        tp = sum(1 for r in results if r.expected == "block" and r.actual == "block")
        tn = sum(1 for r in results if r.expected == "pass" and r.actual == "pass")
        fp = sum(1 for r in results if r.expected == "pass" and r.actual == "block")
        fn = sum(1 for r in results if r.expected == "block" and r.actual == "pass")

        # Latency
        latencies = [r.duration_ms for r in results if r.error is None]
        avg_latency = statistics.mean(latencies) if latencies else 0
        p50_latency = statistics.median(latencies) if latencies else 0
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 1 else 0
        p99_latency = statistics.quantiles(latencies, n=100)[98] if len(latencies) > 1 else 0

        # Coverage
        categories = {test.category for test in suite.cases}
        coverage = 100.0 if categories else 0

        return Scoreboard(
            policy_id=self.policy_id,
            suite_name=suite.name,
            total_tests=total,
            passed=passed,
            failed=failed,
            true_positives=tp,
            true_negatives=tn,
            false_positives=fp,
            false_negatives=fn,
            avg_latency_ms=avg_latency,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            coverage=coverage
        )


def load_suite_from_yaml(suite_path: str) -> TestSuite:
    """Load test suite from YAML file"""
    import yaml

    with open(suite_path) as f:
        data = yaml.safe_load(f)

    cases = []
    for case_data in data.get('tests', []):
        cases.append(TestCase(
            id=case_data['id'],
            input=case_data['input'],
            expected=case_data['expected'],
            category=case_data.get('category', 'uncategorized'),
            severity=case_data.get('severity', 'med'),
            description=case_data.get('description', '')
        ))

    return TestSuite(
        name=data.get('name', 'Unnamed Suite'),
        description=data.get('description', ''),
        cases=cases
    )


async def run_eval(
    policy_path: str,
    suite_paths: list[str],
    output_path: str | None = None
) -> list[Scoreboard]:
    """
    Run evaluation harness

    Args:
        policy_path: Path to policy YAML
        suite_paths: List of test suite YAML paths
        output_path: Optional output JSON file for results

    Returns:
        List of scoreboards
    """
    # Initialize harness
    harness = EvalHarness(policy_path)
    await harness.initialize()

    # Run all suites
    scoreboards = []

    for suite_path in suite_paths:
        print(f"\n🧪 Running suite: {suite_path}")
        suite = load_suite_from_yaml(suite_path)
        scoreboard = await harness.run_suite(suite)
        scoreboard.print_summary()
        scoreboards.append(scoreboard)

    # Save results
    if output_path:
        results = {
            'policy': policy_path,
            'timestamp': time.time(),
            'suites': [s.to_dict() for s in scoreboards]
        }

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\n✅ Results saved to: {output_path}")

    return scoreboards

