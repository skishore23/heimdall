"""
Guard execution helpers for bifrost routes
"""

from typing import Any

from heimdall import Either, Right_


async def run_input_guards(compiled_guards: dict[str, Any], body: dict[str, Any]) -> Either:
    """
    Run input guards on request body

    Args:
        compiled_guards: Compiled guard functions from policy
        body: Request body to validate

    Returns:
        Either with violations (Left) or updated context (Right)
    """
    input_guard = compiled_guards.get("input")
    if not input_guard:
        return Right_({"phase": "input", **body})

    ctx = {"phase": "input", **body}
    result = await input_guard(ctx)
    return result

