"""
Core types for Composable Guard Algebra (Heimdall)

Defines the fundamental types used throughout the guard system:
- Context: The data being processed
- Violation: Represents a policy violation (optimized with __slots__)
- Either: Functional result type (Left = failure, Right = success)
- Guard: The core guard function type
"""

from collections.abc import Awaitable, Callable
from typing import Any, Literal, Union

# Context type - represents the data being processed by guards
Ctx = dict[str, Any]

class Violation:
    """
    Represents a policy violation with metadata (optimized with __slots__)

    Using __slots__ reduces memory overhead by 20-40% compared to dict-based attributes.

    Attributes:
        rule_id: Guard rule identifier (e.g., "pii.input", "auth.required")
        severity: Severity level ("low", "med", "high", "critical")
        message: Human-readable violation message
        span: Additional context (path, source, destination, etc.)
        score: Optional confidence score (0.0 to 1.0)
        evidence: Optional evidence data
        tier: Optional tier classification ("T0", "T1", "T2")
        code: Optional machine-readable error code
        path: Optional path in context where violation occurred
        source: Optional data source (for dataflow violations)
        sink: Optional data destination (for dataflow violations)
        remediation: Optional guidance on how to fix the violation
        timestamp: Optional timestamp when violation occurred
        shadow_mode: If True, violation is logged but does not block execution
        decision_duration_ms: Time taken to evaluate this guard (ms)
        redaction_applied: Optional redaction strategy applied (e.g., "email_mask", "ssn_hash")
    """

    __slots__ = (
        'rule_id', 'severity', 'message', 'span', 'score', 'evidence',
        'tier', 'code', 'path', 'source', 'sink', 'remediation',
        'timestamp', 'shadow_mode', 'decision_duration_ms', 'redaction_applied'
    )

    def __init__(
        self,
        rule_id: str,
        severity: Literal["low", "med", "high", "critical"],
        message: str,
        span: dict[str, Any] | None = None,
        score: float | None = None,
        evidence: Any = None,
        tier: Literal["T0", "T1", "T2"] | None = None,
        code: str | None = None,
        path: str | None = None,
        source: str | None = None,
        sink: str | None = None,
        remediation: str | None = None,
        timestamp: float | None = None,
        shadow_mode: bool = False,
        decision_duration_ms: float | None = None,
        redaction_applied: str | None = None
    ):
        self.rule_id = rule_id
        self.severity = severity
        self.message = message
        self.span = span
        self.score = score
        self.evidence = evidence
        self.tier = tier
        self.code = code
        self.path = path
        self.source = source
        self.sink = sink
        self.remediation = remediation
        self.timestamp = timestamp
        self.shadow_mode = shadow_mode
        self.decision_duration_ms = decision_duration_ms
        self.redaction_applied = redaction_applied

    def to_dict(self) -> dict[str, Any]:
        """Convert violation to dictionary for serialization"""
        result = {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
        }

        # Only include optional fields if they're set
        if self.span is not None:
            result["span"] = self.span
        if self.score is not None:
            result["score"] = self.score
        if self.evidence is not None:
            result["evidence"] = self.evidence
        if self.tier is not None:
            result["tier"] = self.tier
        if self.code is not None:
            result["code"] = self.code
        if self.path is not None:
            result["path"] = self.path
        if self.source is not None:
            result["source"] = self.source
        if self.sink is not None:
            result["sink"] = self.sink
        if self.remediation is not None:
            result["remediation"] = self.remediation
        if self.timestamp is not None:
            result["timestamp"] = self.timestamp
        if self.shadow_mode:
            result["shadow_mode"] = self.shadow_mode
        if self.decision_duration_ms is not None:
            result["decision_duration_ms"] = self.decision_duration_ms
        if self.redaction_applied is not None:
            result["redaction_applied"] = self.redaction_applied

        return result

    def __repr__(self) -> str:
        return f"Violation(rule_id={self.rule_id!r}, severity={self.severity!r}, message={self.message!r})"

# Either type for functional error handling
# Left represents failure (violations), Right represents success (context)
Left = dict[str, Any]  # {"_tag": "Left", "left": [Violation, ...]}
Right = dict[str, Any]  # {"_tag": "Right", "right": Ctx}
Either = Union[Left, Right]

# Guard function type - async function that takes context and returns Either
Guard = Callable[[Ctx], Awaitable[Either]]

def Left_(violations: list[Violation]) -> Left:
    """Create a Left (failure) result with violations"""
    return {
        "_tag": "Left",
        "left": [v.to_dict() if hasattr(v, 'to_dict') else v for v in violations]
    }

def Right_(ctx: Ctx) -> Right:
    """Create a Right (success) result with context"""
    return {
        "_tag": "Right",
        "right": ctx
    }

def is_left(either: Either) -> bool:
    """Check if an Either is Left (failure)"""
    return either["_tag"] == "Left"

def is_right(either: Either) -> bool:
    """Check if an Either is Right (success)"""
    return either["_tag"] == "Right"

def get_violations(either: Either) -> list[dict[str, Any]]:
    """Extract violations from Left result"""
    if not is_left(either):
        raise ValueError("Cannot get violations from Right result")
    return either["left"]

def get_context(either: Either) -> Ctx:
    """Extract context from Right result"""
    if not is_right(either):
        raise ValueError("Cannot get context from Left result")
    return either["right"]
