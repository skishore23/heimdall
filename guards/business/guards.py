"""
Business Guard Implementations

Guards for business compliance scenarios including financial services,
competitor protection, and professional liability.
"""

import re
from typing import Any, Literal

from heimdall import register_factory
from heimdall.author import G
from heimdall.types import Ctx, Either, Guard, Left_, Right_, Violation


def extract_text(ctx: dict[str, Any]) -> str:
    """Extract text from context (output or last message)"""
    text = ctx.get("output", "")

    # Fallback to extracting from messages if no focused content
    if not text and "messages" in ctx:
        messages = ctx.get("messages", [])
        if isinstance(messages, list) and messages:
            text = messages[-1].get("content", "") if isinstance(messages[-1], dict) else str(messages[-1])

    return text if isinstance(text, str) else ""


@register_factory("business.financial_compliance", tier="T1", description="Financial services compliance and disclaimer enforcement", performance_budget_ms=15.0)
def financial_services_compliance(
    company_profile: dict[str, Any] = None,
    require_disclaimers: bool = True,
    block_guarantees: bool = True,
    severity: Literal["low", "med", "high", "critical"] = "high"
):
    """
    Enforce financial services compliance rules

    Args:
        company_profile: Company profile configuration
        require_disclaimers: Require financial disclaimers in responses
        block_guarantees: Block guaranteed return promises
        severity: Severity level for violations

    Returns:
        Guard that enforces financial compliance
    """
    if company_profile is None:
        company_profile = {"industry": "financial_services", "compliance_level": "strict"}

    # Financial advice patterns
    advice_patterns = [
        r"\b(?:what|which) (?:stocks?|shares?|bonds?|securities?|investments?) (?:should|to|do) (?:I|we) (?:buy|purchase|invest in)\b",
        r"\b(?:recommend|suggest) (?:stocks?|investments?|securities?)\b",
        r"\b(?:buy|sell|invest in|purchase)\s+\w+\s+(?:stocks?|shares?|bonds?)\b",  # Matches "buy Apple stock"
        r"\b(?:guaranteed|promise|ensure) (?:returns?|profits?|gains?)\b",
        r"\b(?:risk-free|no risk|safe) investment\b",
        r"\b(?:best|good|top) (?:stocks?|investments?) (?:to buy|for)\b",
        r"\bshould I invest in\b",
        r"\b(?:should|will) (?:buy|purchase)\s+\w+\s+(?:stock|shares?)\b",  # Catches "should buy Apple stock"
    ]

    # Required disclaimer patterns
    disclaimer_patterns = [
        r"\b(?:not a financial advisor|not financial advice|consult.*financial advisor)\b",
        r"\b(?:do your own research|DYOR|past performance)\b",
        r"\b(?:risk tolerance|investment goals|professional advice)\b"
    ]

    compiled_advice = [re.compile(p, re.IGNORECASE) for p in advice_patterns]
    compiled_disclaimers = [re.compile(p, re.IGNORECASE) for p in disclaimer_patterns]

    async def check_compliance(ctx: Ctx) -> Either:
        text = extract_text(ctx)
        if not text.strip():
            return Right_(ctx)

        # Check for financial advice patterns
        advice_matches = sum(1 for pattern in compiled_advice if pattern.search(text))

        if advice_matches > 0:
            phase = ctx.get("phase", "")

            # If phase is missing or input, block direct financial advice requests
            if phase == "" or phase == "input":
                return Left_([Violation(
                    rule_id="business.financial_compliance",
                    severity=severity,
                    message="Direct financial advice request blocked"
                )])

            # For output, check for required disclaimers
            elif phase == "output" and require_disclaimers:
                disclaimer_matches = sum(1 for pattern in compiled_disclaimers if pattern.search(text))
                if disclaimer_matches == 0:
                    return Left_([Violation(
                        rule_id="business.financial_compliance",
                        severity=severity,
                        message="Financial advice without required disclaimers"
                    )])

        return Right_(ctx)

    return check_compliance


@register_factory("business.competitor_protection", tier="T0", description="Block mentions of competitor products/services", performance_budget_ms=3.0)
def competitor_protection(
    competitors: list[str] = None,
    block_recommendations: bool = True,
    severity: Literal["low", "med", "high", "critical"] = "med"
):
    """
    Block mentions of competitor products or services

    Args:
        competitors: List of competitor names to block
        block_recommendations: Block recommendations of competitors
        severity: Severity level for violations

    Returns:
        Guard that blocks competitor mentions
    """
    if competitors is None:
        competitors = [
            "Vanguard", "Fidelity", "Charles Schwab", "E*TRADE",
            "TD Ameritrade", "Robinhood", "Wealthfront", "Betterment"
        ]

    # Create patterns for competitor detection
    competitor_patterns = []
    for competitor in competitors:
        competitor_patterns.append(rf"\b{re.escape(competitor)}\b")
        if block_recommendations:
            competitor_patterns.append(rf"\b(?:try|use|consider|recommend)\s+{re.escape(competitor)}\b")

    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in competitor_patterns]

    def no_competitor_mentions(ctx):
        text = extract_text(ctx)
        if not text:
            return True

        # Check for competitor mentions
        for pattern in compiled_patterns:
            if pattern.search(text):
                return False

        return True

    return G("business.competitor_protection", severity=severity).require(
        no_competitor_mentions,
        "Competitor mention detected"
    ).build()


@register_factory("business.professional_liability", tier="T1", description="Block professional advice that could create liability", performance_budget_ms=8.0)
def professional_liability_protection(
    blocked_advice_types: list[str] = None,
    severity: Literal["low", "med", "high", "critical"] = "high"
):
    """
    Block professional advice that could create liability

    Args:
        blocked_advice_types: Types of professional advice to block
        severity: Severity level for violations

    Returns:
        Guard that blocks professional advice
    """
    if blocked_advice_types is None:
        blocked_advice_types = ["legal", "medical", "tax", "accounting"]

    # Professional advice patterns
    advice_patterns = {
        "legal": [
            r"\b(?:you should|I recommend|my advice is to)\s+(?:sue|file a lawsuit|take legal action)\b",
            r"\b(?:this is|that is|it is)\s+(?:clearly\s+)?(?:legal|illegal|against the law)\b",
            r"\b(?:you have a case|strong legal case|grounds for lawsuit)\b",
        ],
        "medical": [
            r"\b(?:you should|I recommend|my advice is to)\s+(?:take|stop taking|increase|decrease)\s+(?:medication|pills|drugs)\b",
            r"\b(?:this is|that is|it is)\s+(?:a symptom of|caused by|due to)\b",
            r"\b(?:you have|you might have|could be)\s+(?:cancer|diabetes|heart disease)\b"
        ],
        "tax": [
            r"\b(?:you should|I recommend|my advice is to)\s+(?:deduct|claim|file|report)\b",
            r"\b(?:this is|that is|it is)\s+(?:tax deductible|taxable|tax-free)\b",
            r"\b(?:you can|you should)\s+(?:avoid|reduce|minimize)\s+(?:taxes|tax liability)\b"
        ]
    }

    # Compile patterns for requested advice types
    compiled_patterns = {}
    for advice_type in blocked_advice_types:
        if advice_type in advice_patterns:
            compiled_patterns[advice_type] = [
                re.compile(p, re.IGNORECASE) for p in advice_patterns[advice_type]
            ]

    def no_professional_advice(ctx):
        text = extract_text(ctx)
        if not text:
            return True

        # Check for professional advice patterns
        for _advice_type, patterns in compiled_patterns.items():
            matches = sum(1 for pattern in patterns if pattern.search(text))
            if matches > 0:
                return False

        return True

    return G("business.professional_liability", severity=severity).require(
        no_professional_advice,
        "Professional advice detected - potential liability risk"
    ).build()


@register_factory("business.brand_tone", tier="T0", description="Enforce professional brand tone and language", performance_budget_ms=5.0)
def brand_tone_enforcement(
    unprofessional_patterns: list[str] = None,
    required_tone: str = "professional",
    severity: Literal["low", "med", "high", "critical"] = "med"
):
    """
    Enforce professional brand tone and language

    Args:
        unprofessional_patterns: Patterns that indicate unprofessional language
        required_tone: Required tone (professional, casual, formal)
        severity: Severity level for violations

    Returns:
        Guard that enforces brand tone
    """
    if unprofessional_patterns is None:
        unprofessional_patterns = [
            r"\b(?:dude|bro|yo|hey there|sup)\b",
            r"\b(?:awesome|sick|lit|fire|dope)\b",
            r"\b(?:lol|lmao|rofl|omg|wtf)\b",
            r"[!]{2,}",  # Multiple exclamation marks
            r"[?]{2,}",  # Multiple question marks
        ]

    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in unprofessional_patterns]

    def is_professional(ctx):
        text = extract_text(ctx)
        if not text:
            return True

        # Check for unprofessional language
        for pattern in compiled_patterns:
            if pattern.search(text):
                return False

        return True

    return G("business.brand_tone", severity=severity).require(
        is_professional,
        f"Unprofessional language detected (required tone: {required_tone})"
    ).build()


@register_factory("business.block_hosts", tier="T0", description="Block references to forbidden hosts", performance_budget_ms=3.0)
def block_hosts(
    blocked_hosts: list[str],
    severity: Literal["low", "med", "high", "critical"] = "high"
) -> Guard:
    compiled_patterns = [re.compile(rf"{re.escape(host)}", re.IGNORECASE) for host in blocked_hosts]

    async def run(ctx: Ctx) -> Either:
        text = extract_text(ctx)
        for pattern in compiled_patterns:
            if pattern.search(text):
                host = pattern.pattern
                return Left_([Violation(
                    rule_id="business.block_hosts",
                    severity=severity,
                    message=f"Blocked host mentioned: {host}",
                    evidence={"blocked_host": host, "text": text}
                )])
        return Right_(ctx)

    return run
