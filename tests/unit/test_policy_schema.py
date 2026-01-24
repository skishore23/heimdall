"""
Tests for policy schema validation
"""

import pytest

from heimdall.policy_schema import (
    POLICY_SCHEMA,
    validate_composition_expression,
    validate_guard_reference,
    validate_policy_full,
    validate_policy_schema,
)
from heimdall.registry import clear_registry, register_guard


@pytest.fixture(autouse=True)
def setup_registry():
    """Setup test guards in registry"""
    clear_registry()

    async def test_guard(ctx):
        from heimdall.types import Right_
        return Right_(ctx)

    register_guard("test.guard", test_guard)

    yield

    clear_registry()


def test_validate_valid_policy():
    """Test validating a valid policy"""
    policy_data = {
        "policy_id": "test_policy",
        "version": "1.0.0",
        "guards": [
            {
                "id": "test.guard",
                "target": "$.messages[*].content"
            }
        ],
        "compose": {
            "root": "test_guard"
        }
    }

    # Should not raise
    validate_policy_schema(policy_data)


def test_validate_missing_required_field():
    """Test that missing required field fails validation"""
    policy_data = {
        "guards": [
            {"id": "test.guard", "target": "$.messages"}
        ]
        # Missing 'compose'
    }

    with pytest.raises(ValueError, match="schema validation failed"):
        validate_policy_schema(policy_data)


def test_validate_invalid_guard_structure():
    """Test that invalid guard structure fails"""
    policy_data = {
        "guards": [
            {"id": "test.guard"}  # Missing 'target'
        ],
        "compose": {
            "root": "test_guard"
        }
    }

    with pytest.raises(ValueError):
        validate_policy_schema(policy_data)


def test_validate_composition_expression_valid():
    """Test validating valid composition expression"""
    allowed_names = {"allOf", "seq", "test_guard"}

    # Should not raise
    validate_composition_expression("allOf([test_guard])", allowed_names)
    validate_composition_expression("seq([test_guard])", allowed_names)


def test_validate_composition_expression_dangerous_pattern():
    """Test that dangerous patterns are rejected"""
    allowed_names = {"allOf", "test_guard"}

    with pytest.raises(ValueError, match="Dangerous pattern"):
        validate_composition_expression("import os", allowed_names)

    with pytest.raises(ValueError, match="Dangerous pattern"):
        validate_composition_expression("eval('code')", allowed_names)

    with pytest.raises(ValueError, match="Dangerous pattern"):
        validate_composition_expression("__builtins__", allowed_names)


def test_validate_composition_expression_undefined_name():
    """Test that undefined names are rejected"""
    allowed_names = {"allOf"}

    with pytest.raises(ValueError, match="Unknown function"):
        validate_composition_expression("undefined_guard()", allowed_names)


def test_validate_composition_expression_import():
    """Test that import statements are rejected"""
    allowed_names = {"allOf"}

    with pytest.raises(ValueError, match="Dangerous pattern"):
        validate_composition_expression("import sys; allOf()", allowed_names)


def test_validate_composition_expression_lambda():
    """Test that lambda functions are rejected"""
    allowed_names = {"allOf"}

    with pytest.raises(ValueError, match="Function definitions not allowed"):
        validate_composition_expression("lambda x: x", allowed_names)


def test_validate_composition_expression_comprehension():
    """Test that comprehensions are rejected"""
    allowed_names = {"allOf", "guards"}

    with pytest.raises(ValueError, match="Comprehensions not allowed"):
        validate_composition_expression("[g for g in guards]", allowed_names)


def test_validate_guard_reference_valid():
    """Test validating valid guard reference"""
    # test.guard is registered in fixture
    validate_guard_reference("test.guard")


def test_validate_guard_reference_invalid():
    """Test that invalid guard reference fails"""
    with pytest.raises(ValueError, match="not registered"):
        validate_guard_reference("nonexistent.guard")


def test_validate_policy_full_success():
    """Test full policy validation - success"""
    policy_data = {
        "policy_id": "test_policy",
        "version": "1.0.0",
        "guards": [
            {
                "id": "test.guard",
                "target": "$.messages[*].content"
            }
        ],
        "compose": {
            "root": "test_guard"
        }
    }

    # Should not raise
    validate_policy_full(policy_data)


def test_validate_policy_full_invalid_guard():
    """Test full policy validation - invalid guard reference"""
    policy_data = {
        "policy_id": "test_policy",
        "version": "1.0.0",
        "guards": [
            {
                "id": "nonexistent.guard",
                "target": "$.messages"
            }
        ],
        "compose": {
            "root": "nonexistent_guard"
        }
    }

    with pytest.raises(ValueError, match="not registered"):
        validate_policy_full(policy_data)


def test_validate_policy_full_invalid_composition():
    """Test full policy validation - invalid composition"""
    policy_data = {
        "policy_id": "test_policy",
        "version": "1.0.0",
        "guards": [
            {
                "id": "test.guard",
                "target": "$.messages"
            }
        ],
        "compose": {
            "root": "import os; test_guard"
        }
    }

    with pytest.raises(ValueError, match="Dangerous pattern"):
        validate_policy_full(policy_data)


def test_policy_schema_structure():
    """Test that policy schema has expected structure"""
    assert "type" in POLICY_SCHEMA
    assert POLICY_SCHEMA["type"] == "object"
    assert "guards" in POLICY_SCHEMA["properties"]
    assert "compose" in POLICY_SCHEMA["properties"]

