"""
Advanced Orchestration DSL

High-level DSL for composing sophisticated guardrails using all category
theory primitives. Provides fluent interface for guard composition.

Core Concepts:
- Fluent composition API
- Declarative guard building
- Integration of flow, temporal, optics, etc.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .comb import allOf, anyOf, kOf, seq
from .comonad import environment_aware_guard, history_aware_guard, windowed_guard
from .flow import flow_guard
from .kleisli import chain as kleisli_chain
from .kleisli import unless_condition, when
from .natural import (
    promote_to_t1,
    promote_to_t2,
    to_blocking,
    to_permissive,
    with_retry,
    with_timeout,
)
from .optics import Lens, Prism, Traversal, lens_guard, prism_guard, traversal_guard
from .temporal import (
    TemporalChain,
    detect_circular_dependency,
    detect_retry_loop,
    enforce_rate_limit,
)
from .types import Ctx, Either, Guard, Right_


@dataclass
class GuardBuilder:
    """
    Fluent builder for sophisticated guard composition
    Integrates all category theory primitives
    """
    guards: list[Guard] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    flow_enabled: bool = False
    temporal_enabled: bool = False
    temporal_chain: TemporalChain | None = None

    def add(self, guard: Guard) -> 'GuardBuilder':
        """Add a guard to the composition"""
        self.guards.append(guard)
        return self

    def sequence(self, *guards: Guard) -> 'GuardBuilder':
        """Add sequential guards"""
        if guards:
            self.guards.append(seq(*guards))
        return self

    def parallel(self, *guards: Guard) -> 'GuardBuilder':
        """Add parallel guards"""
        if guards:
            self.guards.append(allOf(*guards))
        return self

    def any_of(self, *guards: Guard) -> 'GuardBuilder':
        """Add alternative guards (any succeeds)"""
        if guards:
            self.guards.append(anyOf(*guards))
        return self

    def k_of_n(self, k: int, *guards: Guard) -> 'GuardBuilder':
        """Add k-of-n composition"""
        if guards:
            self.guards.append(kOf(k, *guards))
        return self

    def when_condition(self, condition: Callable[[Ctx], bool], guard: Guard) -> 'GuardBuilder':
        """Add conditional guard"""
        self.guards.append(when(condition, guard))
        return self

    def unless_condition(self, condition: Callable[[Ctx], bool], guard: Guard) -> 'GuardBuilder':
        """Add unless guard"""
        self.guards.append(unless_condition(condition, guard))
        return self

    def with_lens(self, lens: Lens, transform: Callable[[Any], Any]) -> 'GuardBuilder':
        """Add lens-based transformation"""
        self.guards.append(lens_guard(lens, transform))
        return self

    def with_prism(self, prism: Prism, on_match: Guard, on_miss: Guard | None = None) -> 'GuardBuilder':
        """Add prism-based conditional guard"""
        self.guards.append(prism_guard(prism, on_match, on_miss))
        return self

    def with_traversal(self, traversal: Traversal, element_guard: Guard) -> 'GuardBuilder':
        """Add traversal-based guard"""
        self.guards.append(traversal_guard(traversal, element_guard))
        return self

    def with_flow_tracking(self, from_pattern: str, to_pattern: str,
                           predicate: Callable[[Any, Any], bool],
                           rule_id: str, message: str) -> 'GuardBuilder':
        """Add flow-based tracking guard"""
        self.flow_enabled = True
        self.guards.append(flow_guard(from_pattern, to_pattern, predicate, rule_id, message))
        return self

    def with_temporal_tracking(self) -> 'GuardBuilder':
        """Enable temporal tracking"""
        self.temporal_enabled = True
        if not self.temporal_chain:
            self.temporal_chain = TemporalChain()
        return self

    def detect_retry_loops(self, max_retries: int, window: timedelta, call_type: str) -> 'GuardBuilder':
        """Add retry loop detection"""
        if not self.temporal_chain:
            self.temporal_chain = TemporalChain()

        self.guards.append(detect_retry_loop(self.temporal_chain, max_retries, window, call_type))
        return self

    def detect_circular_deps(self) -> 'GuardBuilder':
        """Add circular dependency detection"""
        if not self.temporal_chain:
            self.temporal_chain = TemporalChain()

        self.guards.append(detect_circular_dependency(self.temporal_chain))
        return self

    def rate_limit(self, event_type: str, max_count: int, window: timedelta) -> 'GuardBuilder':
        """Add rate limiting"""
        if not self.temporal_chain:
            self.temporal_chain = TemporalChain()

        self.guards.append(enforce_rate_limit(self.temporal_chain, event_type, max_count, window))
        return self

    def with_history(self, check: Callable, rule_id: str, message: str, max_history: int = 10) -> 'GuardBuilder':
        """Add history-aware guard"""
        self.guards.append(history_aware_guard(check, rule_id, message, max_history))
        return self

    def with_environment(self, env: dict[str, Any], check: Callable, rule_id: str, message: str) -> 'GuardBuilder':
        """Add environment-aware guard"""
        self.guards.append(environment_aware_guard(env, check, rule_id, message))
        return self

    def with_window(self, size: int, aggregate: Callable[[list[Ctx]], bool],
                    rule_id: str, message: str) -> 'GuardBuilder':
        """Add windowed guard"""
        self.guards.append(windowed_guard(size, aggregate, rule_id, message))
        return self

    def promote_tier(self, target_tier: str) -> 'GuardBuilder':
        """Promote all guards to target tier"""
        if target_tier == "T1":
            self.guards = [promote_to_t1(g) for g in self.guards]
        elif target_tier == "T2":
            self.guards = [promote_to_t2(g) for g in self.guards]
        return self

    def to_permissive_mode(self) -> 'GuardBuilder':
        """Convert all guards to permissive mode"""
        self.guards = [to_permissive(g) for g in self.guards]
        return self

    def to_blocking_mode(self) -> 'GuardBuilder':
        """Convert all guards to blocking mode"""
        self.guards = [to_blocking(g) for g in self.guards]
        return self

    def with_timeout(self, timeout_ms: float) -> 'GuardBuilder':
        """Add timeout to all guards"""
        self.guards = [with_timeout(g, timeout_ms) for g in self.guards]
        return self

    def with_retry(self, max_retries: int, backoff_ms: float = 100.0) -> 'GuardBuilder':
        """Add retry logic to all guards"""
        self.guards = [with_retry(g, max_retries, backoff_ms) for g in self.guards]
        return self

    def build(self, composition: str = "sequence") -> Guard:
        """
        Build final guard from composition

        Args:
            composition: Type of composition ("sequence", "parallel", "any")

        Returns:
            Composed guard
        """
        if not self.guards:
            async def empty(ctx: Ctx) -> Either:
                return Right_(ctx)
            return empty

        if composition == "sequence":
            return seq(*self.guards)
        elif composition == "parallel":
            return allOf(*self.guards)
        elif composition == "any":
            return anyOf(*self.guards)
        elif composition == "kleisli":
            return kleisli_chain(*self.guards)
        else:
            raise ValueError(f"Unknown composition type: {composition}")


# Fluent DSL functions

def orchestrate() -> GuardBuilder:
    """Start guard orchestration"""
    return GuardBuilder()


def flow_rule(from_pattern: str, to_pattern: str) -> 'FlowRuleBuilder':
    """Create flow-based rule builder"""
    return FlowRuleBuilder(from_pattern, to_pattern)


@dataclass
class FlowRuleBuilder:
    """Builder for flow-based rules"""
    from_pattern: str
    to_pattern: str
    predicate: Callable[[Any, Any], bool] | None = None
    rule_id: str = "flow_rule"
    message: str = "Flow violation detected"

    def where(self, predicate: Callable[[Any, Any], bool]) -> 'FlowRuleBuilder':
        """Add predicate to flow rule"""
        self.predicate = predicate
        return self

    def with_id(self, rule_id: str) -> 'FlowRuleBuilder':
        """Set rule ID"""
        self.rule_id = rule_id
        return self

    def with_message(self, message: str) -> 'FlowRuleBuilder':
        """Set message"""
        self.message = message
        return self

    def build(self) -> Guard:
        """Build flow guard"""
        if not self.predicate:
            raise ValueError("Flow rule requires predicate")

        return flow_guard(
            self.from_pattern,
            self.to_pattern,
            self.predicate,
            self.rule_id,
            self.message
        )


def temporal_rule() -> 'TemporalRuleBuilder':
    """Create temporal rule builder"""
    return TemporalRuleBuilder()


@dataclass
class TemporalRuleBuilder:
    """Builder for temporal rules"""
    chain: TemporalChain = field(default_factory=TemporalChain)
    rule_type: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def detect_retry_loops(self, max_retries: int, window: timedelta, call_type: str) -> 'TemporalRuleBuilder':
        """Configure retry loop detection"""
        self.rule_type = "retry_loop"
        self.params = {
            "max_retries": max_retries,
            "window": window,
            "call_type": call_type
        }
        return self

    def detect_circular(self) -> 'TemporalRuleBuilder':
        """Configure circular dependency detection"""
        self.rule_type = "circular"
        return self

    def rate_limit(self, event_type: str, max_count: int, window: timedelta) -> 'TemporalRuleBuilder':
        """Configure rate limiting"""
        self.rule_type = "rate_limit"
        self.params = {
            "event_type": event_type,
            "max_count": max_count,
            "window": window
        }
        return self

    def build(self) -> Guard:
        """Build temporal guard"""
        if self.rule_type == "retry_loop":
            return detect_retry_loop(
                self.chain,
                self.params["max_retries"],
                self.params["window"],
                self.params["call_type"]
            )
        elif self.rule_type == "circular":
            return detect_circular_dependency(self.chain)
        elif self.rule_type == "rate_limit":
            return enforce_rate_limit(
                self.chain,
                self.params["event_type"],
                self.params["max_count"],
                self.params["window"]
            )
        else:
            raise ValueError(f"Unknown temporal rule type: {self.rule_type}")


# Example sophisticated compositions

def sophisticated_pii_guard() -> Guard:
    """
    Example: Sophisticated PII detection with flow tracking
    """
    from .optics import path_lens

    return (orchestrate()
            .with_flow_tracking(
                from_pattern="input",
                to_pattern="external_api",
                predicate=lambda inp, out: "email" in str(inp).lower(),
                rule_id="pii.email_leak",
                message="Email detected flowing to external API"
            )
            .with_lens(
                path_lens("messages[0].content"),
                lambda content: content.replace("@", "[at]")
            )
            .promote_tier("T1")
            .with_timeout(50.0)
            .build("sequence"))


def sophisticated_rate_limiter() -> Guard:
    """
    Example: Sophisticated rate limiting with retry detection
    """
    return (orchestrate()
            .with_temporal_tracking()
            .rate_limit("api_call", 10, timedelta(seconds=60))
            .detect_retry_loops(3, timedelta(seconds=30), "api_call")
            .detect_circular_deps()
            .with_timeout(100.0)
            .to_blocking_mode()
            .build("sequence"))


def sophisticated_tool_guard() -> Guard:
    """
    Example: Sophisticated tool enforcement with history
    """
    def check_tool_history(comonad):
        # Check if tool was called too frequently
        recent = comonad.get_history(5)
        tool_calls = [ctx for ctx in recent if ctx.get("phase") == "tool_call"]
        return len(tool_calls) < 3

    return (orchestrate()
            .with_history(
                check=check_tool_history,
                rule_id="tool.excessive_calls",
                message="Tool called too frequently",
                max_history=10
            )
            .with_flow_tracking(
                from_pattern="tool_output",
                to_pattern="external_send",
                predicate=lambda out, send: "sensitive" in str(out).lower(),
                rule_id="tool.data_leak",
                message="Sensitive tool output flowing to external system"
            )
            .promote_tier("T2")
            .with_retry(2, backoff_ms=200.0)
            .build("sequence"))

