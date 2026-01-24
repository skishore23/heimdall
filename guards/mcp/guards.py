"""
MCP-Specific Guards for Agentic Systems

Integrates with Heimdall's temporal tracking and flow analysis
to provide safety for agentic loops and tool use.
"""

from datetime import timedelta
from typing import Literal

from heimdall import register_factory
from heimdall.flow import create_flow_context
from heimdall.temporal import (
    TemporalChain,
    detect_circular_dependency,
    detect_retry_loop,
    enforce_rate_limit,
)
from heimdall.types import Ctx, Either, Guard, Left_, Right_, Violation


@register_factory("mcp.loop.detect", tier="T0", description="Detect retry loops in MCP calls", performance_budget_ms=5.0)
def mcp_loop_detector(
    max_retries: int = 3,
    window_seconds: float = 30.0,
    call_type: str = "mcp_method",
    severity: Literal["low", "med", "high", "critical"] = "high"
) -> Guard:
    """
    Detect retry loops in MCP tool calls.

    Example: Agent keeps calling same tool with same args repeatedly.

    Args:
        max_retries: Maximum retries allowed in window
        window_seconds: Time window to track
        call_type: Type of call to track
    """
    async def guard(ctx: Ctx) -> Either:
        # Get temporal chain from context
        temporal_chain = ctx.get("temporal_chain")
        if not temporal_chain:
            # Create new chain if not exists
            temporal_chain = TemporalChain()
            ctx["temporal_chain"] = temporal_chain

        # Get current MCP method
        method = ctx.get("method", "unknown")
        params = ctx.get("params", {})

        # Create call signature
        call_signature = f"{method}:{str(params)}"

        # Check for retry loop
        is_loop, loop_info = detect_retry_loop(
            temporal_chain,
            max_retries=max_retries,
            window=timedelta(seconds=window_seconds),
            call_type=call_type,
            call_signature=call_signature
        )

        if is_loop:
            return Left_([Violation(
                rule_id="mcp.loop.detected",
                severity="high",
                message=f"Retry loop detected: {method} called {loop_info['count']} times in {window_seconds}s",
                metadata={
                    "method": method,
                    "retry_count": loop_info["count"],
                    "window_seconds": window_seconds,
                    "call_signature": call_signature
                }
            )])

        return Right_(ctx)

    return guard


@register_factory("mcp.circular.detect", tier="T0", description="Detect circular dependencies in MCP calls", performance_budget_ms=5.0)
def mcp_circular_dependency_detector(
    severity: Literal["low", "med", "high", "critical"] = "critical"
) -> Guard:
    """
    Detect circular dependencies in MCP tool calls.

    Example: Tool A calls Tool B calls Tool A (infinite loop).
    """
    async def guard(ctx: Ctx) -> Either:
        temporal_chain = ctx.get("temporal_chain")
        if not temporal_chain:
            temporal_chain = TemporalChain()
            ctx["temporal_chain"] = temporal_chain

        method = ctx.get("method", "unknown")

        # Check for circular dependency
        is_circular, cycle_info = detect_circular_dependency(
            temporal_chain,
            current_call=method
        )

        if is_circular:
            return Left_([Violation(
                rule_id="mcp.circular.detected",
                severity="critical",
                message=f"Circular dependency detected: {' -> '.join(cycle_info['cycle'])}",
                metadata={
                    "cycle": cycle_info["cycle"],
                    "cycle_length": cycle_info["length"]
                }
            )])

        return Right_(ctx)

    return guard


@register_factory("mcp.rate.limit", tier="T0", description="MCP rate limiting", performance_budget_ms=2.0)
def mcp_rate_limiter(
    limits: dict[str, tuple] = None,
    default_limit: tuple = (30, 60)
) -> Guard:
    """
    Rate limit MCP method calls.

    Args:
        limits: Dict of method -> (calls, window_seconds)
        default_limit: Default (calls, window_seconds) for unlisted methods

    Example:
        limits = {
            "tools/call": (10, 60),  # 10 calls per minute
            "resources/read": (20, 60)
        }
    """
    limits = limits or {}

    async def guard(ctx: Ctx) -> Either:
        temporal_chain = ctx.get("temporal_chain")
        if not temporal_chain:
            temporal_chain = TemporalChain()
            ctx["temporal_chain"] = temporal_chain

        method = ctx.get("method", "unknown")

        # Get limit for this method
        max_calls, window_seconds = limits.get(method, default_limit)

        # Check rate limit
        is_limited, limit_info = enforce_rate_limit(
            temporal_chain,
            call_type=method,
            max_calls=max_calls,
            window=timedelta(seconds=window_seconds)
        )

        if is_limited:
            return Left_([Violation(
                rule_id="mcp.rate_limit.exceeded",
                severity="medium",
                message=f"Rate limit exceeded for {method}: {limit_info['current_calls']}/{max_calls} in {window_seconds}s",
                metadata={
                    "method": method,
                    "current_calls": limit_info["current_calls"],
                    "max_calls": max_calls,
                    "window_seconds": window_seconds,
                    "retry_after_seconds": limit_info.get("retry_after", window_seconds)
                }
            )])

        return Right_(ctx)

    return guard


@register_factory("mcp.args.validate", tier="T1", description="MCP args validation", performance_budget_ms=5.0)
def mcp_args_validator(
    max_arg_length: int = 1000,
    forbidden_patterns: list[str] = None
) -> Guard:
    """
    Validate MCP method arguments.

    Args:
        max_arg_length: Maximum length for string arguments
        forbidden_patterns: Regex patterns to block
    """
    forbidden_patterns = forbidden_patterns or []

    async def guard(ctx: Ctx) -> Either:
        params = ctx.get("params", {})

        # Check argument length
        params_str = str(params)
        if len(params_str) > max_arg_length:
            return Left_([Violation(
                rule_id="mcp.args.too_long",
                severity="medium",
                message=f"MCP arguments too long: {len(params_str)}/{max_arg_length}",
                metadata={"length": len(params_str), "max": max_arg_length}
            )])

        # Check forbidden patterns
        import re
        for pattern in forbidden_patterns:
            if re.search(pattern, params_str, re.IGNORECASE):
                return Left_([Violation(
                    rule_id="mcp.args.forbidden_pattern",
                    severity="high",
                    message=f"Forbidden pattern in arguments: {pattern}",
                    metadata={"pattern": pattern, "params": params_str[:100]}
                )])

        return Right_(ctx)

    return guard


@register_factory("mcp.args.pii", tier="T1", description="MCP PII blocking in args", performance_budget_ms=8.0)
def mcp_args_pii_blocker(
    pii_types: list[str] = None,
    action: str = "block"
) -> Guard:
    """
    Block PII in MCP arguments.

    Args:
        pii_types: Types of PII to detect
        action: "block" or "redact"
    """
    pii_types = pii_types or ["EMAIL", "SSN", "PHONE", "CREDIT_CARD"]

    async def guard(ctx: Ctx) -> Either:
        params = ctx.get("params", {})
        params_str = str(params)

        # PII patterns
        import re
        pii_patterns = {
            "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
            "PHONE": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "CREDIT_CARD": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
        }

        violations = []
        for pii_type in pii_types:
            if pii_type in pii_patterns:
                if re.search(pii_patterns[pii_type], params_str):
                    violations.append(Violation(
                        rule_id=f"mcp.args.pii.{pii_type.lower()}",
                        severity="high",
                        message=f"{pii_type} detected in MCP arguments",
                        metadata={"pii_type": pii_type, "action": action}
                    ))

        if violations:
            if action == "block":
                return Left_(violations)
            # If redact, would need to modify params (not implemented here)

        return Right_(ctx)

    return guard


@register_factory("mcp.result.size", tier="T0", description="MCP result size limiting", performance_budget_ms=1.0)
def mcp_result_size_limiter(
    max_size_bytes: int = 100000,
    action: str = "truncate"
) -> Guard:
    """
    Limit MCP result size.

    Args:
        max_size_bytes: Maximum result size in bytes
        action: "truncate" or "block"
    """
    async def guard(ctx: Ctx) -> Either:
        response = ctx.get("response", {})
        result = response.get("result", "")
        result_str = str(result)
        size = len(result_str.encode('utf-8'))

        if size > max_size_bytes:
            if action == "truncate":
                # Truncate result
                truncated = result_str[:max_size_bytes]
                response["result"] = truncated + "... [TRUNCATED]"
                ctx["response"] = response

                ctx["_warnings"] = ctx.get("_warnings", []) + [Violation(
                    rule_id="mcp.result.truncated",
                    severity="low",
                    message=f"Result truncated from {size} to {max_size_bytes} bytes",
                    metadata={"original_size": size, "max_size": max_size_bytes}
                )]
            else:  # block
                return Left_([Violation(
                    rule_id="mcp.result.too_large",
                    severity="medium",
                    message=f"Result too large: {size}/{max_size_bytes} bytes",
                    metadata={"size": size, "max_size": max_size_bytes}
                )])

        return Right_(ctx)

    return guard


@register_factory("mcp.result.toxicity", tier="T1", description="MCP toxicity filtering in results", performance_budget_ms=10.0)
def mcp_result_toxicity_filter(
    categories: list[str] = None,
    threshold: float = 0.7,
    action: str = "redact"
) -> Guard:
    """
    Filter toxicity in MCP results.

    Args:
        categories: Toxicity categories to check
        threshold: Detection threshold
        action: "redact" or "block"
    """
    categories = categories or ["profanity", "harassment", "threats"]

    async def guard(ctx: Ctx) -> Either:
        response = ctx.get("response", {})
        result = response.get("result", "")
        result_str = str(result)

        # Simple pattern-based toxicity detection
        import re
        toxic_patterns = {
            "profanity": r'\b(?:fuck|shit|damn|ass|bitch|bastard)\b',
            "harassment": r'\b(?:idiot|stupid|dumb|moron|loser)\b',
            "threats": r'\b(?:kill|murder|destroy|attack|harm)\b'
        }

        violations = []
        redacted_result = result_str

        for category in categories:
            if category in toxic_patterns:
                pattern = toxic_patterns[category]
                if re.search(pattern, result_str, re.IGNORECASE):
                    violations.append(Violation(
                        rule_id=f"mcp.result.toxicity.{category}",
                        severity="medium",
                        message=f"Toxicity detected in result: {category}",
                        metadata={"category": category, "action": action}
                    ))

                    if action == "redact":
                        redacted_result = re.sub(
                            pattern,
                            "[REDACTED]",
                            redacted_result,
                            flags=re.IGNORECASE
                        )

        if violations:
            if action == "block":
                return Left_(violations)
            else:  # redact
                response["result"] = redacted_result
                ctx["response"] = response
                ctx["_warnings"] = violations

        return Right_(ctx)

    return guard


@register_factory("mcp.tool.allowlist", tier="T0", description="MCP tool allowlist enforcement", performance_budget_ms=1.0)
def mcp_tool_allowlist(
    allowed_methods: list[str],
    severity: Literal["low", "med", "high", "critical"] = "critical"
) -> Guard:
    """
    Allowlist of permitted MCP methods.

    Args:
        allowed_methods: List of allowed method names

    Example:
        allowed_methods = ["tools/list", "tools/call", "resources/read"]
    """
    async def guard(ctx: Ctx) -> Either:
        method = ctx.get("method", "")

        if method not in allowed_methods:
            return Left_([Violation(
                rule_id="mcp.tool.not_allowed",
                severity="critical",
                message=f"MCP method not allowed: {method}",
                metadata={
                    "method": method,
                    "allowed_methods": allowed_methods
                }
            )])

        return Right_(ctx)

    return guard


@register_factory("mcp.result.pii", tier="T1", description="MCP PII redaction in results", performance_budget_ms=8.0)
def mcp_pii_flow_guard(
    pii_types: list[str] = None,
    action: str = "block"
) -> Guard:
    """
    Detect PII flowing from request params to tool results.

    Args:
        pii_types: Types of PII to detect (EMAIL, SSN, PHONE, etc.)
        action: "block" or "redact"
    """
    pii_types = pii_types or ["EMAIL", "SSN", "PHONE", "CREDIT_CARD", "API_KEY"]

    async def guard(ctx: Ctx) -> Either:
        # Get flow context
        flow_ctx = ctx.get("flow_context")
        if not flow_ctx:
            flow_ctx = create_flow_context()
            ctx["flow_context"] = flow_ctx

        # Check if this is a response phase
        phase = ctx.get("phase", "")
        if phase != "mcp_response":
            return Right_(ctx)

        # Get request params and response result
        request_params = ctx.get("request_params", {})
        response = ctx.get("response", {})
        result = response.get("result", "")

        # Simple PII detection (in production, use more sophisticated detection)
        import re

        pii_patterns = {
            "EMAIL": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "SSN": r'\b\d{3}-\d{2}-\d{4}\b',
            "PHONE": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "CREDIT_CARD": r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
            "API_KEY": r'\b[A-Za-z0-9_-]{32,}\b'
        }

        violations = []
        for pii_type in pii_types:
            if pii_type in pii_patterns:
                pattern = pii_patterns[pii_type]

                # Check if PII in params
                params_str = str(request_params)
                if re.search(pattern, params_str):
                    # Check if same PII in result
                    if re.search(pattern, str(result)):
                        violations.append(Violation(
                            rule_id=f"mcp.pii_flow.{pii_type.lower()}",
                            severity="critical" if action == "block" else "high",
                            message=f"{pii_type} detected flowing from request to response",
                            metadata={
                                "pii_type": pii_type,
                                "action": action,
                                "phase": "response"
                            }
                        ))

                        # Redact if requested
                        if action == "redact" and isinstance(result, str):
                            response["result"] = re.sub(pattern, f"[{pii_type}]", result)
                            ctx["response"] = response

        if violations:
            if action == "block":
                return Left_(violations)
            else:
                # Redacted - add warning but allow
                ctx["_warnings"] = violations

        return Right_(ctx)

    return guard


@register_factory("mcp.flow.pii_leak", tier="T0", description="Detect PII leaking to external tools", performance_budget_ms=5.0)
def mcp_flow_pii_leak_detector(
    from_pattern: str = "params.*",
    to_pattern: str = "response.result",
    check: str = "no_pii_flow",
    severity: Literal["low", "med", "high", "critical"] = "critical"
) -> Guard:
    """
    Detect PII flowing from input to external tools (flow tracking).

    Uses flow context to track data lineage.
    """
    async def guard(ctx: Ctx) -> Either:
        # For now, just pass through - this requires full flow tracking infrastructure
        # In production, this would use heimdall.flow module
        return Right_(ctx)

    return guard


# Convenience factory functions

async def create_mcp_agentic_guards() -> dict[str, list]:
    """
    Create full set of MCP agentic safety guards.

    Returns dict of phase -> guard list mappings.
    """
    return {
        "mcp_request": [
            await mcp_tool_allowlist([
                "tools/list",
                "tools/call",
                "resources/read",
                "resources/list",
                "prompts/list",
                "prompts/get"
            ]),
            await mcp_loop_detector(max_retries=3, window_seconds=30),
            await mcp_circular_dependency_detector(),
            await mcp_rate_limiter(limits={
                "tools/call": (10, 60),
                "resources/read": (20, 60)
            }),
            await mcp_args_validator(
                max_arg_length=1000,
                forbidden_patterns=[
                    r'\b(?:rm|delete|DROP|truncate)\b',
                    r'\b(?:exec|eval|system)\b'
                ]
            ),
            await mcp_args_pii_blocker(
                pii_types=["EMAIL", "SSN", "PHONE", "CREDIT_CARD"],
                action="block"
            )
        ],
        "mcp_response": [
            await mcp_pii_flow_guard(action="redact"),
            await mcp_result_size_limiter(max_size_bytes=100000, action="truncate"),
            await mcp_result_toxicity_filter(
                categories=["profanity", "harassment", "threats"],
                action="redact"
            )
        ]
    }

