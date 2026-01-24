"""
Guard Registry for Composable Guard Algebra (Heimdall)

Provides a registry system for GUARD FACTORIES with decorator-based registration
and factory pattern for guard creation.

Note: This is separate from ONNXRegistry which manages ONNX MODEL FILES.
- Registry: Manages guard factories (functions that create guards)
- ONNXRegistry: Manages ONNX model files, metadata, and loading

The two registries work together:
1. ONNXRegistry provides available models
2. Registry tracks which guards can use those models
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from .types import Guard

# Type variable for guard factory functions
T = TypeVar('T', bound=Callable[..., Guard])

@dataclass
class GuardMetadata:
    """Metadata about a registered guard"""
    factory: Callable[..., Guard]
    tier: Literal["T0", "T1", "T2"] | None = None
    description: str | None = None
    performance_budget_ms: float | None = None
    # ONNX-specific metadata (for T2 guards)
    onnx_model_id: str | None = None
    onnx_category: str | None = None
    requires_onnx: bool = False

    # Alias to satisfy tests expecting timeout_ms
    @property
    def timeout_ms(self) -> float | None:
        return self.performance_budget_ms


@dataclass
class PerformanceMetrics:
    """Performance metrics for guard execution"""
    guard_id: str
    execution_time_ms: float
    budget_ms: float | None
    exceeded_budget: bool
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "guard_id": self.guard_id,
            "execution_time_ms": self.execution_time_ms,
            "budget_ms": self.budget_ms,
            "exceeded_budget": self.exceeded_budget,
            "timestamp": self.timestamp
        }

# Global registry of guard factories with metadata
REGISTRY: dict[str, GuardMetadata] = {}

# Performance metrics storage
PERFORMANCE_METRICS: list[PerformanceMetrics] = []


def with_performance_monitoring(guard_id: str, guard: Guard, budget_ms: float | None = None) -> Guard:
    """
    Wrap a guard with performance monitoring

    Args:
        guard_id: Identifier for the guard
        guard: The guard function to monitor
        budget_ms: Performance budget in milliseconds

    Returns:
        Wrapped guard with performance monitoring
    """
    async def monitored_guard(ctx):
        start_time = time.perf_counter()

        try:
            result = await guard(ctx)
            return result
        finally:
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000

            exceeded_budget = False
            if budget_ms is not None:
                exceeded_budget = execution_time_ms > budget_ms

            metrics = PerformanceMetrics(
                guard_id=guard_id,
                execution_time_ms=execution_time_ms,
                budget_ms=budget_ms,
                exceeded_budget=exceeded_budget,
                timestamp=time.time()
            )

            PERFORMANCE_METRICS.append(metrics)

            # Keep only last 1000 metrics to prevent memory bloat
            if len(PERFORMANCE_METRICS) > 1000:
                PERFORMANCE_METRICS.pop(0)

    return monitored_guard


def get_performance_metrics(guard_id: str | None = None) -> list[PerformanceMetrics]:
    """
    Get performance metrics for guards

    Args:
        guard_id: Optional guard ID to filter by

    Returns:
        List of performance metrics
    """
    if guard_id is None:
        return PERFORMANCE_METRICS.copy()

    return [m for m in PERFORMANCE_METRICS if m.guard_id == guard_id]


def clear_performance_metrics() -> None:
    """Clear all performance metrics"""
    PERFORMANCE_METRICS.clear()


def register_factory(
    guard_id: str,
    tier: Literal["T0", "T1", "T2"] | None = None,
    description: str | None = None,
    performance_budget_ms: float | None = None,
    onnx_model_id: str | None = None,
    onnx_category: str | None = None,
    requires_onnx: bool = False
):
    """
    Decorator to register a guard factory function for use in policies

    A factory function takes parameters and returns a Guard.
    This is used by the policy compiler to create guard instances.

    Args:
        guard_id: Unique identifier for the guard
        tier: Performance tier (T0=fast, T1=medium, T2=slow)
        description: Human-readable description
        performance_budget_ms: Expected execution time budget
        onnx_model_id: ONNX model ID if this guard uses ONNX
        onnx_category: ONNX model category (financial, legal, toxicity, etc.)
        requires_onnx: Whether this guard requires ONNX runtime

    Returns:
        Decorator function

    Example:
        from heimdall.author import G

        @register_factory("pii.redact", tier="T0", performance_budget_ms=1.0)
        def pii_redact(types: list[str], mode: str = "mask"):
            return G("pii.redact").forbid(...).build()
    """
    def decorator(factory: T) -> T:
        """Register the guard factory with metadata"""
        REGISTRY[guard_id] = GuardMetadata(
            factory=factory,
            tier=tier,
            description=description,
            performance_budget_ms=performance_budget_ms,
            onnx_model_id=onnx_model_id,
            onnx_category=onnx_category,
            requires_onnx=requires_onnx
        )
        return factory
    return decorator


def register_guard(
    guard_id: str,
    factory: Callable[..., Guard],
    tier: Literal["T0", "T1", "T2"] | None = None,
    description: str | None = None,
    performance_budget_ms: float | None = None
) -> None:
    """
    Manually register a guard factory

    Args:
        guard_id: Unique identifier for the guard
        factory: Factory function that creates the guard
        tier: Performance tier
        description: Human-readable description
        performance_budget_ms: Expected execution time budget
    """
    REGISTRY[guard_id] = GuardMetadata(
        factory=factory,
        tier=tier,
        description=description,
        performance_budget_ms=performance_budget_ms
    )


def get_guard(guard_id: str) -> Callable[..., Guard]:
    """
    Get a guard factory by ID

    Args:
        guard_id: Unique identifier for the guard

    Returns:
        Factory function for the guard

    Raises:
        KeyError: If guard_id is not found
    """
    if guard_id not in REGISTRY:
        raise KeyError(f"Guard '{guard_id}' not found in registry")
    return REGISTRY[guard_id].factory


def get_guard_metadata(guard_id: str) -> GuardMetadata:
    """
    Get guard metadata by ID

    Args:
        guard_id: Unique identifier for the guard

    Returns:
        Guard metadata

    Raises:
        KeyError: If guard_id is not found
    """
    if guard_id not in REGISTRY:
        raise KeyError(f"Guard '{guard_id}' not found in registry")
    return REGISTRY[guard_id]


def get_registry() -> dict[str, GuardMetadata]:
    """
    Get the guard registry

    Returns:
        The guard registry dictionary
    """
    return REGISTRY


def get_guards_by_tier(tier: Literal["T0", "T1", "T2"]) -> dict[str, GuardMetadata]:
    """
    Get all guards of a specific tier

    Args:
        tier: Performance tier to filter by

    Returns:
        Dictionary of guard_id -> metadata for guards of the specified tier
    """
    return {
        guard_id: metadata
        for guard_id, metadata in REGISTRY.items()
        if metadata.tier == tier
    }


def list_guards() -> list[str]:
    """
    List all registered guard IDs

    Returns:
        List of guard IDs
    """
    return list(REGISTRY.keys())


def has_guard(guard_id: str) -> bool:
    """
    Check if a guard is registered

    Args:
        guard_id: Unique identifier for the guard

    Returns:
        True if guard is registered, False otherwise
    """
    return guard_id in REGISTRY


def clear_registry() -> None:
    """Clear all registered guards (mainly for testing)"""
    REGISTRY.clear()


def get_onnx_guards(category: str | None = None) -> dict[str, GuardMetadata]:
    """
    Get all ONNX guards, optionally filtered by category

    Args:
        category: Optional category filter (financial, legal, toxicity, etc.)

    Returns:
        Dictionary of guard_id -> GuardMetadata for ONNX guards
    """
    onnx_guards = {
        guard_id: metadata
        for guard_id, metadata in REGISTRY.items()
        if metadata.requires_onnx
    }

    if category:
        onnx_guards = {
            guard_id: metadata
            for guard_id, metadata in onnx_guards.items()
            if metadata.onnx_category == category
        }

    return onnx_guards


def get_guards_by_onnx_model(model_id: str) -> dict[str, GuardMetadata]:
    """
    Get all guards that use a specific ONNX model

    Args:
        model_id: ONNX model identifier

    Returns:
        Dictionary of guard_id -> GuardMetadata for guards using the model
    """
    return {
        guard_id: metadata
        for guard_id, metadata in REGISTRY.items()
        if metadata.onnx_model_id == model_id
    }
