"""
Toxicity Guard Implementations

Implements guards for detecting toxic, harmful, or inappropriate content.
"""

import re
from typing import Literal

from heimdall import register_factory
from heimdall.types import Ctx, Either, Left_, Right_, Violation

# Common toxic/harmful patterns
PROFANITY_PATTERNS = [
    r"\b(?:fuck|shit|damn|hell|bitch|asshole|cunt|whore|slut)\b",
    r"\b(?:fucking|shitting|damned|hellish|bitchy|assholish)\b",
]

HARASSMENT_PATTERNS = [
    r"\b(?:kill yourself|kys|hang yourself|jump off|end yourself)\b",
    r"\b(?:you should die|you deserve to die|i hope you die)\b",
    r"\b(?:stupid|idiot|moron|retard|dumbass|fool)\b",
]

DISCRIMINATORY_PATTERNS = [
    r"\b(?:nigger|nigga|chink|gook|wetback|spic|kike|heeb)\b",
    r"\b(?:faggot|dyke|tranny|shemale|homo|lesbo)\b",
]

THREAT_PATTERNS = [
    r"\b(?:i will kill|i'll kill|i will murder|i'll murder)\b",
    r"\b(?:i will hurt|i'll hurt|i will beat|i'll beat)\b",
    r"\b(?:threat|threatening|intimidate|intimidation)\b",
]


def compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    """Compile list of regex patterns"""
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def count_pattern_matches(text: str, patterns: list[re.Pattern]) -> int:
    """Count total matches across all patterns"""
    if not isinstance(text, str):
        return 0
    return sum(len(pattern.findall(text)) for pattern in patterns)


@register_factory("toxicity.detect", tier="T1", description="Pattern-based toxicity detection", performance_budget_ms=5.0)
def toxicity_detect(
    categories: list[str] = None,
    threshold: float = 0.5,
    severity: Literal["low", "med", "high", "critical"] = "high"
):
    """
    Detect toxic content without blocking

    Args:
        categories: List of toxicity categories to detect (profanity, harassment, discriminatory, threats)
        threshold: Score threshold for detection (0.0 to 1.0)
        severity: Severity level for violations

    Returns:
        Guard that detects toxic content
    """
    if categories is None:
        categories = ["profanity", "harassment", "discriminatory", "threats"]

    # Compile patterns for each category
    pattern_groups = {
        "profanity": compile_patterns(PROFANITY_PATTERNS),
        "harassment": compile_patterns(HARASSMENT_PATTERNS),
        "discriminatory": compile_patterns(DISCRIMINATORY_PATTERNS),
        "threats": compile_patterns(THREAT_PATTERNS),
    }

    # Category weights
    category_weights = {
        "profanity": 0.2,
        "harassment": 0.4,
        "discriminatory": 0.6,
        "threats": 0.8,
    }

    def calculate_toxicity_score(ctx):
        text = ctx.get("output", "")
        if not isinstance(text, str):
            return 0.0

        total_score = 0.0
        for category in categories:
            if category not in pattern_groups:
                continue

            patterns = pattern_groups[category]
            matches = count_pattern_matches(text, patterns)

            if matches > 0:
                weight = category_weights.get(category, 0.3)
                category_score = min(matches * weight, 1.0)
                total_score += category_score

        # Normalize total score
        return min(total_score, 1.0)

    async def check_toxicity(ctx: Ctx) -> Either:
        score = calculate_toxicity_score(ctx)
        if score >= threshold:
            return Left_([Violation(
                rule_id="toxicity.detect",
                severity=severity,
                message=f"Toxic content detected (score: {score:.2f})",
                score=score
            )])
        return Right_(ctx)

    return check_toxicity


@register_factory("toxicity.block", tier="T1", description="Pattern-based toxicity blocking", performance_budget_ms=5.0)
def toxicity_block(
    categories: list[str] = None,
    threshold: float = 0.3,
    severity: Literal["low", "med", "high", "critical"] = "critical"
):
    """
    Block toxic content based on detection

    Args:
        categories: List of toxicity categories to block
        threshold: Score threshold for blocking (0.0 to 1.0)
        severity: Severity level for violations

    Returns:
        Guard that blocks toxic content
    """
    # Use the same detection logic but with different default threshold
    return toxicity_detect(categories=categories, threshold=threshold, severity=severity)
