"""
Schema Guard Implementations

Implements guards for JSON schema validation and structured output enforcement.
"""

import json
from typing import Any, Literal

from heimdall import register_factory
from heimdall.author import G

try:
    from jsonschema import Draft7Validator, ValidationError, validate
    from jsonschema.exceptions import SchemaError
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    ValidationError = Exception
    SchemaError = Exception
    Draft7Validator = None


@register_factory("schema.validate.json", tier="T0", description="Fast JSON schema validation", performance_budget_ms=4.0)
def schema_validate_json(schema: dict[str, Any], severity: Literal["low", "med", "high", "critical"] = "med"):
    """
    Validate JSON output against a schema

    Args:
        schema: JSON Schema to validate against
        severity: Severity level for validation failures

    Returns:
        Guard that validates JSON structure
    """
    if not JSONSCHEMA_AVAILABLE:
        raise ImportError("jsonschema package is required for schema validation")

    # Validate the schema itself
    if Draft7Validator:
        try:
            Draft7Validator.check_schema(schema)
        except SchemaError as e:
            raise ValueError(f"Invalid JSON Schema: {e}")

    def validate_output(ctx):
        output = ctx.get("output")

        # Try to parse as JSON if it's a string
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                return False  # Invalid JSON

        # Validate against schema
        try:
            validate(instance=output, schema=schema)
            return True
        except ValidationError:
            return False

    return G("schema.validate.json", severity=severity).require(
        validate_output,
        "Invalid JSON"
    ).build()


@register_factory("schema.validate.structure", tier="T0", description="Fast structure validation for dictionaries", performance_budget_ms=1.0)
def schema_validate_structure(
    required_fields: list = None,
    allowed_fields: list = None,
    field_types: dict[str, type] = None,
    severity: Literal["low", "med", "high", "critical"] = "med"
):
    """
    Validate basic structure of output (simpler than full JSON Schema)

    Args:
        required_fields: List of required field names
        allowed_fields: List of allowed field names (if None, any field allowed)
        field_types: Mapping of field names to expected types
        severity: Severity level for validation failures

    Returns:
        Guard that validates basic structure
    """
    if required_fields is None:
        required_fields = []
    if allowed_fields is None:
        allowed_fields = []
    if field_types is None:
        field_types = {}

    def validate_structure(ctx):
        output = ctx.get("output")

        # Must be a dictionary for structure validation
        if not isinstance(output, dict):
            return False

        # Check required fields
        for field in required_fields:
            if field not in output:
                return False

        # Check allowed fields
        if allowed_fields:
            for field in output.keys():
                if field not in allowed_fields:
                    return False

        # Check field types
        for field, expected_type in field_types.items():
            if field in output:
                if not isinstance(output[field], expected_type):
                    return False

        return True

    return G("schema.validate.structure", severity=severity).require(
        validate_structure,
        "Structure validation failed"
    ).build()
