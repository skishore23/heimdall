"""
Temporal Relationship Tracking & Loop Detection

Tracks temporal relationships between calls, detects loops, and enforces
temporal constraints. Surpasses Invariant's capabilities with sophisticated
pattern detection.

Core Concepts:
- Temporal Chain: Ordered sequence of events with timing
- Loop Detection: Identify retry patterns and circular dependencies
- Temporal Constraints: Enforce timing-based rules
"""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .types import Ctx, Either, Guard, Left_, Right_, Violation


@dataclass
class TemporalEvent:
    """Single event in the temporal chain"""
    id: str
    event_type: str  # "tool_call", "llm_call", "guard_check", etc.
    timestamp: datetime
    data: dict[str, Any]
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CallPattern:
    """Pattern in call history"""
    pattern_type: str  # "retry", "loop", "escalation", "alternating"
    events: list[TemporalEvent]
    count: int
    first_seen: datetime
    last_seen: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


class TemporalChain:
    """
    Tracks sequence of events over time
    Enables detection of patterns, loops, and temporal violations
    """

    def __init__(self, max_history: int = 1000):
        self.events: deque[TemporalEvent] = deque(maxlen=max_history)
        self.event_index: dict[str, TemporalEvent] = {}
        self.patterns: list[CallPattern] = []

    def add_event(self, event: TemporalEvent) -> None:
        """Add event to temporal chain"""
        self.events.append(event)
        self.event_index[event.id] = event

        # Update pattern detection
        self._detect_patterns()

    def get_event(self, event_id: str) -> TemporalEvent | None:
        """Retrieve event by ID"""
        return self.event_index.get(event_id)

    def get_events_by_type(self, event_type: str) -> list[TemporalEvent]:
        """Get all events of specific type"""
        return [e for e in self.events if e.event_type == event_type]

    def get_recent_events(self, duration: timedelta) -> list[TemporalEvent]:
        """Get events within time duration"""
        cutoff = datetime.now() - duration
        return [e for e in self.events if e.timestamp >= cutoff]

    def get_event_chain(self, event_id: str) -> list[TemporalEvent]:
        """Get chain of events leading to specific event"""
        chain = []
        current_id = event_id

        while current_id:
            event = self.get_event(current_id)
            if not event:
                break
            chain.append(event)
            current_id = event.parent_id

        return list(reversed(chain))

    def _detect_patterns(self) -> None:
        """Detect patterns in event history"""
        # Detect retry patterns
        self._detect_retry_pattern()

        # Detect circular loops
        self._detect_loop_pattern()

        # Detect alternating patterns
        self._detect_alternating_pattern()

    def _detect_retry_pattern(self) -> None:
        """Detect retry patterns (same call repeated)"""
        recent = list(self.events)[-20:]  # Look at last 20 events

        for i in range(len(recent)):
            event = recent[i]

            # Count repetitions
            repetitions = [event]
            for j in range(i + 1, len(recent)):
                if self._events_similar(event, recent[j]):
                    repetitions.append(recent[j])

            if len(repetitions) >= 2:
                # Found retry pattern
                pattern = CallPattern(
                    pattern_type="retry",
                    events=repetitions,
                    count=len(repetitions),
                    first_seen=repetitions[0].timestamp,
                    last_seen=repetitions[-1].timestamp,
                    metadata={"call_type": event.event_type}
                )

                # Add if not already tracked
                if not self._pattern_exists(pattern):
                    self.patterns.append(pattern)

    def _detect_loop_pattern(self) -> None:
        """Detect circular call loops"""
        recent = list(self.events)[-30:]

        # Build call graph
        call_graph: dict[str, list[str]] = {}
        for event in recent:
            if event.parent_id:
                if event.parent_id not in call_graph:
                    call_graph[event.parent_id] = []
                call_graph[event.parent_id].append(event.id)

        # Detect cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node: str, path: list[str]) -> list[str] | None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in call_graph.get(node, []):
                if neighbor not in visited:
                    cycle = has_cycle(neighbor, path[:])
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:]

            rec_stack.remove(node)
            return None

        for event_id in call_graph:
            if event_id not in visited:
                cycle = has_cycle(event_id, [])
                if cycle:
                    cycle_events = [self.event_index[eid] for eid in cycle if eid in self.event_index]

                    pattern = CallPattern(
                        pattern_type="loop",
                        events=cycle_events,
                        count=len(cycle),
                        first_seen=cycle_events[0].timestamp,
                        last_seen=cycle_events[-1].timestamp,
                        metadata={"cycle_length": len(cycle)}
                    )

                    if not self._pattern_exists(pattern):
                        self.patterns.append(pattern)

    def _detect_alternating_pattern(self) -> None:
        """Detect alternating call patterns (A -> B -> A -> B)"""
        recent = list(self.events)[-15:]

        if len(recent) < 4:
            return

        for i in range(len(recent) - 3):
            if (self._events_similar(recent[i], recent[i + 2]) and
                self._events_similar(recent[i + 1], recent[i + 3]) and
                not self._events_similar(recent[i], recent[i + 1])):

                pattern = CallPattern(
                    pattern_type="alternating",
                    events=recent[i:i + 4],
                    count=2,
                    first_seen=recent[i].timestamp,
                    last_seen=recent[i + 3].timestamp,
                    metadata={
                        "type_a": recent[i].event_type,
                        "type_b": recent[i + 1].event_type
                    }
                )

                if not self._pattern_exists(pattern):
                    self.patterns.append(pattern)

    def _events_similar(self, e1: TemporalEvent, e2: TemporalEvent) -> bool:
        """Check if two events are similar (for pattern detection)"""
        return (e1.event_type == e2.event_type and
                e1.data.get("function_name") == e2.data.get("function_name"))

    def _pattern_exists(self, pattern: CallPattern) -> bool:
        """Check if pattern already tracked"""
        for p in self.patterns:
            if (p.pattern_type == pattern.pattern_type and
                p.events[-1].id == pattern.events[-1].id):
                return True
        return False

    def get_patterns(self, pattern_type: str | None = None) -> list[CallPattern]:
        """Get detected patterns, optionally filtered by type"""
        if pattern_type:
            return [p for p in self.patterns if p.pattern_type == pattern_type]
        return self.patterns


class TemporalConstraint:
    """
    Temporal constraint checker
    Enforces time-based rules on event sequences
    """

    def __init__(self, chain: TemporalChain):
        self.chain = chain

    def count_in_window(
        self,
        event_type: str,
        window: timedelta,
        predicate: Callable[[TemporalEvent], bool] | None = None
    ) -> int:
        """Count events of type in time window"""
        recent = self.chain.get_recent_events(window)
        matching = [e for e in recent if e.event_type == event_type]

        if predicate:
            matching = [e for e in matching if predicate(e)]

        return len(matching)

    def has_sequence(self, event_types: list[str], window: timedelta) -> bool:
        """Check if sequence of event types occurred in window"""
        recent = self.chain.get_recent_events(window)

        if len(recent) < len(event_types):
            return False

        # Look for subsequence
        for i in range(len(recent) - len(event_types) + 1):
            match = True
            for j, expected_type in enumerate(event_types):
                if recent[i + j].event_type != expected_type:
                    match = False
                    break
            if match:
                return True

        return False

    def time_between_events(
        self,
        event_id1: str,
        event_id2: str
    ) -> timedelta | None:
        """Calculate time between two events"""
        e1 = self.chain.get_event(event_id1)
        e2 = self.chain.get_event(event_id2)

        if not e1 or not e2:
            return None

        return abs(e2.timestamp - e1.timestamp)


def detect_retry_loop(
    chain: TemporalChain,
    max_retries: int,
    window: timedelta,
    call_type: str
) -> Guard:
    """
    Create guard that detects retry loops

    Args:
        chain: Temporal chain to check
        max_retries: Maximum allowed retries
        window: Time window to check
        call_type: Type of call to check

    Returns:
        Guard that blocks on excessive retries
    """
    async def run(ctx: Ctx) -> Either:
        constraint = TemporalConstraint(chain)

        count = constraint.count_in_window(
            event_type=call_type,
            window=window
        )

        if count > max_retries:
            return Left_([Violation(
                rule_id="temporal.retry_loop",
                severity="high",
                message=f"Retry loop detected: {count} {call_type} calls in {window}",
                evidence={
                    "count": count,
                    "max_retries": max_retries,
                    "call_type": call_type,
                    "window_seconds": window.total_seconds()
                }
            )])

        return Right_(ctx)

    return run


def detect_circular_dependency(chain: TemporalChain) -> Guard:
    """
    Create guard that detects circular call dependencies

    Args:
        chain: Temporal chain to check

    Returns:
        Guard that blocks on circular dependencies
    """
    async def run(ctx: Ctx) -> Either:
        # Check for loop patterns
        loops = chain.get_patterns("loop")

        if loops:
            return Left_([Violation(
                rule_id="temporal.circular_dependency",
                severity="critical",
                message=f"Circular dependency detected: {len(loops)} loop(s)",
                evidence={
                    "loop_count": len(loops),
                    "cycle_lengths": [p.metadata.get("cycle_length") for p in loops]
                }
            )])

        return Right_(ctx)

    return run


def enforce_rate_limit(
    chain: TemporalChain,
    event_type: str,
    max_count: int,
    window: timedelta
) -> Guard:
    """
    Create guard that enforces rate limits

    Args:
        chain: Temporal chain to check
        event_type: Type of event to limit
        max_count: Maximum allowed count
        window: Time window

    Returns:
        Guard that blocks on rate limit violation
    """
    async def run(ctx: Ctx) -> Either:
        constraint = TemporalConstraint(chain)

        count = constraint.count_in_window(event_type, window)

        if count >= max_count:
            return Left_([Violation(
                rule_id="temporal.rate_limit",
                severity="high",
                message=f"Rate limit exceeded: {count}/{max_count} {event_type} in {window}",
                evidence={
                    "count": count,
                    "max_count": max_count,
                    "event_type": event_type,
                    "window_seconds": window.total_seconds()
                }
            )])

        return Right_(ctx)

    return run


def require_sequence(
    chain: TemporalChain,
    required_sequence: list[str],
    window: timedelta
) -> Guard:
    """
    Create guard that requires specific event sequence

    Args:
        chain: Temporal chain to check
        required_sequence: Required sequence of event types
        window: Time window to check

    Returns:
        Guard that blocks if sequence not found
    """
    async def run(ctx: Ctx) -> Either:
        constraint = TemporalConstraint(chain)

        has_seq = constraint.has_sequence(required_sequence, window)

        if not has_seq:
            return Left_([Violation(
                rule_id="temporal.missing_sequence",
                severity="med",
                message=f"Required sequence not found: {' -> '.join(required_sequence)}",
                evidence={
                    "required_sequence": required_sequence,
                    "window_seconds": window.total_seconds()
                }
            )])

        return Right_(ctx)

    return run

