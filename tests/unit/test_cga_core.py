"""
Unit tests for Heimdall core functionality
"""

import pytest

from heimdall import (
    Left_,
    Right_,
    Violation,
    allOf,
    focus,
    get_context,
    get_violations,
    is_left,
    is_right,
    lens,
    seq,
)


class TestViolation:
    """Test Violation class"""

    def test_violation_creation(self):
        """Test violation creation"""
        violation = Violation(
            rule_id="test.rule",
            severity="high",
            message="Test violation"
        )

        assert violation.rule_id == "test.rule"
        assert violation.severity == "high"
        assert violation.message == "Test violation"
        assert violation.span is None
        assert violation.score is None
        assert violation.evidence is None

    def test_violation_to_dict(self):
        """Test violation serialization"""
        violation = Violation(
            rule_id="test.rule",
            severity="high",
            message="Test violation",
            score=0.8
        )

        data = violation.to_dict()
        assert data["rule_id"] == "test.rule"
        assert data["severity"] == "high"
        assert data["message"] == "Test violation"
        assert data["score"] == 0.8


class TestEither:
    """Test Either type functionality"""

    def test_left_creation(self):
        """Test Left creation"""
        violations = [
            Violation("rule1", "high", "Error 1"),
            Violation("rule2", "med", "Error 2")
        ]

        left = Left_(violations)
        assert left["_tag"] == "Left"
        assert len(left["left"]) == 2

    def test_right_creation(self):
        """Test Right creation"""
        ctx = {"key": "value", "number": 42}
        right = Right_(ctx)
        assert right["_tag"] == "Right"
        assert right["right"] == ctx

    def test_is_left(self):
        """Test is_left function"""
        violations = [Violation("rule1", "high", "Error")]
        left = Left_(violations)
        right = Right_({"key": "value"})

        assert is_left(left) is True
        assert is_left(right) is False

    def test_is_right(self):
        """Test is_right function"""
        violations = [Violation("rule1", "high", "Error")]
        left = Left_(violations)
        right = Right_({"key": "value"})

        assert is_right(right) is True
        assert is_right(left) is False

    def test_get_violations(self):
        """Test get_violations function"""
        violations = [Violation("rule1", "high", "Error")]
        left = Left_(violations)

        extracted = get_violations(left)
        assert len(extracted) == 1
        assert extracted[0]["rule_id"] == "rule1"

    def test_get_context(self):
        """Test get_context function"""
        ctx = {"key": "value", "number": 42}
        right = Right_(ctx)

        extracted = get_context(right)
        assert extracted == ctx


class TestCombinators:
    """Test combinator functions"""

    @pytest.mark.asyncio
    async def test_seq_success(self):
        """Test sequential composition with success"""
        async def guard1(ctx):
            return Right_({**ctx, "step1": "done"})

        async def guard2(ctx):
            return Right_({**ctx, "step2": "done"})

        combined = seq(guard1, guard2)
        result = await combined({"initial": "value"})

        assert is_right(result)
        context = get_context(result)
        assert context["step1"] == "done"
        assert context["step2"] == "done"
        assert context["initial"] == "value"

    @pytest.mark.asyncio
    async def test_seq_failure(self):
        """Test sequential composition with failure"""
        async def guard1(ctx):
            return Right_({**ctx, "step1": "done"})

        async def guard2(ctx):
            return Left_([Violation("rule2", "high", "Failed")])

        combined = seq(guard1, guard2)
        result = await combined({"initial": "value"})

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "rule2"

    @pytest.mark.asyncio
    async def test_allOf_success(self):
        """Test parallel composition with success"""
        async def guard1(ctx):
            return Right_({**ctx, "step1": "done"})

        async def guard2(ctx):
            return Right_({**ctx, "step2": "done"})

        combined = allOf(guard1, guard2)
        result = await combined({"initial": "value"})

        assert is_right(result)
        context = get_context(result)
        assert "step1" in context or "step2" in context

    @pytest.mark.asyncio
    async def test_allOf_failure(self):
        """Test parallel composition with failure"""
        async def guard1(ctx):
            return Left_([Violation("rule1", "high", "Failed 1")])

        async def guard2(ctx):
            return Left_([Violation("rule2", "med", "Failed 2")])

        combined = allOf(guard1, guard2)
        result = await combined({"initial": "value"})

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 2
        rule_ids = [v["rule_id"] for v in violations]
        assert "rule1" in rule_ids
        assert "rule2" in rule_ids


class TestLens:
    """Test lens functionality"""

    def test_lens_creation(self):
        """Test lens creation"""
        getter, setter = lens("messages[*].content")
        assert callable(getter)
        assert callable(setter)

    def test_lens_getter(self):
        """Test lens getter"""
        getter, _ = lens("messages[*].content")

        ctx = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"}
            ]
        }

        result = getter(ctx)
        assert result == "Hello Hi there"

    def test_lens_setter(self):
        """Test lens setter"""
        _, setter = lens("output.text")

        ctx = {"output": {"text": "original"}}
        updated = setter(ctx, "updated")

        assert updated["output"]["text"] == "updated"

    @pytest.mark.asyncio
    async def test_focus_composition(self):
        """Test focus composition"""
        async def simple_guard(ctx):
            output = ctx.get("output", "")
            return Right_({**ctx, "output": output.upper()})

        getter, setter = lens("messages[*].content")
        focused = focus(getter, setter, simple_guard)

        ctx = {
            "messages": [
                {"role": "user", "content": "hello world"}
            ]
        }

        result = await focused(ctx)
        assert is_right(result)

        updated_ctx = get_context(result)
        assert updated_ctx["messages"][0]["content"] == "HELLO WORLD"
