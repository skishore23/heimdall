"""
JSON Schema for policy validation

Provides strict JSON Schema validation for YAML policies to prevent
malicious or malformed policies.
"""

from typing import Any

import jsonschema

# JSON Schema for policy YAML files
POLICY_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["guards", "compose"],
    "properties": {
        "version": {
            "type": "string",
            "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$",
            "description": "Policy version (SemVer)"
        },
        "policy_id": {
            "type": "string",
            "pattern": "^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$",
            "description": "Unique policy identifier"
        },
        "description": {
            "type": "string",
            "maxLength": 500,
            "description": "Human-readable policy description"
        },
        "guards": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "target"],
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^[a-zA-Z0-9_][a-zA-Z0-9_.]*$",
                        "description": "Guard identifier (must be registered)"
                    },
                    "target": {
                        "type": "string",
                        "description": "JSONPath target for guard"
                    },
                    "with": {
                        "type": "object",
                        "description": "Guard parameters"
                    },
                    "with_ref": {
                        "type": "string",
                        "description": "Reference to external parameters file"
                    },
                    "tier": {
                        "type": "string",
                        "enum": ["T0", "T1", "T2"],
                        "description": "Performance tier"
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": "Whether this guard is enabled"
                    }
                },
                "additionalProperties": False
            }
        },
        "compose": {
            "type": "object",
            "required": ["root"],
            "properties": {
                "root": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 10000,
                    "description": "Root composition expression"
                }
            },
            "patternProperties": {
                "^[a-zA-Z_][a-zA-Z0-9_]*$": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 10000,
                    "description": "Named composition phase"
                }
            },
            "additionalProperties": False
        },
        "thresholds": {
            "type": "object",
            "description": "Tier gating thresholds",
            "patternProperties": {
                "^t[0-2]$": {
                    "type": "object",
                    "patternProperties": {
                        "^gate_t[0-2]$": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0
                        }
                    }
                }
            }
        },
        "onnx_models": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "ONNX model identifier"
                    },
                    "sha256": {
                        "type": "string",
                        "pattern": "^[a-fA-F0-9]{64}$",
                        "description": "Expected SHA256 hash of model file"
                    },
                    "quant": {
                        "type": "string",
                        "enum": ["fp32", "fp16", "int8"],
                        "description": "Quantization level"
                    }
                }
            }
        },
        "failure_mode": {
            "type": "string",
            "enum": ["block", "redact", "warn"],
            "default": "block",
            "description": "What to do on policy violation"
        },
        "tier_hints": {
            "type": "object",
            "description": "Performance tier hints for guards",
            "patternProperties": {
                "^[a-zA-Z0-9_.]+$": {
                    "type": "string",
                    "enum": ["fast", "medium", "slow"]
                }
            }
        },
        "performance": {
            "type": "object",
            "description": "Performance configuration",
            "properties": {
                "max_latency_ms": {
                    "type": "number",
                    "minimum": 0
                },
                "fail_mode": {
                    "type": "string",
                    "enum": ["open", "closed"]
                }
            }
        }
    },
    "additionalProperties": False
}


def validate_policy_schema(policy_data: dict[str, Any]) -> None:
    """
    Validate policy against JSON Schema

    Args:
        policy_data: Parsed policy data

    Raises:
        jsonschema.ValidationError: If policy violates schema
        ValueError: If policy is invalid
    """
    try:
        jsonschema.validate(instance=policy_data, schema=POLICY_SCHEMA)
    except jsonschema.ValidationError as e:
        raise ValueError(f"Policy schema validation failed: {e.message} at {list(e.path)}")
    except jsonschema.SchemaError as e:
        raise ValueError(f"Invalid policy schema: {e}")


def validate_composition_expression(expr: str, allowed_names: set[str]) -> None:
    """
    Validate composition expression for safety

    Args:
        expr: Composition expression
        allowed_names: Set of allowed identifiers

    Raises:
        ValueError: If expression is unsafe
    """
    import ast
    import re

    # Check maximum length
    if len(expr) > 10000:
        raise ValueError("Composition expression too long (max 10000 chars)")

    # Check for dangerous patterns
    dangerous_patterns = [
        r'__\w+__',  # Dunder methods
        r'import\s+',
        r'from\s+\w+\s+import',
        r'eval\s*\(',
        r'exec\s*\(',
        r'compile\s*\(',
        r'open\s*\(',
        r'__class__',
        r'__globals__',
        r'__builtins__',
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, expr):
            raise ValueError(f"Dangerous pattern detected in composition: {pattern}")

    # Parse AST
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        raise ValueError(f"Invalid syntax in composition expression: {e}")

    # Walk AST and validate
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in allowed_names:
                raise ValueError(
                    f"Undefined name '{node.id}' in composition expression. "
                    f"Allowed names: {sorted(allowed_names)}"
                )

        elif isinstance(node, ast.Import | ast.ImportFrom):
            raise ValueError("Import statements not allowed in compositions")

        elif isinstance(node, ast.Attribute):
            # Only allow whitelisted attribute access
            if isinstance(node.value, ast.Name):
                # Allow simple attribute access on known objects
                pass
            else:
                raise ValueError("Complex attribute access not allowed in compositions")

        elif isinstance(node, ast.Call):
            # Validate function calls
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct function calls allowed in compositions")

            func_name = node.func.id
            if func_name not in allowed_names:
                raise ValueError(f"Unknown function '{func_name}' in composition")

        elif isinstance(node, ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef):
            raise ValueError("Function definitions not allowed in compositions")

        elif isinstance(node, ast.ListComp | ast.DictComp | ast.SetComp | ast.GeneratorExp):
            raise ValueError("Comprehensions not allowed in compositions")

        elif isinstance(node, ast.Try | ast.ExceptHandler | ast.With):
            raise ValueError("Control flow statements not allowed in compositions")


def validate_guard_reference(guard_id: str) -> None:
    """
    Validate guard reference

    Args:
        guard_id: Guard identifier

    Raises:
        ValueError: If guard_id is invalid
    """
    from .registry import has_guard

    if not has_guard(guard_id):
        raise ValueError(
            f"Guard '{guard_id}' is not registered. "
            "Ensure the guard pack is installed and loaded."
        )


def validate_policy_full(policy_data: dict[str, Any]) -> None:
    """
    Full policy validation: schema + references + expressions

    Args:
        policy_data: Parsed policy data

    Raises:
        ValueError: If policy is invalid
    """
    # Step 1: Validate JSON Schema
    validate_policy_schema(policy_data)

    # Step 2: Validate guard references
    for guard_def in policy_data.get("guards", []):
        guard_id = guard_def["id"]
        validate_guard_reference(guard_id)

    # Step 3: Validate composition expressions
    allowed_names = {"allOf", "seq", "anyOf", "kOf", "unless"}

    # Add guard IDs as allowed names (with dots replaced by underscores)
    for guard_def in policy_data.get("guards", []):
        guard_id = guard_def["id"]
        python_id = guard_id.replace(".", "_")
        allowed_names.add(python_id)

    # Add phase names as allowed names (for referencing other phases)
    compose_section = policy_data.get("compose", {})
    for phase in compose_section.keys():
        allowed_names.add(phase)

    # Validate all composition expressions
    for phase, expr in compose_section.items():
        if expr:
            validate_composition_expression(expr, allowed_names)

