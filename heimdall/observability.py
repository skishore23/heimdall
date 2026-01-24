"""
OpenTelemetry Integration for Guard Observability

Provides first-class observability with OpenTelemetry spans for every guard execution.
Traces include: rule_id, severity, decision, duration_ms, source, sink, redaction_applied.

Fail-fast design: if OTel is enabled but misconfigured, raise errors immediately.
"""

import time
from typing import Any

from .types import Ctx, Either, Guard, get_violations, is_left

# === OpenTelemetry Types (duck-typed for optional dependency) ===

class OTelProvider:
    """Abstract OpenTelemetry provider"""

    def __init__(self, enabled: bool = False, endpoint: str | None = None, service_name: str = "heimdall"):
        self.enabled = enabled
        self.endpoint = endpoint
        self.service_name = service_name
        self._tracer = None

    def initialize(self) -> None:
        """Initialize OpenTelemetry provider"""
        if not self.enabled:
            return

        if not self.endpoint:
            raise ValueError("OTel endpoint must be set when OTel is enabled")

        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            # Create resource
            resource = Resource.create({
                "service.name": self.service_name,
                "service.version": "1.0.0",
            })

            # Create tracer provider
            provider = TracerProvider(resource=resource)

            # Create OTLP exporter
            exporter = OTLPSpanExporter(endpoint=self.endpoint)

            # Add batch processor
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)

            # Set global tracer provider
            trace.set_tracer_provider(provider)

            # Get tracer
            self._tracer = trace.get_tracer(__name__)

        except ImportError as e:
            raise ImportError(
                "OpenTelemetry is enabled but not installed. "
                "Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp"
            ) from e

    def get_tracer(self):
        """Get the tracer instance"""
        return self._tracer


# Global provider instance
_otel_provider: OTelProvider | None = None


def initialize_otel(enabled: bool, endpoint: str | None = None, service_name: str = "heimdall") -> None:
    """
    Initialize global OpenTelemetry provider

    Args:
        enabled: Enable OpenTelemetry tracing
        endpoint: OTLP endpoint (required if enabled=True)
        service_name: Service name for traces
    """
    global _otel_provider
    _otel_provider = OTelProvider(enabled, endpoint, service_name)
    _otel_provider.initialize()


def get_otel_provider() -> OTelProvider | None:
    """Get the global OTel provider"""
    return _otel_provider


# === Guard Instrumentation ===

def with_otel_span(guard: Guard, rule_id: str, severity: str = "high") -> Guard:
    """
    Wrap a guard with OpenTelemetry span

    Creates a span for each guard execution with attributes:
    - rule_id: Guard identifier
    - severity: Violation severity
    - decision: "allow" or "block"
    - duration_ms: Execution time
    - source: Data source (if available)
    - sink: Data sink (if available)
    - redaction_applied: Redaction strategy (if applied)

    Args:
        guard: Guard to instrument
        rule_id: Rule identifier
        severity: Expected severity level

    Returns:
        Instrumented guard
    """
    async def run(ctx: Ctx) -> Either:
        provider = get_otel_provider()

        if not provider or not provider.enabled:
            # No OTel, just run guard
            return await guard(ctx)

        tracer = provider.get_tracer()
        if not tracer:
            # Tracer not initialized, just run guard
            return await guard(ctx)

        # Import trace here for span status
        from opentelemetry import trace as otel_trace

        # Start span
        with tracer.start_as_current_span(f"guard.{rule_id}") as span:
            start_time = time.time()

            try:
                # Execute guard
                result = await guard(ctx)

                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000

                # Set span attributes
                span.set_attribute("rule_id", rule_id)
                span.set_attribute("severity", severity)
                span.set_attribute("duration_ms", duration_ms)

                # Determine decision
                if is_left(result):
                    span.set_attribute("decision", "block")

                    # Extract violation details
                    violations = get_violations(result)
                    if violations:
                        first_violation = violations[0]

                        if "source" in first_violation:
                            span.set_attribute("source", first_violation["source"])
                        if "sink" in first_violation:
                            span.set_attribute("sink", first_violation["sink"])
                        if "redaction_applied" in first_violation:
                            span.set_attribute("redaction_applied", first_violation["redaction_applied"])

                        # Set span status to error
                        span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR, first_violation.get("message", "Guard blocked")))
                else:
                    span.set_attribute("decision", "allow")
                    span.set_status(otel_trace.Status(otel_trace.StatusCode.OK))

                return result

            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                span.set_attribute("duration_ms", duration_ms)
                span.set_attribute("decision", "error")
                span.set_attribute("error", str(e))
                span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR, str(e)))
                raise

    return run


# === Decision Trace Stream ===

class DecisionTrace:
    """Decision trace event for streaming"""

    def __init__(
        self,
        rule_id: str,
        decision: str,
        duration_ms: float,
        severity: str = "high",
        message: str = "",
        metadata: dict[str, Any] | None = None
    ):
        self.rule_id = rule_id
        self.decision = decision
        self.duration_ms = duration_ms
        self.severity = severity
        self.message = message
        self.metadata = metadata or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "rule_id": self.rule_id,
            "decision": self.decision,
            "duration_ms": self.duration_ms,
            "severity": self.severity,
            "message": self.message,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }


class DecisionTraceCollector:
    """Collects decision traces for streaming"""

    def __init__(self, max_traces: int = 1000):
        self._traces: list[DecisionTrace] = []
        self._max_traces = max_traces

    def add_trace(self, trace: DecisionTrace) -> None:
        """Add a decision trace"""
        self._traces.append(trace)

        # Keep only recent traces
        if len(self._traces) > self._max_traces:
            self._traces = self._traces[-self._max_traces:]

    def get_traces(self, since: float | None = None) -> list[DecisionTrace]:
        """Get traces since timestamp"""
        if since is None:
            return list(self._traces)

        return [t for t in self._traces if t.timestamp >= since]

    def clear(self) -> None:
        """Clear all traces"""
        self._traces.clear()


# Global trace collector
_trace_collector = DecisionTraceCollector()


def get_trace_collector() -> DecisionTraceCollector:
    """Get the global trace collector"""
    return _trace_collector


def with_decision_trace(guard: Guard, rule_id: str) -> Guard:
    """
    Wrap a guard with decision trace collection

    Args:
        guard: Guard to instrument
        rule_id: Rule identifier

    Returns:
        Instrumented guard
    """
    async def run(ctx: Ctx) -> Either:
        start_time = time.time()

        try:
            result = await guard(ctx)
            duration_ms = (time.time() - start_time) * 1000

            # Create trace
            if is_left(result):
                violations = get_violations(result)
                trace = DecisionTrace(
                    rule_id=rule_id,
                    decision="block",
                    duration_ms=duration_ms,
                    severity=violations[0].get("severity", "high") if violations else "high",
                    message=violations[0].get("message", "") if violations else "",
                    metadata={"violations": len(violations)}
                )
            else:
                trace = DecisionTrace(
                    rule_id=rule_id,
                    decision="allow",
                    duration_ms=duration_ms
                )

            # Add to collector
            _trace_collector.add_trace(trace)

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            trace = DecisionTrace(
                rule_id=rule_id,
                decision="error",
                duration_ms=duration_ms,
                severity="critical",
                message=str(e)
            )
            _trace_collector.add_trace(trace)
            raise

    return run


# === Combined Instrumentation ===

def with_observability(
    guard: Guard,
    rule_id: str,
    severity: str = "high",
    enable_otel: bool = True,
    enable_trace: bool = True
) -> Guard:
    """
    Wrap guard with full observability (OTel + decision trace)

    Args:
        guard: Guard to instrument
        rule_id: Rule identifier
        severity: Expected severity
        enable_otel: Enable OpenTelemetry spans
        enable_trace: Enable decision trace collection

    Returns:
        Fully instrumented guard
    """
    wrapped = guard

    if enable_otel:
        wrapped = with_otel_span(wrapped, rule_id, severity)

    if enable_trace:
        wrapped = with_decision_trace(wrapped, rule_id)

    return wrapped


__all__ = [
    # Initialization
    "initialize_otel",
    "get_otel_provider",
    # Instrumentation
    "with_otel_span",
    "with_decision_trace",
    "with_observability",
    # Decision trace
    "DecisionTrace",
    "DecisionTraceCollector",
    "get_trace_collector",
]

