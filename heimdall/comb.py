"""
Combinators for Composable Guard Algebra (Heimdall)

Provides functional combinators for composing guards:
- seq: Sequential composition (stop on first failure)
- allOf: Parallel composition (collect all violations)
- anyOf: Alternative composition (succeed if any guard succeeds)
- kOf: K-of-N composition (succeed if k guards succeed)
- unless: Conditional composition (run guard unless condition)
- focus: Lens-based composition (focus on specific data)
- lens: JSONPath-based lenses for data access
"""

from collections.abc import Callable
from typing import Any

from jsonpath_ng import parse as parse_jsonpath

from .types import Ctx, Either, Guard, Left_, Right_, get_context, is_left, is_right


def seq(*guards: Guard) -> Guard:
    """
    Sequential composition: run guards in sequence, stop on first failure

    Args:
        *guards: Guards to run in sequence

    Returns:
        Guard that runs all guards sequentially
    """
    async def run(ctx: Ctx) -> Either:
        current = ctx
        for guard in guards:
            result = await guard(current)
            if is_left(result):
                return result
            current = result["right"]
        return Right_(current)
    return run


def allOf(*guards: Guard, parallel: bool = False) -> Guard:
    """
    Parallel composition: run all guards, collect all violations

    Args:
        *guards: Guards to run in parallel
        parallel: If True, execute guards concurrently using asyncio.gather

    Returns:
        Guard that runs all guards and collects violations
    """
    async def run(ctx: Ctx) -> Either:
        if parallel:
            return await _allOf_parallel(guards, ctx)
        else:
            return await _allOf_sequential(guards, ctx)
    return run


async def _allOf_sequential(guards: tuple, ctx: Ctx) -> Either:
    """Sequential execution of guards"""
    current = ctx
    all_violations = []

    for guard in guards:
        result = await guard(current)
        if is_left(result):
            violations = result["left"]
            # Handle both Violation objects and dictionaries
            for v in violations:
                if hasattr(v, 'to_dict'):
                    all_violations.append(v.to_dict())
                else:
                    all_violations.append(v)
        else:
            current = result["right"]

    return Left_(all_violations) if all_violations else Right_(current)


async def _allOf_parallel(guards: tuple, ctx: Ctx) -> Either:
    """Parallel execution of guards using asyncio.gather"""
    import asyncio

    # Execute all guards concurrently
    results = await asyncio.gather(
        *[guard(ctx) for guard in guards],
        return_exceptions=False
    )

    all_violations = []
    final_ctx = ctx

    for result in results:
        if is_left(result):
            violations = result["left"]
            for v in violations:
                if hasattr(v, 'to_dict'):
                    all_violations.append(v.to_dict())
                else:
                    all_violations.append(v)
        else:
            # Keep last successful context
            final_ctx = result["right"]

    return Left_(all_violations) if all_violations else Right_(final_ctx)


def anyOf(*guards: Guard) -> Guard:
    """
    Alternative composition: succeed if any guard succeeds

    Args:
        *guards: Guards to try as alternatives

    Returns:
        Guard that succeeds if any guard succeeds
    """
    async def run(ctx: Ctx) -> Either:
        all_violations = []

        for guard in guards:
            result = await guard(ctx)
            if is_right(result):
                return result
            all_violations.extend(result["left"])

        # All guards failed, return combined violations
        return Left_(all_violations)
    return run


def kOf(k: int, *guards: Guard) -> Guard:
    """
    K-of-N composition: succeed if at least k guards succeed

    Args:
        k: Minimum number of guards that must succeed
        *guards: Guards to evaluate

    Returns:
        Guard that succeeds if at least k guards succeed
    """
    async def run(ctx: Ctx) -> Either:
        if k <= 0:
            return Right_(ctx)

        if k > len(guards):
            # Impossible to satisfy
            all_violations = []
            for guard in guards:
                result = await guard(ctx)
                if is_left(result):
                    all_violations.extend(result["left"])
            return Left_(all_violations)

        successes = 0
        all_violations = []
        final_ctx = ctx

        for guard in guards:
            result = await guard(ctx)
            if is_right(result):
                successes += 1
                final_ctx = result["right"]
                if successes >= k:
                    return Right_(final_ctx)
            else:
                all_violations.extend(result["left"])

        # Not enough successes
        return Left_(all_violations)
    return run


def unless(condition: Guard, guard: Guard) -> Guard:
    """
    Conditional composition: run guard unless condition fails

    Args:
        condition: Guard that determines whether to run the main guard
        guard: Guard to run conditionally

    Returns:
        Guard that runs the main guard unless condition fails
    """
    async def run(ctx: Ctx) -> Either:
        cond_result = await condition(ctx)
        if is_left(cond_result):
            # Condition failed, don't run the guard
            return Right_(ctx)

        # Condition passed, run the guard
        return await guard(ctx)
    return run


def lens(jsonpath: str):
    """
    Create a lens from a JSONPath expression with enhanced nested update support

    Args:
        jsonpath: JSONPath expression (e.g., "messages[*].content", "output.text")

    Returns:
        Tuple of (getter, setter) functions
    """
    parsed_path = parse_jsonpath(jsonpath)

    def getter(ctx: Ctx) -> Any:
        """Extract value from context using JSONPath"""
        matches = parsed_path.find(ctx)
        if not matches:
            return None

        # For array targets, join all matches
        if jsonpath.endswith("content") or "*" in jsonpath:
            return " ".join(str(m.value) for m in matches if m.value is not None)

        # For single targets, return first match
        return matches[0].value

    def setter(ctx: Ctx, value: Any) -> Ctx:
        """Set value in context using JSONPath with deep copy safety"""
        import copy
        new_ctx = copy.deepcopy(ctx)  # Ensure immutability

        matches = parsed_path.find(new_ctx)
        if not matches:
            # Path doesn't exist, try to create it
            return _create_path(new_ctx, jsonpath, value)

        # Update all matches for array patterns
        if "*" in jsonpath:
            for match in matches:
                _update_match(match, value)
        else:
            # Update first match for single patterns
            _update_match(matches[0], value)

        return new_ctx

    return getter, setter


def _create_path(ctx: Ctx, jsonpath: str, value: Any) -> Ctx:
    """Create a path in the context if it doesn't exist"""
    import copy
    new_ctx = copy.deepcopy(ctx)

    # Simple path creation for common patterns
    if jsonpath == "output.text":
        if "output" not in new_ctx:
            new_ctx["output"] = {}
        new_ctx["output"]["text"] = value
    elif jsonpath == "output.json":
        if "output" not in new_ctx:
            new_ctx["output"] = {}
        new_ctx["output"]["json"] = value
    # Add more patterns as needed

    return new_ctx


def _update_match(match, value: Any) -> None:
    """Update a JSONPath match with proper nested handling"""
    try:
        # Handle different path types
        if hasattr(match.path, 'left') and hasattr(match.path.left, 'fields'):
            # Array access like messages[0].content
            key = match.path.left.fields[0]
            if hasattr(match.context, 'value') and isinstance(match.context.value, dict):
                match.context.value[key] = value
        elif hasattr(match.path, 'fields') and match.path.fields:
            # Direct field access like output.text
            key = match.path.fields[0]
            if hasattr(match.context, 'value') and isinstance(match.context.value, dict):
                match.context.value[key] = value
        elif hasattr(match, 'full_path'):
            # Complex nested path
            _set_nested_value(match.context.value, match.full_path.path, value)
    except (AttributeError, KeyError, TypeError):
        # Fallback to simple assignment
        if hasattr(match.context, 'value'):
            match.context.value = value


def _set_nested_value(obj: Any, path: str, value: Any) -> None:
    """Set a value in a nested object using dot notation"""
    keys = path.split('.')
    current = obj

    # Navigate to the parent of the target
    for key in keys[:-1]:
        if isinstance(current, dict):
            if key not in current:
                current[key] = {}
            current = current[key]
        else:
            return  # Can't navigate further

    # Set the final value
    if isinstance(current, dict):
        current[keys[-1]] = value


def focus(getter: Callable[[Ctx], Any], setter: Callable[[Ctx, Any], Ctx], guard: Guard) -> Guard:
    """
    Focus a guard on a specific part of the context using a lens

    Args:
        getter: Function to extract value from context
        setter: Function to set value in context
        guard: Guard to run on the focused value

    Returns:
        Guard that runs on the focused part of the context
    """
    async def run(ctx: Ctx) -> Either:
        # Extract the focused value
        extracted = getter(ctx)
        focused_ctx = {"output": extracted}

        # Run the guard on the focused value
        result = await guard(focused_ctx)

        if is_left(result):
            return result

        # Update the context with the result
        updated_context = get_context(result)
        updated_value = updated_context.get("output", getter(ctx))
        updated_ctx = setter(ctx, updated_value)
        return Right_(updated_ctx)
    return run
