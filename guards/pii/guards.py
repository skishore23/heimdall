"""
PII Guard Implementations

Implements guards for Personal Identifiable Information detection and redaction.
"""

import re
from typing import Literal

from heimdall import register_factory
from heimdall.author import G

# Core PII patterns
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
PHONE_PATTERN = r"(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})"
CREDIT_CARD_PATTERN = r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
SSN_PATTERN = r"\b\d{3}-\d{2}-\d{4}\b"
IP_ADDRESS_PATTERN = r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"

# Enhanced PII patterns
BANK_ACCOUNT_PATTERN = r"\b\d{8,17}\b"
ROUTING_NUMBER_PATTERN = r"\b\d{9}\b"
IBAN_PATTERN = r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b"
PASSPORT_PATTERN = r"\b[A-Z]{1,2}\d{6,9}\b"
DRIVERS_LICENSE_PATTERN = r"\b[A-Z]\d{7,8}\b"
TAX_ID_PATTERN = r"\b\d{2}-?\d{7}\b"
MEDICAL_RECORD_PATTERN = r"\bMRN[-:\s]?\d{6,10}\b"
API_KEY_PATTERN = r"\b[Aa][Pp][Ii][-_]?[Kk][Ee][Yy][-_:=\s]*[A-Za-z0-9+/]{20,}\b"
JWT_PATTERN = r"\beyJ[A-Za-z0-9+/=]+\.[A-Za-z0-9+/=]+\.[A-Za-z0-9+/=]*\b"
NAME_PATTERN = r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\b"
ADDRESS_PATTERN = r"\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Place|Pl)\b"
ZIP_CODE_PATTERN = r"\b\d{5}(?:-\d{4})?\b"
DATE_OF_BIRTH_PATTERN = r"\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b"
MAC_ADDRESS_PATTERN = r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"
IPV6_PATTERN = r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"

# Compiled patterns for performance
PATTERNS = {
    # Core PII
    "EMAIL": re.compile(EMAIL_PATTERN, re.IGNORECASE),
    "PHONE": re.compile(PHONE_PATTERN),
    "CREDIT_CARD": re.compile(CREDIT_CARD_PATTERN),
    "SSN": re.compile(SSN_PATTERN),
    "IP_ADDRESS": re.compile(IP_ADDRESS_PATTERN),

    # Enhanced PII
    "BANK_ACCOUNT": re.compile(BANK_ACCOUNT_PATTERN),
    "ROUTING_NUMBER": re.compile(ROUTING_NUMBER_PATTERN),
    "IBAN": re.compile(IBAN_PATTERN, re.IGNORECASE),
    "PASSPORT": re.compile(PASSPORT_PATTERN),
    "DRIVERS_LICENSE": re.compile(DRIVERS_LICENSE_PATTERN),
    "TAX_ID": re.compile(TAX_ID_PATTERN),
    "MEDICAL_RECORD": re.compile(MEDICAL_RECORD_PATTERN, re.IGNORECASE),
    "API_KEY": re.compile(API_KEY_PATTERN),
    "JWT": re.compile(JWT_PATTERN),
    "NAME": re.compile(NAME_PATTERN),
    "ADDRESS": re.compile(ADDRESS_PATTERN, re.IGNORECASE),
    "ZIP_CODE": re.compile(ZIP_CODE_PATTERN),
    "DATE_OF_BIRTH": re.compile(DATE_OF_BIRTH_PATTERN),
    "MAC_ADDRESS": re.compile(MAC_ADDRESS_PATTERN, re.IGNORECASE),
    "IPV6": re.compile(IPV6_PATTERN, re.IGNORECASE),
}

# Entity metadata for UI display
PII_ENTITY_INFO = {
    "EMAIL": {"name": "Email Address", "category": "Contact", "risk": "Medium"},
    "PHONE": {"name": "Phone Number", "category": "Contact", "risk": "Medium"},
    "SSN": {"name": "Social Security Number", "category": "Government ID", "risk": "High"},
    "CREDIT_CARD": {"name": "Credit Card", "category": "Financial", "risk": "High"},
    "BANK_ACCOUNT": {"name": "Bank Account", "category": "Financial", "risk": "High"},
    "ROUTING_NUMBER": {"name": "Routing Number", "category": "Financial", "risk": "High"},
    "IBAN": {"name": "IBAN", "category": "Financial", "risk": "High"},
    "PASSPORT": {"name": "Passport Number", "category": "Government ID", "risk": "High"},
    "DRIVERS_LICENSE": {"name": "Driver's License", "category": "Government ID", "risk": "High"},
    "TAX_ID": {"name": "Tax ID (EIN/TIN)", "category": "Government ID", "risk": "High"},
    "MEDICAL_RECORD": {"name": "Medical Record Number", "category": "Healthcare", "risk": "High"},
    "IP_ADDRESS": {"name": "IP Address", "category": "Technical", "risk": "Low"},
    "IPV6": {"name": "IPv6 Address", "category": "Technical", "risk": "Low"},
    "MAC_ADDRESS": {"name": "MAC Address", "category": "Technical", "risk": "Low"},
    "API_KEY": {"name": "API Key", "category": "Credentials", "risk": "High"},
    "JWT": {"name": "JWT Token", "category": "Credentials", "risk": "High"},
    "NAME": {"name": "Full Name", "category": "Personal", "risk": "Medium"},
    "ADDRESS": {"name": "Street Address", "category": "Personal", "risk": "Medium"},
    "ZIP_CODE": {"name": "ZIP Code", "category": "Personal", "risk": "Low"},
    "DATE_OF_BIRTH": {"name": "Date of Birth", "category": "Personal", "risk": "High"},
}


def has_pii_type(text: str, pii_type: str) -> bool:
    """Check if text contains a specific PII type"""
    if not isinstance(text, str) or pii_type not in PATTERNS:
        return False
    return PATTERNS[pii_type].search(text) is not None


def redact_pii_type(text: str, pii_type: str, mode: str = "mask") -> str:
    """Redact a specific PII type from text"""
    if not isinstance(text, str) or pii_type not in PATTERNS:
        return text

    pattern = PATTERNS[pii_type]
    if mode == "mask":
        replacement = f"[{pii_type}]"
    else:  # mode == "remove"
        replacement = ""

    return pattern.sub(replacement, text)


@register_factory("pii.redact", tier="T0", description="Fast PII redaction using regex patterns", performance_budget_ms=3.0)
def pii_redact(types: list[str], mode: Literal["mask", "remove"] = "mask"):
    """
    Redact PII from text

    Args:
        types: List of PII types to redact (EMAIL, PHONE, CREDIT_CARD, SSN, IP_ADDRESS)
        mode: Redaction mode - "mask" replaces with [TYPE], "remove" removes entirely

    Returns:
        Guard that redacts specified PII types
    """
    def transform_text(ctx):
        text = ctx.get("output", "")
        if not isinstance(text, str):
            return ctx

        redacted_text = text
        for pii_type in types:
            redacted_text = redact_pii_type(redacted_text, pii_type, mode)

        return {**ctx, "output": redacted_text}

    # Redaction always transforms and allows (doesn't block)
    # We use require with a True condition but transform the context
    guard = G("pii.redact").require(
        lambda ctx: True,  # Always pass
        "PII redacted"
    ).build()

    # Wrap to apply transformation
    async def run(ctx):
        transformed = transform_text(ctx)
        return await guard(transformed)

    return run


@register_factory("pii.detect", tier="T0", description="Fast PII detection using regex patterns", performance_budget_ms=2.0)
def pii_detect(
    types: list[str],
    threshold: float = 0.0,
    severity: Literal["low", "med", "high", "critical"] = "high"
):
    """
    Detect PII in text without redacting

    Args:
        types: List of PII types to detect
        threshold: Minimum number of matches to trigger violation
        severity: Severity level for violations

    Returns:
        Guard that detects PII and reports violations
    """
    def check_pii(ctx):
        text = ctx.get("output", "")
        if not isinstance(text, str):
            return True  # No PII if not text

        # Count total matches across all types
        total_matches = sum(
            len(PATTERNS[pii_type].findall(text))
            for pii_type in types
            if pii_type in PATTERNS
        )

        return total_matches < threshold

    message_parts = [f"Detected PII types: {', '.join(types)}"]
    if threshold > 0:
        message_parts.append(f"(threshold: {threshold})")

    return G("pii.detect", severity=severity).forbid(
        lambda ctx: not check_pii(ctx),
        " ".join(message_parts)
    ).build()
