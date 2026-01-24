"""
Politics Guard Implementations

Implements guards for political content detection and blocking.
"""

import re
from typing import Literal

# Use standard re module for compatibility
regex_engine = re

from heimdall import Ctx, Either, Guard, Left_, Right_, Violation, register_factory


@register_factory("politics.block", tier="T0", description="Fast pattern-based political content blocking", performance_budget_ms=3.0)
def politics_block(
    patterns_strong: list[str],
    patterns_weak: list[str] = None,
    allow: list[str] = None,
    threshold: float = 0.75,
    severity: Literal["low", "med", "high", "critical"] = "high"
) -> Guard:
    """
    Block political content based on pattern matching

    Args:
        patterns_strong: Strong indicators of political content (high weight)
        patterns_weak: Weak indicators of political content (low weight)
        allow: Patterns that should be allowed even if they match political patterns
        threshold: Score threshold for blocking (0.0 to 1.0)
        severity: Severity level for violations

    Returns:
        Guard that blocks political content
    """
    if patterns_weak is None:
        patterns_weak = []
    if allow is None:
        allow = []

    # Compile patterns for performance
    strong_patterns = [regex_engine.compile(p, regex_engine.IGNORECASE) for p in patterns_strong]
    weak_patterns = [regex_engine.compile(p, regex_engine.IGNORECASE) for p in patterns_weak]
    allow_patterns = [regex_engine.compile(p, regex_engine.IGNORECASE) for p in allow]

    async def run(ctx: Ctx) -> Either:
        # Get text from focused content (via JSONPath lens) or fallback to output
        text = ctx.get("output", "")

        # Debug: Check what we actually received
        if not text:
            # This might be a direct message context
            if "content" in ctx:
                text = ctx.get("content", "")
            elif "messages" in ctx:
                messages = ctx.get("messages", [])
                if isinstance(messages, list) and messages:
                    # Get the last message content
                    last_msg = messages[-1]
                    text = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)

        if not isinstance(text, str):
            return Right_(ctx)

        # Check allow patterns first
        for allow_pattern in allow_patterns:
            if allow_pattern.search(text):
                return Right_(ctx)

        # Calculate political content score
        score = 0.0

        # Strong patterns contribute more to the score
        strong_matches = sum(1 for pattern in strong_patterns if pattern.search(text))
        if strong_matches > 0:
            score += min(strong_matches * 0.4, 0.8)  # Cap strong pattern contribution

        # Weak patterns contribute less to the score
        weak_matches = sum(1 for pattern in weak_patterns if pattern.search(text))
        if weak_matches > 0:
            score += min(weak_matches * 0.1, 0.2)  # Cap weak pattern contribution

        # Normalize score
        score = min(score, 1.0)

        if score >= threshold:
            return Left_([Violation(
                rule_id="politics.block",
                severity=severity,
                message=f"Political content detected (score: {score:.2f})",
                score=score,
                evidence={
                    "text_analyzed": text[:100] + "..." if len(text) > 100 else text,
                    "strong_matches": strong_matches,
                    "weak_matches": weak_matches,
                    "threshold": threshold
                }
            )])

        return Right_(ctx)

    return run


@register_factory("politics.detect", tier="T0", description="Fast pattern-based political content detection", performance_budget_ms=2.0)
def politics_detect(
    patterns_strong: list[str],
    patterns_weak: list[str] = None,
    allow: list[str] = None,
    severity: Literal["low", "med", "high", "critical"] = "med"
) -> Guard:
    """
    Detect political content without blocking

    Args:
        patterns_strong: Strong indicators of political content
        patterns_weak: Weak indicators of political content
        allow: Patterns that should be allowed
        severity: Severity level for violations

    Returns:
        Guard that detects political content
    """
    if patterns_weak is None:
        patterns_weak = []
    if allow is None:
        allow = []

    # Compile patterns for performance
    strong_patterns = [regex_engine.compile(p, regex_engine.IGNORECASE) for p in patterns_strong]
    weak_patterns = [regex_engine.compile(p, regex_engine.IGNORECASE) for p in patterns_weak]
    allow_patterns = [regex_engine.compile(p, regex_engine.IGNORECASE) for p in allow]

    async def run(ctx: Ctx) -> Either:
        # Get text from focused content (via JSONPath lens) or fallback to output
        text = ctx.get("output", "")

        # Debug: Check what we actually received
        if not text:
            # This might be a direct message context
            if "content" in ctx:
                text = ctx.get("content", "")
            elif "messages" in ctx:
                messages = ctx.get("messages", [])
                if isinstance(messages, list) and messages:
                    # Get the last message content
                    last_msg = messages[-1]
                    text = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)

        if not isinstance(text, str):
            return Right_(ctx)

        # Check allow patterns first
        for allow_pattern in allow_patterns:
            if allow_pattern.search(text):
                return Right_(ctx)

        # Count matches
        strong_matches = sum(1 for pattern in strong_patterns if pattern.search(text))
        weak_matches = sum(1 for pattern in weak_patterns if pattern.search(text))

        if strong_matches > 0 or weak_matches > 0:
            score = min(strong_matches * 0.4 + weak_matches * 0.1, 1.0)

            return Left_([Violation(
                rule_id="politics.detect",
                severity=severity,
                message=f"Political content detected (strong: {strong_matches}, weak: {weak_matches})",
                score=score,
                evidence={
                    "text_analyzed": text[:100] + "..." if len(text) > 100 else text,
                    "strong_matches": strong_matches,
                    "weak_matches": weak_matches
                }
            )])

        return Right_(ctx)

    return run
