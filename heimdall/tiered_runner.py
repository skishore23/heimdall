"""
Tiered Guard Runner

Implements T0/T1/T2 tiered execution with early exits and performance budgets.
Optimizes for latency by running fast guards first and gating expensive guards.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal

from .registry import get_guards_by_tier
from .types import (
    Ctx,
    Guard,
    get_context,
    get_violations,
    is_left,
)


@dataclass
class TierConfig:
    """Configuration for a guard tier"""
    enabled: bool = True
    timeout_ms: float = 100.0  # Per-guard timeout
    total_budget_ms: float = 200.0  # Total tier budget
    early_exit_on_violation: bool = True
    gate_condition: str | None = None  # e.g., "t0_score > 0.6"


@dataclass
class ExecutionResult:
    """Result of tiered guard execution"""
    violations: list[dict[str, Any]]
    context: Ctx
    tier_stats: dict[str, dict[str, Any]]
    total_time_ms: float
    early_exit: bool = False
    gated_tiers: list[str] = None


class TieredGuardRunner:
    """
    Executes guards in T0/T1/T2 tiers with performance optimization

    T0: Ultra-fast (regex, allowlists) - always run
    T1: Fast semantic (lightweight ML) - run based on T0 scores
    T2: Heavy ML (ONNX, APIs) - gated by T1 scores
    """

    def __init__(self, tier_configs: dict[str, TierConfig] | None = None):
        """
        Initialize tiered runner

        Args:
            tier_configs: Configuration for each tier (T0, T1, T2)
        """
        self.tier_configs = tier_configs or {
            "T0": TierConfig(
                enabled=True,
                timeout_ms=5.0,
                total_budget_ms=10.0,
                early_exit_on_violation=False  # Always run T0 completely
            ),
            "T1": TierConfig(
                enabled=True,
                timeout_ms=20.0,
                total_budget_ms=50.0,
                early_exit_on_violation=True,
                gate_condition="t0_score < 0.8"  # Only run if T0 didn't find major issues
            ),
            "T2": TierConfig(
                enabled=True,
                timeout_ms=100.0,
                total_budget_ms=200.0,
                early_exit_on_violation=True,
                gate_condition="t1_score < 0.9"  # Only run if T1 didn't find major issues
            )
        }

    async def run_tiered_guards(
        self,
        guards: dict[str, Guard],
        context: Ctx,
        enabled_tiers: list[Literal["T0", "T1", "T2"]] | None = None
    ) -> ExecutionResult:
        """
        Run guards in tiered fashion with early exits

        Args:
            guards: Dictionary of guard_id -> guard_instance
            context: Context to process
            enabled_tiers: List of tiers to run (defaults to all enabled)

        Returns:
            ExecutionResult with violations, context, and performance stats
        """
        start_time = time.time()

        if enabled_tiers is None:
            enabled_tiers = ["T0", "T1", "T2"]

        all_violations = []
        current_context = context.copy()
        tier_stats = {}
        gated_tiers = []
        early_exit = False

        # Calculate tier scores for gating
        tier_scores = {"t0_score": 0.0, "t1_score": 0.0, "t2_score": 0.0}

        for tier in ["T0", "T1", "T2"]:
            if tier not in enabled_tiers:
                continue

            tier_config = self.tier_configs.get(tier)
            if not tier_config or not tier_config.enabled:
                continue

            # Check gate condition
            if tier_config.gate_condition:
                if not self._evaluate_gate_condition(tier_config.gate_condition, tier_scores):
                    gated_tiers.append(tier)
                    tier_stats[tier] = {
                        "status": "gated",
                        "gate_condition": tier_config.gate_condition,
                        "tier_scores": tier_scores.copy()
                    }
                    continue

            # Run tier guards
            tier_result = await self._run_tier(
                tier, guards, current_context, tier_config
            )

            tier_stats[tier] = tier_result["stats"]

            if tier_result["violations"]:
                all_violations.extend(tier_result["violations"])

                # Update tier score based on violations
                max_score = max(
                    (v.get("score", 0.0) for v in tier_result["violations"]),
                    default=0.0
                )
                tier_scores[f"{tier.lower()}_score"] = max_score

                # Early exit if configured
                if tier_config.early_exit_on_violation:
                    early_exit = True
                    tier_stats[tier]["early_exit"] = True
                    break

            # Update context
            current_context = tier_result["context"]

        total_time = (time.time() - start_time) * 1000

        return ExecutionResult(
            violations=all_violations,
            context=current_context,
            tier_stats=tier_stats,
            total_time_ms=total_time,
            early_exit=early_exit,
            gated_tiers=gated_tiers
        )

    async def _run_tier(
        self,
        tier: str,
        all_guards: dict[str, Guard],
        context: Ctx,
        config: TierConfig
    ) -> dict[str, Any]:
        """Run all guards in a specific tier"""
        tier_start = time.time()
        tier_violations = []
        current_context = context.copy()

        # Get guards for this tier
        tier_guard_metadata = get_guards_by_tier(tier)
        tier_guards = {
            guard_id: all_guards[guard_id]
            for guard_id in tier_guard_metadata.keys()
            if guard_id in all_guards
        }

        guard_results = []

        for guard_id, guard in tier_guards.items():
            guard_start = time.time()

            try:
                # Run guard with timeout
                result = await asyncio.wait_for(
                    guard(current_context),
                    timeout=config.timeout_ms / 1000.0
                )

                guard_time = (time.time() - guard_start) * 1000

                if is_left(result):
                    violations = get_violations(result)
                    tier_violations.extend(violations)

                    guard_results.append({
                        "guard_id": guard_id,
                        "status": "violation",
                        "violations": len(violations),
                        "time_ms": guard_time
                    })
                else:
                    # Update context
                    current_context = get_context(result)

                    guard_results.append({
                        "guard_id": guard_id,
                        "status": "pass",
                        "time_ms": guard_time
                    })

            except TimeoutError:
                guard_time = (time.time() - guard_start) * 1000
                guard_results.append({
                    "guard_id": guard_id,
                    "status": "timeout",
                    "time_ms": guard_time
                })

            except Exception as e:
                guard_time = (time.time() - guard_start) * 1000
                guard_results.append({
                    "guard_id": guard_id,
                    "status": "error",
                    "error": str(e),
                    "time_ms": guard_time
                })

            # Check tier budget
            tier_elapsed = (time.time() - tier_start) * 1000
            if tier_elapsed > config.total_budget_ms:
                guard_results.append({
                    "tier": tier,
                    "status": "budget_exceeded",
                    "budget_ms": config.total_budget_ms,
                    "elapsed_ms": tier_elapsed
                })
                break

        tier_time = (time.time() - tier_start) * 1000

        return {
            "violations": tier_violations,
            "context": current_context,
            "stats": {
                "tier": tier,
                "total_time_ms": tier_time,
                "guards_run": len(guard_results),
                "violations": len(tier_violations),
                "guard_results": guard_results
            }
        }

    def _evaluate_gate_condition(
        self,
        condition: str,
        tier_scores: dict[str, float]
    ) -> bool:
        """
        Evaluate a gate condition like 't0_score < 0.8'

        Args:
            condition: Gate condition string
            tier_scores: Current tier scores

        Returns:
            True if condition passes (gate opens), False otherwise
        """
        try:
            # Simple condition evaluation - in production, use a proper parser
            # For now, support basic comparisons like "t0_score < 0.8"
            if "<" in condition:
                var, threshold = condition.split("<")
                var = var.strip()
                threshold = float(threshold.strip())
                return tier_scores.get(var, 0.0) < threshold
            elif ">" in condition:
                var, threshold = condition.split(">")
                var = var.strip()
                threshold = float(threshold.strip())
                return tier_scores.get(var, 0.0) > threshold
            elif "==" in condition:
                var, threshold = condition.split("==")
                var = var.strip()
                threshold = float(threshold.strip())
                return tier_scores.get(var, 0.0) == threshold
            else:
                # Default to True if condition can't be parsed
                return True
        except Exception:
            # Default to True if condition evaluation fails
            return True


# Convenience function for common use cases
async def run_tiered_guards(
    guards: dict[str, Guard],
    context: Ctx,
    enabled_tiers: list[Literal["T0", "T1", "T2"]] | None = None,
    tier_configs: dict[str, TierConfig] | None = None
) -> ExecutionResult:
    """
    Convenience function to run tiered guards

    Args:
        guards: Dictionary of guard_id -> guard_instance
        context: Context to process
        enabled_tiers: List of tiers to run
        tier_configs: Custom tier configurations

    Returns:
        ExecutionResult
    """
    runner = TieredGuardRunner(tier_configs)
    return await runner.run_tiered_guards(guards, context, enabled_tiers)
