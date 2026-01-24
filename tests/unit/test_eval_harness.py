"""
Tests for evaluation harness
"""


import pytest

from heimdall.eval_harness import (
    EvalHarness,
    EvalResult,
    Scoreboard,
    TestCase,
    TestSuite,
)
from heimdall.types import Ctx, Either, Left_, Right_, Violation


@pytest.fixture
def sample_test_case():
    """Create sample test case"""
    return TestCase(
        id="test_001",
        input={"messages": [{"role": "user", "content": "test"}]},
        expected="pass",
        category="basic",
        severity="low",
        description="Basic test"
    )


@pytest.fixture
def sample_test_suite(sample_test_case):
    """Create sample test suite"""
    return TestSuite(
        name="Test Suite",
        description="Sample test suite",
        cases=[sample_test_case]
    )


def test_test_case_creation(sample_test_case):
    """Test TestCase creation"""
    assert sample_test_case.id == "test_001"
    assert sample_test_case.expected == "pass"
    assert sample_test_case.category == "basic"


def test_test_suite_creation(sample_test_suite):
    """Test TestSuite creation"""
    assert sample_test_suite.name == "Test Suite"
    assert len(sample_test_suite.cases) == 1


def test_eval_result_passed():
    """Test EvalResult for passed test"""
    result = EvalResult(
        test_id="test_001",
        passed=True,
        expected="pass",
        actual="pass",
        duration_ms=5.2
    )

    assert result.passed is True
    assert result.duration_ms == 5.2


def test_eval_result_failed():
    """Test EvalResult for failed test"""
    result = EvalResult(
        test_id="test_002",
        passed=False,
        expected="block",
        actual="pass",
        duration_ms=3.1,
        violations=[]
    )

    assert result.passed is False
    assert result.expected == "block"
    assert result.actual == "pass"


def test_scoreboard_creation():
    """Test Scoreboard creation"""
    scoreboard = Scoreboard(
        policy_id="test_policy",
        suite_name="Test Suite",
        total_tests=10,
        passed=8,
        failed=2,
        true_positives=5,
        true_negatives=3,
        false_positives=1,
        false_negatives=1,
        avg_latency_ms=5.0,
        p50_latency_ms=4.5,
        p95_latency_ms=8.0,
        p99_latency_ms=10.0,
        coverage=100.0
    )

    assert scoreboard.total_tests == 10
    assert scoreboard.passed == 8
    assert scoreboard.failed == 2


def test_scoreboard_to_dict():
    """Test Scoreboard serialization"""
    scoreboard = Scoreboard(
        policy_id="test_policy",
        suite_name="Test Suite",
        total_tests=10,
        passed=8,
        failed=2,
        true_positives=5,
        true_negatives=3,
        false_positives=1,
        false_negatives=1,
        avg_latency_ms=5.0,
        p50_latency_ms=4.5,
        p95_latency_ms=8.0,
        p99_latency_ms=10.0,
        coverage=100.0
    )

    result = scoreboard.to_dict()

    assert result["policy_id"] == "test_policy"
    assert result["total_tests"] == 10
    assert result["accuracy"] == 0.8
    assert "precision" in result
    assert "recall" in result
    assert "latency" in result


def test_scoreboard_metrics():
    """Test Scoreboard metric calculations"""
    scoreboard = Scoreboard(
        policy_id="test",
        suite_name="test",
        total_tests=10,
        passed=9,
        failed=1,
        true_positives=5,
        true_negatives=4,
        false_positives=0,
        false_negatives=1,
        avg_latency_ms=5.0,
        p50_latency_ms=4.5,
        p95_latency_ms=8.0,
        p99_latency_ms=10.0,
        coverage=100.0
    )

    result = scoreboard.to_dict()

    # Precision = TP / (TP + FP) = 5 / (5 + 0) = 1.0
    assert result["precision"] == 1.0

    # Recall = TP / (TP + FN) = 5 / (5 + 1) ≈ 0.833
    assert result["recall"] == pytest.approx(5/6)


def test_scoreboard_print_summary(capsys):
    """Test Scoreboard print summary"""
    scoreboard = Scoreboard(
        policy_id="test_policy",
        suite_name="Test Suite",
        total_tests=10,
        passed=10,
        failed=0,
        true_positives=5,
        true_negatives=5,
        false_positives=0,
        false_negatives=0,
        avg_latency_ms=5.0,
        p50_latency_ms=4.5,
        p95_latency_ms=8.0,
        p99_latency_ms=10.0,
        coverage=100.0
    )

    scoreboard.print_summary()

    captured = capsys.readouterr()
    assert "Test Suite" in captured.out
    assert "test_policy" in captured.out
    assert "100.0%" in captured.out


@pytest.mark.asyncio
async def test_eval_harness_run_passing_test():
    """Test running a passing test case"""
    # Create simple guard that always passes
    async def always_pass(ctx: Ctx) -> Either:
        return Right_(ctx)

    # Create harness with mock policy
    harness = EvalHarness.__new__(EvalHarness)
    harness.guards = {"root": always_pass}
    harness.policy_id = "test_policy"

    test_case = TestCase(
        id="test_001",
        input={"test": "data"},
        expected="pass",
        category="basic"
    )

    result = await harness.run_test_case(test_case)

    assert result.passed is True
    assert result.actual == "pass"
    assert result.duration_ms > 0


@pytest.mark.asyncio
async def test_eval_harness_run_blocking_test():
    """Test running a blocking test case"""
    # Create guard that always blocks
    async def always_block(ctx: Ctx) -> Either:
        return Left_([Violation(
            rule_id="test.block",
            severity="high",
            message="Blocked"
        )])

    harness = EvalHarness.__new__(EvalHarness)
    harness.guards = {"root": always_block}
    harness.policy_id = "test_policy"

    test_case = TestCase(
        id="test_002",
        input={"test": "data"},
        expected="block",
        category="security"
    )

    result = await harness.run_test_case(test_case)

    assert result.passed is True  # Expected block, got block
    assert result.actual == "block"
    assert len(result.violations) == 1


@pytest.mark.asyncio
async def test_eval_harness_run_error_test():
    """Test running test case that errors"""
    # Create guard that raises error
    async def error_guard(ctx: Ctx) -> Either:
        raise ValueError("Test error")

    harness = EvalHarness.__new__(EvalHarness)
    harness.guards = {"root": error_guard}
    harness.policy_id = "test_policy"

    test_case = TestCase(
        id="test_003",
        input={"test": "data"},
        expected="pass",
        category="basic"
    )

    result = await harness.run_test_case(test_case)

    assert result.passed is False
    assert result.actual == "error"
    assert result.error is not None


@pytest.mark.asyncio
async def test_eval_harness_run_suite():
    """Test running full test suite"""
    # Create simple guard
    async def simple_guard(ctx: Ctx) -> Either:
        return Right_(ctx)

    harness = EvalHarness.__new__(EvalHarness)
    harness.guards = {"root": simple_guard}
    harness.policy_id = "test_policy"

    suite = TestSuite(
        name="Test Suite",
        description="Test",
        cases=[
            TestCase(
                id="test_001",
                input={"test": "data"},
                expected="pass",
                category="basic"
            ),
            TestCase(
                id="test_002",
                input={"test": "data"},
                expected="pass",
                category="basic"
            )
        ]
    )

    scoreboard = await harness.run_suite(suite)

    assert scoreboard.total_tests == 2
    assert scoreboard.passed == 2
    assert scoreboard.failed == 0

