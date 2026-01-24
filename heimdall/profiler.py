"""
Automatic Performance Profiling

Automatically profiles and optimizes guard execution based on:
- Measured execution time
- Performance characteristics
- Resource usage patterns

Transparent to users - optimization happens automatically.
"""

import time
from dataclasses import dataclass

from .types import Ctx, Either, Guard


@dataclass
class GuardProfile:
    """Performance profile of a guard"""
    guard_id: str
    avg_time_ms: float
    max_time_ms: float
    min_time_ms: float
    sample_count: int
    performance_category: str  # "fast", "medium", "slow"

    def update(self, execution_time_ms: float) -> None:
        """Update profile with new measurement"""
        total = self.avg_time_ms * self.sample_count
        self.sample_count += 1
        self.avg_time_ms = (total + execution_time_ms) / self.sample_count
        self.max_time_ms = max(self.max_time_ms, execution_time_ms)
        self.min_time_ms = min(self.min_time_ms, execution_time_ms)

        # Update performance category based on measurements
        self.performance_category = self._classify_performance()

    def _classify_performance(self) -> str:
        """Automatically classify based on performance"""
        if self.avg_time_ms < 5:
            return "fast"  # < 5ms
        elif self.avg_time_ms < 20:
            return "medium"  # 5-20ms
        else:
            return "slow"  # > 20ms


class PerformanceProfiler:
    """
    Automatically profiles and optimizes guard execution.
    Transparent to users - no manual configuration needed.
    """

    def __init__(self):
        self.profiles: dict[str, GuardProfile] = {}
        self.warmup_samples = 3  # Samples before stable classification

    def profile_guard(self, guard_id: str) -> GuardProfile | None:
        """Get guard profile"""
        return self.profiles.get(guard_id)

    def wrap_guard(self, guard_id: str, guard: Guard) -> Guard:
        """
        Wrap guard with automatic profiling and tier assignment.
        Transparent to the guard itself.
        """
        async def profiled(ctx: Ctx) -> Either:
            start = time.perf_counter()

            try:
                result = await guard(ctx)
                return result
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                self._record_execution(guard_id, elapsed)

        return profiled

    def _record_execution(self, guard_id: str, time_ms: float) -> None:
        """Record execution time and update classification"""
        if guard_id not in self.profiles:
            self.profiles[guard_id] = GuardProfile(
                guard_id=guard_id,
                avg_time_ms=time_ms,
                max_time_ms=time_ms,
                min_time_ms=time_ms,
                sample_count=1,
                performance_category="unknown"
            )
        else:
            self.profiles[guard_id].update(time_ms)

    def get_category(self, guard_id: str) -> str:
        """Get performance category"""
        profile = self.profiles.get(guard_id)
        if not profile:
            return "unknown"

        # Need warmup samples before confident classification
        if profile.sample_count < self.warmup_samples:
            return "unknown"

        return profile.performance_category

    def get_guards_by_category(self, category: str) -> list[str]:
        """Get all guards in a specific performance category"""
        return [
            gid for gid, profile in self.profiles.items()
            if profile.performance_category == category and
               profile.sample_count >= self.warmup_samples
        ]

    def should_gate(self, guard_id: str, previous_score: float) -> bool:
        """
        Decide if guard should be gated based on previous guard scores.

        Fast guards always run.
        Medium guards only run if fast guards found issues.
        Slow guards only run if medium guards found issues.
        """
        category = self.get_category(guard_id)

        if category == "fast":
            return False  # Always run
        elif category == "medium":
            # Run if fast guards found something
            return previous_score > 0.3
        elif category == "slow":
            # Run if medium guards found something
            return previous_score > 0.6
        else:
            return True  # Unknown - run it to profile


# Global profiler instance
_profiler = PerformanceProfiler()


def get_profiler() -> PerformanceProfiler:
    """Get global performance profiler"""
    return _profiler


def profile_guard(guard_id: str, guard: Guard) -> Guard:
    """
    Wrap guard with automatic profiling.

    Usage:
        guard = profile_guard("my_guard", my_guard_func)

    System automatically profiles performance and optimizes execution.
    Transparent to users - no configuration needed.
    """
    return _profiler.wrap_guard(guard_id, guard)


async def benchmark_guard(guard: Guard, sample_ctx: Ctx, iterations: int = 10) -> dict[str, float]:
    """
    Benchmark a guard to estimate its performance.

    Returns:
        Dict with avg_ms, max_ms, min_ms, performance_category
    """
    times = []

    for _ in range(iterations):
        start = time.perf_counter()
        await guard(sample_ctx)
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)

    avg_ms = sum(times) / len(times)
    max_ms = max(times)
    min_ms = min(times)

    # Classify
    if avg_ms < 5:
        category = "fast"
    elif avg_ms < 20:
        category = "medium"
    else:
        category = "slow"

    return {
        "avg_ms": avg_ms,
        "max_ms": max_ms,
        "min_ms": min_ms,
        "performance_category": category,
        "samples": iterations
    }

