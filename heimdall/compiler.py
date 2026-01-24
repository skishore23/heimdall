"""
Policy Compiler for Composable Guard Algebra (Heimdall)

Compiles YAML policies into executable guard graphs using the registry
and combinator system.
"""

import ast
import asyncio
import json
from typing import Any

import yaml

from .comb import allOf, anyOf, focus, kOf, lens, seq, unless
from .policy_schema import validate_policy_full
from .registry import REGISTRY, get_guard
from .types import Guard


def compile_policy(yaml_bytes: bytes) -> tuple[Guard, dict[str, Any]]:
    """
    Compile a YAML policy into an executable guard graph

    Args:
        yaml_bytes: YAML policy content as bytes

    Returns:
        Tuple of (compiled_guard, policy_metadata)

    Raises:
        ValueError: If policy is invalid
        KeyError: If referenced guards or schemas are not found
    """
    try:
        policy_data = yaml.safe_load(yaml_bytes)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML policy: {e}")

    if not isinstance(policy_data, dict):
        raise ValueError("Policy must be a dictionary")

    # Ensure built-in guards are registered before validation
    # Importing guard packs has side effects that register factories
    try:
        import guards  # noqa: F401
    except Exception as e:
        # Fail fast if guard packs cannot be imported
        raise ValueError(f"Failed to load guard packs: {e}")

    # Validate policy against JSON Schema and safety rules
    validate_policy_full(policy_data)

    if "guards" not in policy_data:
        raise ValueError("Policy must contain 'guards' section")

    if "compose" not in policy_data:
        raise ValueError("Policy must contain 'compose' section")

    # Build guard steps
    guard_steps = {}

    for guard_def in policy_data["guards"]:
        if not isinstance(guard_def, dict):
            raise ValueError("Guard definition must be a dictionary")

        guard_id = guard_def.get("id")
        if not guard_id:
            raise ValueError("Guard definition must have 'id' field")

        target = guard_def.get("target")
        if not target:
            raise ValueError(f"Guard '{guard_id}' must have 'target' field")

        # Get guard factory
        try:
            factory = get_guard(guard_id)
        except KeyError:
            raise KeyError(f"Guard '{guard_id}' not found in registry")

        # Build lens for target
        getter, setter = lens(target)

        # Get guard parameters
        params = {}
        if "with" in guard_def:
            params = guard_def["with"]
        elif "with_ref" in guard_def:
            # Load parameters from referenced file
            ref_path = guard_def["with_ref"]
            try:
                with open(ref_path) as f:
                    params = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                raise ValueError(f"Cannot load guard parameters from '{ref_path}': {e}")

        # Create guard instance
        try:
            guard_instance = factory(**params)
        except TypeError as e:
            raise ValueError(f"Invalid parameters for guard '{guard_id}': {e}")

        # Wrap with lens
        focused_guard = focus(getter, setter, guard_instance)
        guard_steps[guard_id] = focused_guard

    # Parse composition expressions
    compose_section = policy_data.get("compose", {})

    # Build composition context
    composition_context = {
        "allOf": allOf,
        "seq": seq,
        "anyOf": anyOf,
        "kOf": kOf,
        "unless": unless,
    }

    # Add guard instances to composition context
    for guard_id, guard_instance in guard_steps.items():
        # Replace dots with underscores for valid Python identifiers
        python_id = guard_id.replace(".", "_")
        composition_context[python_id] = guard_instance

    # Compile all compositions
    compiled_guards = {}

    for phase, compose_expr in compose_section.items():
        if not compose_expr:
            continue

        try:
            # Validate expression safety first
            if not _is_safe_expression(compose_expr, set(composition_context.keys())):
                raise ValueError(f"Unsafe composition expression '{compose_expr}' for phase '{phase}'")

            # Prefer custom AST interpreter to avoid eval entirely
            compiled_guard = _custom_ast_interpreter(compose_expr, composition_context)
            if compiled_guard is None:
                raise ValueError("Failed to interpret composition expression via AST interpreter")

            # If the result is a coroutine, this indicates a bug in combinators
            if asyncio.iscoroutine(compiled_guard):
                raise ValueError("Composition expression returned a coroutine - this indicates a bug in the combinator implementation")

        except Exception as e:
            raise ValueError(f"Invalid composition expression '{compose_expr}' for phase '{phase}': {e}")

        # Validate that result is a Guard
        if not callable(compiled_guard):
            raise ValueError(f"Composition expression for phase '{phase}' must evaluate to a Guard, got {type(compiled_guard)}")

        compiled_guards[phase] = compiled_guard

    # Ensure we have at least a root composition
    if "root" not in compiled_guards:
        raise ValueError("Compose section must have 'root' expression")

    return compiled_guards, policy_data


def compile_policy_from_file(file_path: str) -> tuple[Guard, dict[str, Any]]:
    """
    Compile a policy from a YAML file

    Args:
        file_path: Path to YAML policy file

    Returns:
        Tuple of (compiled_guard, policy_metadata)
    """
    try:
        with open(file_path, 'rb') as f:
            return compile_policy(f.read())
    except FileNotFoundError:
        raise ValueError(f"Policy file not found: {file_path}")
    except Exception as e:
        raise ValueError(f"Error loading policy from '{file_path}': {e}")


def validate_policy_structure(policy_data: dict[str, Any]) -> None:
    """
    Validate policy structure without compiling

    Args:
        policy_data: Parsed policy data

    Raises:
        ValueError: If policy structure is invalid
    """
    required_sections = ["guards", "compose"]
    for section in required_sections:
        if section not in policy_data:
            raise ValueError(f"Policy must contain '{section}' section")

    # Validate guards section
    guards = policy_data["guards"]
    if not isinstance(guards, list):
        raise ValueError("'guards' must be a list")

    for i, guard_def in enumerate(guards):
        if not isinstance(guard_def, dict):
            raise ValueError(f"Guard definition at index {i} must be a dictionary")

        required_fields = ["id", "target"]
        for field in required_fields:
            if field not in guard_def:
                raise ValueError(f"Guard at index {i} must have '{field}' field")

        guard_id = guard_def["id"]
        if not isinstance(guard_id, str):
            raise ValueError(f"Guard ID at index {i} must be a string")

        # Check if guard is registered
        if guard_id not in REGISTRY:
            raise ValueError(f"Guard '{guard_id}' at index {i} is not registered")

    # Validate compose section
    compose = policy_data["compose"]
    if not isinstance(compose, dict):
        raise ValueError("'compose' must be a dictionary")

    if "root" not in compose:
        raise ValueError("'compose' must have 'root' expression")

    root_expr = compose["root"]
    if not isinstance(root_expr, str):
        raise ValueError("'root' expression must be a string")


def _is_safe_expression(expr: str, allowed_names: set[str]) -> bool:
    """
    Validate that a composition expression is safe to evaluate

    Uses AST parsing to ensure only allowed operations and names are used.

    Args:
        expr: The expression to validate
        allowed_names: Set of allowed variable names

    Returns:
        True if the expression is safe, False otherwise
    """
    try:
        # Parse the expression into an AST
        tree = ast.parse(expr, mode='eval')

        # Walk the AST and check for unsafe operations
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                # Check if the name is allowed
                if node.id not in allowed_names:
                    return False
            elif isinstance(node, ast.Import | ast.ImportFrom):
                # No imports allowed
                return False
            elif isinstance(node, ast.Attribute):
                # No attribute access (prevents module.function calls)
                return False
            elif isinstance(node, ast.Call):
                # Only allow calls to known functions
                if isinstance(node.func, ast.Name):
                    if node.func.id not in allowed_names:
                        return False
                else:
                    # Complex function calls not allowed
                    return False
            elif isinstance(node, ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef):
                # No function definitions
                return False
            elif isinstance(node, ast.ListComp | ast.DictComp | ast.SetComp | ast.GeneratorExp):
                # No comprehensions (could be used for side effects)
                return False
            # Note: ast.Exec and ast.Eval were removed in Python 3.8+
            # They're handled by checking for 'exec' and 'eval' as function names

        return True

    except SyntaxError:
        # Invalid syntax
        return False


def _custom_ast_interpreter(expr: str, context: dict[str, Any]) -> Guard | None:
    """
    Custom AST interpreter for composition expressions

    Provides a safer alternative to eval() by directly interpreting AST nodes
    and constructing guard compositions without code execution.
    """
    try:
        tree = ast.parse(expr, mode='eval')
        return _interpret_ast_node(tree.body, context)
    except Exception:
        # Fall back to None if AST interpretation fails
        return None


def _interpret_ast_node(node: ast.AST, context: dict[str, Any]) -> Any:
    """
    Interpret a single AST node and return the corresponding value

    Args:
        node: AST node to interpret
        context: Available variables and functions

    Returns:
        The interpreted value (guard, combinator result, etc.)
    """
    if isinstance(node, ast.Name):
        # Variable lookup
        if node.id in context:
            return context[node.id]
        raise NameError(f"Name '{node.id}' is not defined")

    elif isinstance(node, ast.Call):
        # Function call
        func = _interpret_ast_node(node.func, context)
        args = [_interpret_ast_node(arg, context) for arg in node.args]
        kwargs = {
            kw.arg: _interpret_ast_node(kw.value, context)
            for kw in node.keywords
        }
        return func(*args, **kwargs)

    elif isinstance(node, ast.Attribute):
        # Attribute access (e.g., obj.attr)
        value = _interpret_ast_node(node.value, context)
        return getattr(value, node.attr)

    elif isinstance(node, ast.Constant):
        # Literal values (strings, numbers, etc.)
        return node.value

    elif isinstance(node, ast.List):
        # List literals
        return [_interpret_ast_node(elt, context) for elt in node.elts]

    elif isinstance(node, ast.Dict):
        # Dictionary literals
        return {
            _interpret_ast_node(k, context): _interpret_ast_node(v, context)
            for k, v in zip(node.keys, node.values, strict=False)
        }

    else:
        raise TypeError(f"Unsupported AST node type: {type(node).__name__}")
