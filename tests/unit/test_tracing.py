"""
Tests for OpenTelemetry tracing
"""


import pytest

from heimdall.tracing import (
    DecisionTraceCollector,
    create_decision_trace,
    get_trace_collector,
    trace_guard,
)
from heimdall.types import Ctx, Either, Left_, Right_, Violation


@pytest.mark.asyncio
async def test_trace_guard_decorator():
    """Test trace_guard decorator wraps guard correctly"""

    @trace_guard("test.guard", tier="T0")
    async def test_guard_func(ctx: Ctx) -> Either:
        return Right_(ctx)

    result = await test_guard_func({"test": "data"})
    assert result["_tag"] == "Right"


@pytest.mark.asyncio
async def test_trace_guard_on_success():
    """Test trace_guard on successful guard execution"""

    @trace_guard("test.pass", tier="T0")
    async def passing_guard(ctx: Ctx) -> Either:
        return Right_(ctx)

    result = await passing_guard({"user_id": "123"})
    assert result["_tag"] == "Right"


@pytest.mark.asyncio
async def test_trace_guard_on_failure():
    """Test trace_guard on failed guard execution"""

    @trace_guard("test.fail", tier="T0")
    async def failing_guard(ctx: Ctx) -> Either:
        return Left_([Violation(
            rule_id="test.fail",
            severity="med",
            message="Test failure"
        )])

    result = await failing_guard({"user_id": "123"})
    assert result["_tag"] == "Left"


@pytest.mark.asyncio
async def test_trace_guard_on_error():
    """Test trace_guard on guard execution error"""

    @trace_guard("test.error", tier="T0")
    async def error_guard(ctx: Ctx) -> Either:
        raise ValueError("Test error")

    with pytest.raises(ValueError):
        await error_guard({"user_id": "123"})


def test_create_decision_trace_pass():
    """Test creating decision trace for passing guard"""
    ctx = {"user_id": "123", "tenant_id": "org1"}
    result = Right_(ctx)

    trace = create_decision_trace(
        guard_id="test.guard",
        decision="pass",
        ctx=ctx,
        result=result,
        duration_ms=5.2,
        tier="T0"
    )

    assert trace["guard_id"] == "test.guard"
    assert trace["decision"] == "pass"
    assert trace["duration_ms"] == 5.2
    assert trace["tier"] == "T0"
    assert trace["user_id"] == "123"
    assert trace["tenant_id"] == "org1"


def test_create_decision_trace_block():
    """Test creating decision trace for blocking guard"""
    ctx = {"user_id": "123"}
    result = Left_([Violation(
        rule_id="test.guard",
        severity="high",
        message="Blocked"
    )])

    trace = create_decision_trace(
        guard_id="test.guard",
        decision="block",
        ctx=ctx,
        result=result,
        duration_ms=10.5
    )

    assert trace["decision"] == "block"
    assert "violations" in trace
    assert trace["violation_count"] == 1


def test_decision_trace_collector():
    """Test DecisionTraceCollector"""
    collector = DecisionTraceCollector(max_traces=10)

    # Add some traces
    for i in range(5):
        collector.add_trace({
            "guard_id": f"test.guard.{i}",
            "decision": "pass",
            "duration_ms": 1.0
        })

    traces = collector.get_traces()
    assert len(traces) == 5


def test_decision_trace_collector_max_size():
    """Test that collector respects max size"""
    collector = DecisionTraceCollector(max_traces=3)

    # Add more than max
    for i in range(5):
        collector.add_trace({
            "guard_id": f"test.guard.{i}",
            "decision": "pass"
        })

    traces = collector.get_traces()
    assert len(traces) == 3  # Should only keep last 3


def test_decision_trace_collector_filtering():
    """Test filtering traces"""
    collector = DecisionTraceCollector()

    collector.add_trace({
        "guard_id": "test.guard.1",
        "decision": "pass",
        "duration_ms": 1.0
    })

    collector.add_trace({
        "guard_id": "test.guard.2",
        "decision": "block",
        "duration_ms": 2.0
    })

    # Filter by guard_id
    traces = collector.get_traces(guard_id="test.guard.1")
    assert len(traces) == 1
    assert traces[0]["guard_id"] == "test.guard.1"

    # Filter by decision
    traces = collector.get_traces(decision="block")
    assert len(traces) == 1
    assert traces[0]["decision"] == "block"


def test_decision_trace_collector_clear():
    """Test clearing traces"""
    collector = DecisionTraceCollector()

    collector.add_trace({"guard_id": "test", "decision": "pass"})
    assert len(collector.get_traces()) == 1

    collector.clear_traces()
    assert len(collector.get_traces()) == 0


def test_decision_trace_collector_statistics():
    """Test getting statistics"""
    collector = DecisionTraceCollector()

    # Add some traces
    collector.add_trace({
        "guard_id": "test.guard.1",
        "decision": "pass",
        "duration_ms": 5.0
    })

    collector.add_trace({
        "guard_id": "test.guard.2",
        "decision": "block",
        "duration_ms": 10.0
    })

    stats = collector.get_statistics()

    assert stats["total_traces"] == 2
    assert stats["pass_count"] == 1
    assert stats["block_count"] == 1
    assert stats["avg_duration_ms"] == 7.5


def test_decision_trace_collector_empty_statistics():
    """Test statistics on empty collector"""
    collector = DecisionTraceCollector()

    stats = collector.get_statistics()

    assert stats["total_traces"] == 0
    assert stats["pass_count"] == 0
    assert stats["block_count"] == 0
    assert stats["avg_duration_ms"] == 0


def test_get_trace_collector():
    """Test getting global trace collector"""
    collector = get_trace_collector()
    assert isinstance(collector, DecisionTraceCollector)

