"""
Advanced SDK Extensions for Sophisticated Guard Composition

High-level API for using advanced category theory features.
Provides simple interface to complex compositions.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from .comonad import environment_aware_guard, history_aware_guard
from .flow import FlowContext, check_data_flow, create_flow_context
from .kleisli import chain, lift
from .natural import promote_to_t1, promote_to_t2, with_retry, with_timeout
from .optics import path_lens
from .orchestrate import (
    FlowRuleBuilder,
    GuardBuilder,
    TemporalRuleBuilder,
    flow_rule,
    orchestrate,
    temporal_rule,
)
from .temporal import TemporalChain, TemporalEvent
from .types import Ctx, Guard


class AdvancedGuardSDK:
    """
    High-level SDK for sophisticated guard composition
    Simplifies usage of category theory features
    """

    def __init__(self):
        self.temporal_chain = TemporalChain()
        self.flow_contexts: dict[str, FlowContext] = {}

    def builder(self) -> GuardBuilder:
        """Create new guard builder"""
        return orchestrate()

    def flow_builder(self, from_pattern: str, to_pattern: str) -> FlowRuleBuilder:
        """Create flow rule builder"""
        return flow_rule(from_pattern, to_pattern)

    def temporal_builder(self) -> TemporalRuleBuilder:
        """Create temporal rule builder"""
        builder = temporal_rule()
        builder.chain = self.temporal_chain
        return builder

    def create_flow_context(self, ctx: Ctx, flow_id: str) -> FlowContext:
        """Create and track flow context"""
        flow_ctx = create_flow_context(ctx, flow_id)
        self.flow_contexts[flow_id] = flow_ctx
        return flow_ctx

    def track_event(self, event: TemporalEvent) -> None:
        """Track temporal event"""
        self.temporal_chain.add_event(event)

    def check_flow(
        self,
        flow_id: str,
        from_pattern: str,
        to_pattern: str,
        predicate: Callable[[Any, Any], bool] | None = None
    ) -> bool:
        """Check if data flows between patterns"""
        if flow_id not in self.flow_contexts:
            return False

        return check_data_flow(
            self.flow_contexts[flow_id],
            from_pattern,
            to_pattern,
            predicate
        )

    def compose_kleisli(self, *guards: Guard) -> Guard:
        """Compose guards using Kleisli composition"""
        return chain(*guards)

    def lens_transform(self, path: str, transform: Callable[[Any], Any]) -> Guard:
        """Create lens-based transformation guard"""
        from .optics import lens_guard
        lens = path_lens(path)
        return lens_guard(lens, transform)

    def history_guard(
        self,
        check: Callable,
        rule_id: str,
        message: str,
        max_history: int = 10
    ) -> Guard:
        """Create history-aware guard"""
        return history_aware_guard(check, rule_id, message, max_history)

    def environment_guard(
        self,
        environment: dict[str, Any],
        check: Callable,
        rule_id: str,
        message: str
    ) -> Guard:
        """Create environment-aware guard"""
        return environment_aware_guard(environment, check, rule_id, message)

    def tiered_guard(self, guard: Guard, tier: str) -> Guard:
        """Promote guard to specific tier"""
        if tier == "T1":
            return promote_to_t1(guard)
        elif tier == "T2":
            return promote_to_t2(guard)
        return guard

    def resilient_guard(
        self,
        guard: Guard,
        timeout_ms: float = 1000.0,
        max_retries: int = 2,
        backoff_ms: float = 100.0
    ) -> Guard:
        """Create resilient guard with timeout and retry"""
        return with_retry(
            with_timeout(guard, timeout_ms),
            max_retries,
            backoff_ms
        )


# Convenience functions

def pii_flow_guard(
    pii_types: list[str],
    allowed_destinations: list[str]
) -> Guard:
    """
    Create guard that prevents PII from flowing to unauthorized destinations

    Args:
        pii_types: Types of PII to track (email, ssn, etc.)
        allowed_destinations: Allowed destination patterns

    Returns:
        Flow-based PII guard
    """
    def has_pii(data: Any) -> bool:
        data_str = str(data).lower()
        return any(pii_type in data_str for pii_type in pii_types)

    def is_allowed_dest(dest: Any) -> bool:
        dest_str = str(dest).lower()
        return any(allowed in dest_str for allowed in allowed_destinations)

    def check_flow(source: Any, dest: Any) -> bool:
        # If source has PII and dest is not allowed, block
        if has_pii(source) and not is_allowed_dest(dest):
            return False
        return True

    return (flow_rule("input", "external_call")
            .where(lambda src, dst: not check_flow(src, dst))
            .with_id("pii.unauthorized_flow")
            .with_message("PII detected flowing to unauthorized destination")
            .build())


def retry_prevention_guard(
    max_retries: int = 3,
    window_seconds: float = 30.0,
    call_types: list[str] | None = None
) -> Guard:
    """
    Create guard that prevents excessive retry loops

    Args:
        max_retries: Maximum retries allowed
        window_seconds: Time window in seconds
        call_types: Types of calls to monitor

    Returns:
        Retry prevention guard
    """
    if call_types is None:
        call_types = ["tool_call", "api_call"]

    builder = (orchestrate()
               .with_temporal_tracking())

    for call_type in call_types:
        builder = builder.detect_retry_loops(
            max_retries,
            timedelta(seconds=window_seconds),
            call_type
        )

    return builder.build("sequence")


def circular_dependency_guard() -> Guard:
    """
    Create guard that detects circular call dependencies

    Returns:
        Circular dependency detection guard
    """
    return (orchestrate()
            .with_temporal_tracking()
            .detect_circular_deps()
            .with_timeout(50.0)
            .build())


def rate_limit_guard(
    events_per_window: int,
    window_seconds: float,
    event_types: list[str] | None = None
) -> Guard:
    """
    Create rate limiting guard

    Args:
        events_per_window: Maximum events allowed in window
        window_seconds: Time window in seconds
        event_types: Types of events to rate limit

    Returns:
        Rate limiting guard
    """
    if event_types is None:
        event_types = ["api_call"]

    builder = (orchestrate()
               .with_temporal_tracking())

    for event_type in event_types:
        builder = builder.rate_limit(
            event_type,
            events_per_window,
            timedelta(seconds=window_seconds)
        )

    return builder.build("parallel")


def sophisticated_tool_enforcement_guard(
    allowed_tools: list[str],
    max_calls_per_window: int = 5,
    window_seconds: float = 60.0,
    check_output_flow: bool = True
) -> Guard:
    """
    Create sophisticated tool enforcement guard

    Args:
        allowed_tools: List of allowed tool names
        max_calls_per_window: Maximum calls per time window
        window_seconds: Time window in seconds
        check_output_flow: Whether to check output data flow

    Returns:
        Sophisticated tool guard
    """
    def check_allowed_tool(ctx: Ctx) -> bool:
        tool_name = ctx.get("function_name", "")
        return tool_name in allowed_tools

    def check_call_frequency(comonad):
        recent = comonad.get_history(10)
        tool_calls = [c for c in recent if c.get("phase") == "tool_call"]
        return len(tool_calls) <= max_calls_per_window

    builder = (orchestrate()
               .when_condition(
                   lambda ctx: ctx.get("phase") == "tool_call",
                   lift(lambda ctx: ctx if check_allowed_tool(ctx) else None)
               )
               .with_history(
                   check=check_call_frequency,
                   rule_id="tool.excessive_calls",
                   message=f"Tool called more than {max_calls_per_window} times",
                   max_history=10
               )
               .rate_limit(
                   "tool_call",
                   max_calls_per_window,
                   timedelta(seconds=window_seconds)
               ))

    if check_output_flow:
        builder = builder.with_flow_tracking(
            from_pattern="tool_output",
            to_pattern="external_send",
            predicate=lambda out, dest: "sensitive" not in str(out).lower(),
            rule_id="tool.sensitive_output_leak",
            message="Sensitive tool output flowing to external system"
        )

    return builder.promote_tier("T1").with_timeout(100.0).build("sequence")


def content_filtering_pipeline(
    pii_types: list[str],
    toxicity_threshold: float = 0.7,
    max_retries: int = 2
) -> Guard:
    """
    Create sophisticated content filtering pipeline

    Args:
        pii_types: Types of PII to detect
        toxicity_threshold: Threshold for toxicity
        max_retries: Maximum retries for guards

    Returns:
        Content filtering pipeline guard
    """
    # This would integrate with actual PII and toxicity detection
    # For now, showing the composition pattern

    return (orchestrate()
            .with_lens(
                path_lens("output.text"),
                lambda text: text  # Would apply PII redaction
            )
            .with_flow_tracking(
                from_pattern="input",
                to_pattern="output",
                predicate=lambda inp, out: True,  # Would check PII flow
                rule_id="content.pii_leak",
                message="PII detected in output"
            )
            .promote_tier("T2")
            .with_retry(max_retries)
            .with_timeout(500.0)
            .build("sequence"))


# Export singleton SDK instance
advanced_sdk = AdvancedGuardSDK()

