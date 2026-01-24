"""
Per-Guard Budget and Timeout Enforcement

Provides runtime budget control for guards:
- Timeout enforcement with asyncio
- Retry logic with exponential backoff
- Circuit breaker pattern for failing guards
- Budget tracking and degradation modes
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .types import Ctx, Either, Guard, Left_, Right_, Violation

# === Budget Configuration ===

@dataclass(frozen=True)
class GuardBudget:
    """Immutable budget configuration for a guard"""
    timeout_ms: float | None = None
    max_retries: int = 0
    retry_backoff_ms: float = 100.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout_seconds: int = 60
    degradation_mode: Literal["fail", "skip", "fallback"] = "fail"


# === Circuit Breaker ===

@dataclass
class CircuitBreaker:
    """Circuit breaker state for a guard"""
    failure_count: int = 0
    last_failure_time: datetime | None = None
    state: Literal["closed", "open", "half_open"] = "closed"
    threshold: int = 5
    timeout_seconds: int = 60

    def record_success(self) -> None:
        """Record a successful execution"""
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self) -> None:
        """Record a failed execution"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.threshold:
            self.state = "open"

    def is_open(self) -> bool:
        """Check if circuit breaker is open"""
        if self.state == "closed":
            return False

        if self.state == "open":
            # Check if timeout has elapsed
            if self.last_failure_time:
                elapsed = datetime.now() - self.last_failure_time
                if elapsed.total_seconds() >= self.timeout_seconds:
                    self.state = "half_open"
                    return False
            return True

        # half_open state allows one attempt
        return False

    def get_state(self) -> str:
        """Get current circuit breaker state"""
        return self.state


# === Timeout Wrapper ===

def with_timeout(guard: Guard, timeout_ms: float) -> Guard:
    """
    Wrap a guard with timeout enforcement

    Args:
        guard: Guard to wrap
        timeout_ms: Timeout in milliseconds

    Returns:
        Guard with timeout enforcement
    """
    async def run(ctx: Ctx) -> Either:
        try:
            result = await asyncio.wait_for(
                guard(ctx),
                timeout=timeout_ms / 1000.0
            )
            return result
        except TimeoutError:
            return Left_([Violation(
                rule_id=f"{guard.__name__}_timeout",
                severity="high",
                message=f"Guard execution exceeded timeout of {timeout_ms}ms",
                code="GUARD_TIMEOUT",
                decision_duration_ms=timeout_ms
            )])

    return run


# === Retry Wrapper ===

def with_retry(guard: Guard, max_retries: int, backoff_ms: float = 100.0) -> Guard:
    """
    Wrap a guard with retry logic

    Args:
        guard: Guard to wrap
        max_retries: Maximum number of retries
        backoff_ms: Initial backoff in milliseconds (doubles each retry)

    Returns:
        Guard with retry logic
    """
    async def run(ctx: Ctx) -> Either:
        last_error = None
        current_backoff = backoff_ms

        for attempt in range(max_retries + 1):
            try:
                result = await guard(ctx)
                return result
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(current_backoff / 1000.0)
                    current_backoff *= 2  # Exponential backoff

        # All retries exhausted
        return Left_([Violation(
            rule_id=f"{guard.__name__}_retry_exhausted",
            severity="high",
            message=f"Guard failed after {max_retries} retries: {str(last_error)}",
            code="GUARD_RETRY_EXHAUSTED",
            evidence={"attempts": max_retries + 1, "error": str(last_error)}
        )])

    return run


# === Circuit Breaker Wrapper ===

# Global circuit breaker registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def with_circuit_breaker(
    guard: Guard,
    guard_id: str,
    threshold: int = 5,
    timeout_seconds: int = 60
) -> Guard:
    """
    Wrap a guard with circuit breaker pattern

    Args:
        guard: Guard to wrap
        guard_id: Unique identifier for this guard
        threshold: Number of failures before opening circuit
        timeout_seconds: Seconds before attempting to close circuit

    Returns:
        Guard with circuit breaker
    """
    # Get or create circuit breaker
    if guard_id not in _circuit_breakers:
        _circuit_breakers[guard_id] = CircuitBreaker(
            threshold=threshold,
            timeout_seconds=timeout_seconds
        )

    breaker = _circuit_breakers[guard_id]

    async def run(ctx: Ctx) -> Either:
        # Check if circuit is open
        if breaker.is_open():
            return Left_([Violation(
                rule_id=f"{guard_id}_circuit_open",
                severity="med",
                message=f"Circuit breaker is open for guard {guard_id}",
                code="CIRCUIT_BREAKER_OPEN",
                evidence={"state": breaker.get_state(), "failures": breaker.failure_count}
            )])

        try:
            result = await guard(ctx)

            # Record success
            from .types import is_left
            if not is_left(result):
                breaker.record_success()
            else:
                breaker.record_failure()

            return result
        except Exception as e:
            breaker.record_failure()
            return Left_([Violation(
                rule_id=f"{guard_id}_error",
                severity="critical",
                message=f"Guard execution failed: {str(e)}",
                code="GUARD_ERROR",
                evidence={"error": str(e)}
            )])

    return run


# === Complete Budget Enforcement ===

def with_budget(guard: Guard, guard_id: str, budget: GuardBudget) -> Guard:
    """
    Wrap a guard with complete budget enforcement

    Applies timeout, retry, and circuit breaker according to budget configuration.

    Args:
        guard: Guard to wrap
        guard_id: Unique identifier for this guard
        budget: Budget configuration

    Returns:
        Guard with budget enforcement
    """
    wrapped = guard

    # Apply timeout if configured
    if budget.timeout_ms is not None:
        wrapped = with_timeout(wrapped, budget.timeout_ms)

    # Apply retry if configured
    if budget.max_retries > 0:
        wrapped = with_retry(wrapped, budget.max_retries, budget.retry_backoff_ms)

    # Apply circuit breaker
    wrapped = with_circuit_breaker(
        wrapped,
        guard_id,
        budget.circuit_breaker_threshold,
        budget.circuit_breaker_timeout_seconds
    )

    # Apply degradation mode wrapper
    if budget.degradation_mode == "skip":
        wrapped = _with_skip_on_failure(wrapped, guard_id)
    elif budget.degradation_mode == "fallback":
        wrapped = _with_fallback_on_failure(wrapped, guard_id)

    return wrapped


def _with_skip_on_failure(guard: Guard, guard_id: str) -> Guard:
    """Skip guard on failure (permissive mode)"""
    async def run(ctx: Ctx) -> Either:
        try:
            result = await guard(ctx)
            from .types import is_left
            if is_left(result):
                # Log but don't block
                violations = result["left"]
                for v in violations:
                    if isinstance(v, dict):
                        v["shadow_mode"] = True
                return Right_(ctx)  # Pass through
            return result
        except Exception:
            return Right_(ctx)  # Pass through on error

    return run


def _with_fallback_on_failure(guard: Guard, guard_id: str) -> Guard:
    """Use simple fallback on failure"""
    async def run(ctx: Ctx) -> Either:
        try:
            result = await guard(ctx)
            from .types import is_left
            if is_left(result):
                # Try simple fallback (e.g., regex-based check)
                # For now, just log and pass through
                return Right_(ctx)
            return result
        except Exception:
            return Right_(ctx)

    return run


# === Instrumentation ===

@dataclass
class GuardMetrics:
    """Metrics for a guard execution"""
    guard_id: str
    start_time: float
    end_time: float
    duration_ms: float
    success: bool
    retries: int = 0
    circuit_breaker_state: str = "closed"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "guard_id": self.guard_id,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "retries": self.retries,
            "circuit_breaker_state": self.circuit_breaker_state,
            "timestamp": self.start_time
        }


def with_metrics(guard: Guard, guard_id: str) -> Guard:
    """
    Wrap a guard with metrics collection

    Args:
        guard: Guard to wrap
        guard_id: Guard identifier

    Returns:
        Guard with metrics collection
    """
    async def run(ctx: Ctx) -> Either:
        start_time = time.time()

        try:
            result = await guard(ctx)
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            from .types import is_left

            # Attach metrics to context
            if "_guard_metrics" not in ctx:
                ctx["_guard_metrics"] = []

            ctx["_guard_metrics"].append({
                "guard_id": guard_id,
                "duration_ms": duration_ms,
                "success": not is_left(result),
                "timestamp": start_time
            })

            return result
        except Exception as e:
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000

            if "_guard_metrics" not in ctx:
                ctx["_guard_metrics"] = []

            ctx["_guard_metrics"].append({
                "guard_id": guard_id,
                "duration_ms": duration_ms,
                "success": False,
                "error": str(e),
                "timestamp": start_time
            })

            raise

    return run


__all__ = [
    # Configuration
    "GuardBudget",
    # Circuit breaker
    "CircuitBreaker",
    # Wrappers
    "with_timeout",
    "with_retry",
    "with_circuit_breaker",
    "with_budget",
    "with_metrics",
    # Metrics
    "GuardMetrics",
]

