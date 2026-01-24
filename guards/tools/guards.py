"""
Tool Guard Implementations

Guards for enforcing policies on tool/function calls including
allowlists, denylists, argument validation, and result filtering.
"""

import re
from typing import Literal

from heimdall import Ctx, Either, Guard, Left_, Right_, Violation, register_factory


@register_factory("tools.allowlist", tier="T0", description="Fast tool allowlist enforcement", performance_budget_ms=1.0)
def tool_allowlist(
    allowed_tools: list[str],
    severity: Literal["low", "med", "high", "critical"] = "high"
) -> Guard:
    """
    Allow only specific tools to be called

    Args:
        allowed_tools: List of allowed tool/function names
        severity: Severity level for violations

    Returns:
        Guard that blocks non-allowed tools
    """
    async def run(ctx: Ctx) -> Either:
        # Support both direct context and focused context (via lens)
        function_name = ctx.get("function_name", "") or ctx.get("output", "")

        if function_name and function_name not in allowed_tools:
            return Left_([Violation(
                rule_id="tools.allowlist",
                severity=severity,
                message=f"Tool '{function_name}' not in allowlist",
                evidence={
                    "function_name": function_name,
                    "allowed_tools": allowed_tools
                }
            )])

        return Right_(ctx)

    return run


@register_factory("tools.denylist", tier="T0", description="Fast tool denylist enforcement", performance_budget_ms=1.0)
def tool_denylist(
    denied_tools: list[str],
    severity: Literal["low", "med", "high", "critical"] = "high"
) -> Guard:
    """
    Block specific tools from being called

    Args:
        denied_tools: List of denied tool/function names
        severity: Severity level for violations

    Returns:
        Guard that blocks denied tools
    """
    async def run(ctx: Ctx) -> Either:
        # Support both direct context and focused context (via lens)
        function_name = ctx.get("function_name", "") or ctx.get("output", "")

        if function_name in denied_tools:
            return Left_([Violation(
                rule_id="tools.denylist",
                severity=severity,
                message=f"Tool '{function_name}' is denied",
                evidence={
                    "function_name": function_name,
                    "denied_tools": denied_tools
                }
            )])

        return Right_(ctx)

    return run


@register_factory("tools.args.validator", tier="T1", description="Tool argument validation and sanitization", performance_budget_ms=10.0)
def tool_args_validator(
    required_args: dict[str, list[str]] | None = None,
    forbidden_patterns: dict[str, list[str]] | None = None,
    max_string_length: int = 1000,
    severity: Literal["low", "med", "high", "critical"] = "med"
) -> Guard:
    """
    Validate tool arguments

    Args:
        required_args: Dict of function_name -> list of required argument names
        forbidden_patterns: Dict of function_name -> list of forbidden regex patterns
        max_string_length: Maximum length for string arguments
        severity: Severity level for violations

    Returns:
        Guard that validates tool arguments
    """
    if required_args is None:
        required_args = {}
    if forbidden_patterns is None:
        forbidden_patterns = {}

    # Compile patterns for performance
    compiled_patterns = {}
    for func_name, patterns in forbidden_patterns.items():
        compiled_patterns[func_name] = [re.compile(p, re.IGNORECASE) for p in patterns]

    async def run(ctx: Ctx) -> Either:
        function_name = ctx.get("function_name", "")
        arguments = ctx.get("arguments", {})
        violations = []

        # Check required arguments
        if function_name in required_args:
            for required_arg in required_args[function_name]:
                if required_arg not in arguments:
                    violations.append(Violation(
                        rule_id="tools.args.validator",
                        severity=severity,
                        message=f"Missing required argument '{required_arg}' for tool '{function_name}'",
                        evidence={
                            "function_name": function_name,
                            "missing_argument": required_arg,
                            "provided_arguments": list(arguments.keys())
                        }
                    ))

        # Check forbidden patterns
        if function_name in compiled_patterns:
            for arg_name, arg_value in arguments.items():
                if isinstance(arg_value, str):
                    # Check string length
                    if len(arg_value) > max_string_length:
                        violations.append(Violation(
                            rule_id="tools.args.validator",
                            severity=severity,
                            message=f"Argument '{arg_name}' too long ({len(arg_value)} > {max_string_length})",
                            evidence={
                                "function_name": function_name,
                                "argument_name": arg_name,
                                "length": len(arg_value),
                                "max_length": max_string_length
                            }
                        ))

                    # Check forbidden patterns
                    for pattern in compiled_patterns[function_name]:
                        if pattern.search(arg_value):
                            violations.append(Violation(
                                rule_id="tools.args.validator",
                                severity=severity,
                                message=f"Forbidden pattern found in argument '{arg_name}' for tool '{function_name}'",
                                evidence={
                                    "function_name": function_name,
                                    "argument_name": arg_name,
                                    "pattern": pattern.pattern
                                }
                            ))

        if violations:
            return Left_(violations)

        return Right_(ctx)

    return run


@register_factory("tools.result.filter", tier="T1", description="Tool result filtering and sanitization", performance_budget_ms=8.0)
def tool_result_filter(
    max_result_length: int = 5000,
    forbidden_patterns: list[str] | None = None,
    redact_patterns: dict[str, str] | None = None,
    severity: Literal["low", "med", "high", "critical"] = "med"
) -> Guard:
    """
    Filter and sanitize tool results

    Args:
        max_result_length: Maximum length for tool results
        forbidden_patterns: List of regex patterns that block the result
        redact_patterns: Dict of pattern -> replacement for redaction
        severity: Severity level for violations

    Returns:
        Guard that filters tool results
    """
    if forbidden_patterns is None:
        forbidden_patterns = []
    if redact_patterns is None:
        redact_patterns = {}

    # Compile patterns
    forbidden_compiled = [re.compile(p, re.IGNORECASE) for p in forbidden_patterns]
    redact_compiled = [(re.compile(p, re.IGNORECASE), r) for p, r in redact_patterns.items()]

    async def run(ctx: Ctx) -> Either:
        tool_result = ctx.get("tool_result", {})
        content = tool_result.get("content", "")

        if not isinstance(content, str):
            return Right_(ctx)

        violations = []

        # Check length
        if len(content) > max_result_length:
            violations.append(Violation(
                rule_id="tools.result.filter",
                severity=severity,
                message=f"Tool result too long ({len(content)} > {max_result_length})",
                evidence={
                    "result_length": len(content),
                    "max_length": max_result_length
                }
            ))

        # Check forbidden patterns
        for pattern in forbidden_compiled:
            if pattern.search(content):
                violations.append(Violation(
                    rule_id="tools.result.filter",
                    severity=severity,
                    message="Forbidden pattern found in tool result",
                    evidence={
                        "pattern": pattern.pattern
                    }
                ))

        if violations:
            return Left_(violations)

        # Apply redaction patterns
        filtered_content = content
        for pattern, replacement in redact_compiled:
            filtered_content = pattern.sub(replacement, filtered_content)

        # Update context with filtered content
        updated_result = dict(tool_result)
        updated_result["content"] = filtered_content

        return Right_({**ctx, "tool_result": updated_result})

    return run
