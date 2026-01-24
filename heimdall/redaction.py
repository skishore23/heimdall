"""
Redaction Utilities - Pure Functions for PII Masking

Provides composable redaction strategies for sensitive data.
All functions are pure and return new values without mutation.
"""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# === Redaction Strategy Type ===

RedactionFn = Callable[[str], tuple[str, str]]  # (text) -> (redacted_text, strategy_name)


# === Core Redaction Functions ===

def mask_email(text: str) -> tuple[str, str]:
    """Mask email addresses: user@domain.com -> u***@d***.com"""
    pattern = r'\b([a-zA-Z0-9])[a-zA-Z0-9._-]*@([a-zA-Z0-9])[a-zA-Z0-9.-]*\.[a-zA-Z]{2,}\b'

    def replace_email(match: re.Match) -> str:
        first_char = match.group(1)
        domain_char = match.group(2)
        domain_ext = match.group(0).split('.')[-1]
        return f"{first_char}***@{domain_char}***.{domain_ext}"

    redacted = re.sub(pattern, replace_email, text)
    return (redacted, "email_mask")


def mask_phone(text: str) -> tuple[str, str]:
    """Mask phone numbers: +1-234-567-8900 -> +1-***-***-8900"""
    pattern = r'(\+?\d{1,3}[-.\s]?)(\d{3})[-.\s]?(\d{3})[-.\s]?(\d{4})'

    def replace_phone(match: re.Match) -> str:
        country = match.group(1) if match.group(1) else ''
        last_four = match.group(4)
        return f"{country}***-***-{last_four}"

    redacted = re.sub(pattern, replace_phone, text)
    return (redacted, "phone_mask")


def mask_ssn(text: str) -> tuple[str, str]:
    """Mask SSN: 123-45-6789 -> ***-**-6789"""
    pattern = r'\b\d{3}-\d{2}-(\d{4})\b'

    def replace_ssn(match: re.Match) -> str:
        last_four = match.group(1)
        return f"***-**-{last_four}"

    redacted = re.sub(pattern, replace_ssn, text)
    return (redacted, "ssn_mask")


def mask_credit_card(text: str) -> tuple[str, str]:
    """Mask credit card: 1234-5678-9012-3456 -> ****-****-****-3456"""
    pattern = r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?(\d{4})\b'

    def replace_card(match: re.Match) -> str:
        last_four = match.group(1)
        return f"****-****-****-{last_four}"

    redacted = re.sub(pattern, replace_card, text)
    return (redacted, "credit_card_mask")


def hash_value(text: str) -> tuple[str, str]:
    """Hash sensitive values: sensitive -> sha256:abc123..."""
    hashed = hashlib.sha256(text.encode()).hexdigest()[:16]
    return (f"sha256:{hashed}", "hash")


def redact_full(text: str) -> tuple[str, str]:
    """Fully redact text: anything -> [REDACTED]"""
    return ("[REDACTED]", "full_redact")


# === Composite Redaction ===

def compose_redactions(*redactions: RedactionFn) -> RedactionFn:
    """
    Compose multiple redaction functions sequentially

    Args:
        *redactions: Redaction functions to apply in order

    Returns:
        Composite redaction function
    """
    def composite(text: str) -> tuple[str, str]:
        current = text
        strategies = []

        for redact_fn in redactions:
            current, strategy = redact_fn(current)
            strategies.append(strategy)

        combined_strategy = "+".join(strategies)
        return (current, combined_strategy)

    return composite


def apply_pii_redaction(text: str) -> tuple[str, str]:
    """
    Apply comprehensive PII redaction

    Masks emails, phones, SSNs, and credit cards
    """
    redaction_pipeline = compose_redactions(
        mask_email,
        mask_phone,
        mask_ssn,
        mask_credit_card
    )
    return redaction_pipeline(text)


# === Redaction Profiles ===

@dataclass(frozen=True)
class RedactionProfile:
    """Immutable redaction profile configuration"""
    name: str
    strategies: tuple[RedactionFn, ...]

    def apply(self, text: str) -> tuple[str, str]:
        """Apply all strategies in this profile"""
        redaction_fn = compose_redactions(*self.strategies)
        return redaction_fn(text)


# Predefined profiles
PROFILE_PII = RedactionProfile(
    name="pii",
    strategies=(mask_email, mask_phone, mask_ssn)
)

PROFILE_FINANCIAL = RedactionProfile(
    name="financial",
    strategies=(mask_credit_card, mask_ssn, mask_phone)
)

PROFILE_COMPREHENSIVE = RedactionProfile(
    name="comprehensive",
    strategies=(mask_email, mask_phone, mask_ssn, mask_credit_card)
)

PROFILE_HASH_ALL = RedactionProfile(
    name="hash_all",
    strategies=(hash_value,)
)


# === Context Redaction ===

def redact_at_path(ctx: dict[str, Any], path: str, redaction_fn: RedactionFn) -> dict[str, Any]:
    """
    Apply redaction at a specific path in context

    Args:
        ctx: Context dictionary
        path: Dot-separated path (e.g., "input.message")
        redaction_fn: Redaction function to apply

    Returns:
        New context with redacted value
    """
    import copy
    new_ctx = copy.deepcopy(ctx)

    # Navigate to path
    parts = path.split('.')
    current = new_ctx

    for part in parts[:-1]:
        if part not in current:
            return new_ctx  # Path doesn't exist
        current = current[part]

    # Apply redaction
    final_key = parts[-1]
    if final_key in current and isinstance(current[final_key], str):
        redacted_value, strategy = redaction_fn(current[final_key])
        current[final_key] = redacted_value

        # Store strategy metadata
        if "_redaction_metadata" not in new_ctx:
            new_ctx["_redaction_metadata"] = {}
        new_ctx["_redaction_metadata"][path] = strategy

    return new_ctx


def extract_redaction_metadata(ctx: dict[str, Any]) -> dict[str, str]:
    """Extract redaction metadata from context"""
    return ctx.get("_redaction_metadata", {})


# === Regex-based Redaction Builder ===

def regex_redactor(pattern: str, replacement: str, strategy_name: str) -> RedactionFn:
    """
    Build a custom redaction function from regex pattern

    Args:
        pattern: Regex pattern to match
        replacement: Replacement string
        strategy_name: Name of this strategy

    Returns:
        Redaction function
    """
    compiled = re.compile(pattern)

    def redact(text: str) -> tuple[str, str]:
        redacted = compiled.sub(replacement, text)
        return (redacted, strategy_name)

    return redact


# === Example Custom Redactors ===

redact_ip_address = regex_redactor(
    r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
    '[IP_REDACTED]',
    'ip_address_mask'
)

redact_api_key = regex_redactor(
    r'\b[A-Za-z0-9]{32,}\b',
    '[API_KEY_REDACTED]',
    'api_key_mask'
)

redact_jwt = regex_redactor(
    r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
    '[JWT_REDACTED]',
    'jwt_mask'
)


__all__ = [
    # Core functions
    "mask_email",
    "mask_phone",
    "mask_ssn",
    "mask_credit_card",
    "hash_value",
    "redact_full",
    # Composition
    "compose_redactions",
    "apply_pii_redaction",
    # Profiles
    "RedactionProfile",
    "PROFILE_PII",
    "PROFILE_FINANCIAL",
    "PROFILE_COMPREHENSIVE",
    "PROFILE_HASH_ALL",
    # Context operations
    "redact_at_path",
    "extract_redaction_metadata",
    # Builders
    "regex_redactor",
    # Custom redactors
    "redact_ip_address",
    "redact_api_key",
    "redact_jwt",
]

