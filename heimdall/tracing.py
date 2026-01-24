"""
Decision Tracing with OpenTelemetry

Provides comprehensive tracing for guard decisions with OpenTelemetry integration.
Each guard execution emits a span with decision metadata.
"""

import time
from functools import wraps
from typing import Any

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    TracerProvider = None
    BatchSpanProcessor = None
    ConsoleSpanExporter = None
    Resource = None
    Status = None
    StatusCode = None


from .types import Ctx, Either, Guard, get_violations, is_left


def setup_tracing(service_name: str = "guardrails", export_to_console: bool = False) -> None:
    """
    Setup OpenTelemetry tracing

    Args:
        service_name: Service name for traces
        export_to_console: Whether to export traces to console (dev mode)
    """
    if not OTEL_AVAILABLE:
        raise RuntimeError("OpenTelemetry not available. Install with: pip install opentelemetry-api opentelemetry-sdk")

    # Create resource
    resource = Resource.create({"service.name": service_name})

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Add exporters
    if export_to_console:
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))

    # Set as global provider
    trace.set_tracer_provider(provider)


def get_tracer(name: str = "heimdall") -> Any:
    """Get tracer instance"""
    if not OTEL_AVAILABLE:
        return None
    return trace.get_tracer(name)


def trace_guard(guard_id: str, tier: str | None = None):
    """
    Decorator to add tracing to a guard

    Args:
        guard_id: Guard identifier
        tier: Performance tier

    Returns:
        Decorator

    Example:
        ```python
        @trace_guard("pii.redact", tier="T0")
        async def pii_redact_guard(ctx: Ctx) -> Either:
            # ... guard logic
            pass
        ```
    """
    def decorator(guard: Guard) -> Guard:
        @wraps(guard)
        async def traced_guard(ctx: Ctx) -> Either:
            if not OTEL_AVAILABLE:
                # No tracing available, just run guard
                return await guard(ctx)

            tracer = get_tracer()

            with tracer.start_as_current_span(
                f"guard.{guard_id}",
                kind=trace.SpanKind.INTERNAL
            ) as span:
                # Set span attributes
                span.set_attribute("guard.id", guard_id)
                if tier:
                    span.set_attribute("guard.tier", tier)

                # Add context snapshot (limited)
                if "user_id" in ctx:
                    span.set_attribute("guard.user_id", str(ctx["user_id"]))
                if "tenant_id" in ctx:
                    span.set_attribute("guard.tenant_id", str(ctx["tenant_id"]))

                # Track timing
                start_time = time.perf_counter()

                try:
                    # Run guard
                    result = await guard(ctx)

                    # Calculate duration
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    # Record decision
                    if is_left(result):
                        # Failed - record violations
                        violations = get_violations(result)
                        span.set_attribute("guard.decision", "block")
                        span.set_attribute("guard.violation_count", len(violations))

                        # Record violation details
                        for i, violation in enumerate(violations[:5]):  # Max 5 violations
                            if isinstance(violation, dict):
                                span.set_attribute(f"guard.violation.{i}.rule_id", violation.get("rule_id", "unknown"))
                                span.set_attribute(f"guard.violation.{i}.severity", violation.get("severity", "unknown"))
                                span.set_attribute(f"guard.violation.{i}.message", violation.get("message", ""))

                        span.set_status(Status(StatusCode.ERROR, "Policy violation"))
                    else:
                        # Passed
                        span.set_attribute("guard.decision", "pass")
                        span.set_status(Status(StatusCode.OK))

                    # Record timing
                    span.set_attribute("guard.duration_ms", duration_ms)

                    # Add taint info if present
                    if "_taint" in ctx:
                        taint = ctx["_taint"]
                        if hasattr(taint, "classifications"):
                            span.set_attribute("guard.taint.classifications", ",".join(taint.classifications))

                    return result

                except Exception as e:
                    # Guard execution error
                    duration_ms = (time.perf_counter() - start_time) * 1000
                    span.set_attribute("guard.duration_ms", duration_ms)
                    span.set_attribute("guard.error", str(e))
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        return traced_guard

    return decorator


def create_decision_trace(
    guard_id: str,
    decision: str,
    ctx: Ctx,
    result: Either,
    duration_ms: float,
    tier: str | None = None
) -> dict[str, Any]:
    """
    Create a decision trace record (for non-OTEL backends)

    Args:
        guard_id: Guard identifier
        decision: Decision ("pass" or "block")
        ctx: Context
        result: Guard result
        duration_ms: Execution duration
        tier: Performance tier

    Returns:
        Decision trace dictionary
    """
    trace = {
        "guard_id": guard_id,
        "decision": decision,
        "duration_ms": duration_ms,
        "timestamp": time.time(),
    }

    if tier:
        trace["tier"] = tier

    # Add context metadata
    if "user_id" in ctx:
        trace["user_id"] = ctx["user_id"]
    if "tenant_id" in ctx:
        trace["tenant_id"] = ctx["tenant_id"]

    # Add violations if blocked
    if is_left(result):
        violations = get_violations(result)
        trace["violations"] = violations
        trace["violation_count"] = len(violations)

    # Add taint info
    if "_taint" in ctx:
        taint = ctx["_taint"]
        if hasattr(taint, "classifications"):
            trace["taint_classifications"] = list(taint.classifications)

    return trace


class DecisionTraceCollector:
    """
    Collector for decision traces (dev/debug mode)

    Provides an in-memory buffer for decision traces that can be
    streamed via SSE/WebSocket for live debugging.
    """

    def __init__(self, max_traces: int = 1000):
        self.traces: list[dict[str, Any]] = []
        self.max_traces = max_traces

    def add_trace(self, trace: dict[str, Any]) -> None:
        """Add a decision trace"""
        self.traces.append(trace)

        # Trim to max size
        if len(self.traces) > self.max_traces:
            self.traces.pop(0)

    def get_traces(
        self,
        guard_id: str | None = None,
        decision: str | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get traces with optional filtering

        Args:
            guard_id: Filter by guard ID
            decision: Filter by decision ("pass" or "block")
            limit: Maximum number of traces to return

        Returns:
            List of traces
        """
        filtered = self.traces

        if guard_id:
            filtered = [t for t in filtered if t.get("guard_id") == guard_id]

        if decision:
            filtered = [t for t in filtered if t.get("decision") == decision]

        return filtered[-limit:]

    def clear_traces(self) -> None:
        """Clear all traces"""
        self.traces.clear()

    def get_statistics(self) -> dict[str, Any]:
        """Get trace statistics"""
        if not self.traces:
            return {
                "total_traces": 0,
                "pass_count": 0,
                "block_count": 0,
                "avg_duration_ms": 0,
            }

        pass_count = sum(1 for t in self.traces if t.get("decision") == "pass")
        block_count = sum(1 for t in self.traces if t.get("decision") == "block")

        durations = [t.get("duration_ms", 0) for t in self.traces]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "total_traces": len(self.traces),
            "pass_count": pass_count,
            "block_count": block_count,
            "avg_duration_ms": avg_duration,
            "guards": list({t.get("guard_id") for t in self.traces if t.get("guard_id")})
        }


# Global trace collector (dev mode)
TRACE_COLLECTOR = DecisionTraceCollector()


def get_trace_collector() -> DecisionTraceCollector:
    """Get global trace collector"""
    return TRACE_COLLECTOR

