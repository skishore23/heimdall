"""
Comonads for Context-Aware Guards

Dual of monads - represent context-dependent computations.
Perfect for guards that need surrounding context (history, environment).

Core Concepts:
- Comonad: Structure with extract and extend operations
- Context-aware guards: Guards that depend on surrounding execution context
- History tracking: Maintain state across guard executions
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from .types import Ctx, Either, Guard, Left_, Right_, Violation

A = TypeVar('A')
B = TypeVar('B')


@dataclass
class ComonadContext(Generic[A]):
    """
    Comonad structure holding value with context

    Laws:
    1. extract . extend(f) = f
    2. extend(extract) = id
    3. extend(f) . extend(g) = extend(f . extend(g))
    """
    focus: A
    context: dict[str, Any] = field(default_factory=dict)
    history: list[A] = field(default_factory=list)

    def extract(self) -> A:
        """Extract the focused value"""
        return self.focus

    def extend(self, f: Callable[['ComonadContext[A]'], B]) -> 'ComonadContext[B]':
        """
        Extend computation over context
        Applies f to the whole comonadic context
        """
        new_focus = f(self)
        new_history = self.history + [self.focus]

        return ComonadContext(
            focus=new_focus,
            context=self.context.copy(),
            history=new_history
        )

    def duplicate(self) -> 'ComonadContext[ComonadContext[A]]':
        """
        Duplicate context
        Creates nested comonadic structure
        """
        return ComonadContext(
            focus=self,
            context=self.context.copy(),
            history=self.history.copy()
        )

    def map(self, f: Callable[[A], B]) -> 'ComonadContext[B]':
        """Functor map over the focus"""
        return ComonadContext(
            focus=f(self.focus),
            context=self.context.copy(),
            history=self.history.copy()
        )


@dataclass
class HistoryComonad(Generic[A]):
    """
    Comonad that tracks history of values
    Perfect for guards that need to see previous states
    """
    current: A
    past: list[A] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def extract(self) -> A:
        """Get current value"""
        return self.current

    def extend(self, f: Callable[['HistoryComonad[A]'], B]) -> 'HistoryComonad[B]':
        """Extend with history preservation"""
        new_current = f(self)
        new_past = self.past + [self.current]

        return HistoryComonad(
            current=new_current,
            past=new_past,
            metadata=self.metadata.copy()
        )

    def get_history(self, n: int) -> list[A]:
        """Get last n historical values"""
        return self.past[-n:] if n <= len(self.past) else self.past

    def all_values(self) -> list[A]:
        """Get all values including current"""
        return self.past + [self.current]


@dataclass
class EnvironmentComonad(Generic[A]):
    """
    Comonad that provides environmental context
    Useful for guards that need configuration or global state
    """
    value: A
    environment: dict[str, Any] = field(default_factory=dict)

    def extract(self) -> A:
        """Get value"""
        return self.value

    def extend(self, f: Callable[['EnvironmentComonad[A]'], B]) -> 'EnvironmentComonad[B]':
        """Extend with environment"""
        new_value = f(self)

        return EnvironmentComonad(
            value=new_value,
            environment=self.environment.copy()
        )

    def local(self, f: Callable[[dict[str, Any]], dict[str, Any]]) -> 'EnvironmentComonad[A]':
        """Modify environment locally"""
        return EnvironmentComonad(
            value=self.value,
            environment=f(self.environment)
        )

    def ask(self, key: str) -> Any:
        """Query environment"""
        return self.environment.get(key)


# Guard constructors using comonads

def history_aware_guard(
    comonadic_check: Callable[[HistoryComonad[Ctx]], bool],
    rule_id: str,
    message: str,
    max_history: int = 10
) -> Guard:
    """
    Create guard that's aware of execution history

    Args:
        comonadic_check: Function that checks comonadic context
        rule_id: Rule identifier
        message: Violation message
        max_history: Maximum history to maintain

    Returns:
        History-aware guard
    """
    history: list[Ctx] = []

    async def run(ctx: Ctx) -> Either:
        # Create comonadic context
        comonad = HistoryComonad(
            current=ctx,
            past=history[-max_history:] if history else []
        )

        # Check using comonadic function
        if not comonadic_check(comonad):
            return Left_([Violation(
                rule_id=rule_id,
                severity="med",
                message=message,
                evidence={
                    "current": ctx,
                    "history_size": len(history)
                }
            )])

        # Update history
        history.append(ctx)
        if len(history) > max_history:
            history.pop(0)

        return Right_(ctx)

    return run


def environment_aware_guard(
    environment: dict[str, Any],
    check: Callable[[EnvironmentComonad[Ctx]], bool],
    rule_id: str,
    message: str
) -> Guard:
    """
    Create guard with environmental context

    Args:
        environment: Environmental configuration
        check: Comonadic check function
        rule_id: Rule identifier
        message: Violation message

    Returns:
        Environment-aware guard
    """
    async def run(ctx: Ctx) -> Either:
        # Create comonadic context
        comonad = EnvironmentComonad(
            value=ctx,
            environment=environment
        )

        # Check using comonadic function
        if not check(comonad):
            return Left_([Violation(
                rule_id=rule_id,
                severity="med",
                message=message,
                evidence={"environment": environment}
            )])

        return Right_(ctx)

    return run


def windowed_guard(
    window_size: int,
    aggregate: Callable[[list[Ctx]], bool],
    rule_id: str,
    message: str
) -> Guard:
    """
    Create guard that operates on a sliding window of contexts

    Args:
        window_size: Size of sliding window
        aggregate: Function to check aggregated window
        rule_id: Rule identifier
        message: Violation message

    Returns:
        Windowed guard
    """
    window: list[Ctx] = []

    async def run(ctx: Ctx) -> Either:
        # Add to window
        window.append(ctx)
        if len(window) > window_size:
            window.pop(0)

        # Check aggregate condition
        if len(window) == window_size:
            if not aggregate(window):
                return Left_([Violation(
                    rule_id=rule_id,
                    severity="med",
                    message=message,
                    evidence={"window_size": len(window)}
                )])

        return Right_(ctx)

    return run


def stateful_guard(
    initial_state: A,
    update: Callable[[A, Ctx], A],
    check: Callable[[A, Ctx], bool],
    rule_id: str,
    message: str
) -> Guard:
    """
    Create guard with explicit state management (comonadic style)

    Args:
        initial_state: Initial state value
        update: State update function
        check: Check function using state
        rule_id: Rule identifier
        message: Violation message

    Returns:
        Stateful guard
    """
    state = {"current": initial_state}

    async def run(ctx: Ctx) -> Either:
        # Check using current state
        if not check(state["current"], ctx):
            return Left_([Violation(
                rule_id=rule_id,
                severity="med",
                message=message,
                evidence={"state": state["current"]}
            )])

        # Update state
        state["current"] = update(state["current"], ctx)

        return Right_(ctx)

    return run


# Comonadic combinators

def cmap(f: Callable[[A], B], comonad: ComonadContext[A]) -> ComonadContext[B]:
    """Functor map for comonad"""
    return comonad.map(f)


def cobind(comonad: ComonadContext[A], f: Callable[[ComonadContext[A]], B]) -> ComonadContext[B]:
    """Comonadic bind (extend)"""
    return comonad.extend(f)


def counit(comonad: ComonadContext[A]) -> A:
    """Counit (extract)"""
    return comonad.extract()


# Example comonadic guards

def rate_limiting_guard(
    max_requests: int,
    time_window_seconds: float,
    rule_id: str = "rate_limit"
) -> Guard:
    """
    Rate limiting guard using history comonad

    Args:
        max_requests: Maximum requests allowed
        time_window_seconds: Time window in seconds
        rule_id: Rule identifier

    Returns:
        Rate limiting guard
    """
    from datetime import datetime, timedelta

    def check_rate_limit(comonad: HistoryComonad[Ctx]) -> bool:
        cutoff = datetime.now() - timedelta(seconds=time_window_seconds)

        # Count recent requests in window
        recent_count = 0
        for past_ctx in comonad.past:
            if past_ctx.get("_timestamp", datetime.min) > cutoff:
                recent_count += 1

        return recent_count < max_requests

    return history_aware_guard(
        comonadic_check=check_rate_limit,
        rule_id=rule_id,
        message=f"Rate limit exceeded: {max_requests} requests per {time_window_seconds}s"
    )


def trend_detection_guard(
    threshold: float,
    window: int,
    metric_key: str,
    rule_id: str = "trend_detection"
) -> Guard:
    """
    Detect trends in metric values using windowed comonad

    Args:
        threshold: Threshold for trend detection
        window: Window size
        metric_key: Key for metric in context
        rule_id: Rule identifier

    Returns:
        Trend detection guard
    """
    def check_trend(contexts: list[Ctx]) -> bool:
        values = [ctx.get(metric_key, 0) for ctx in contexts]

        if len(values) < 2:
            return True

        # Calculate trend (simple linear)
        trend = (values[-1] - values[0]) / len(values)

        return abs(trend) < threshold

    return windowed_guard(
        window_size=window,
        aggregate=check_trend,
        rule_id=rule_id,
        message=f"Trend exceeded threshold: {threshold}"
    )


def conditional_on_history(
    predicate: Callable[[list[Ctx]], bool],
    then_guard: Guard,
    else_guard: Guard | None = None
) -> Guard:
    """
    Conditionally apply guards based on history

    Args:
        predicate: Predicate on history
        then_guard: Guard to apply if predicate true
        else_guard: Guard to apply if predicate false

    Returns:
        Conditional history-aware guard
    """
    history: list[Ctx] = []

    async def run(ctx: Ctx) -> Either:
        history.append(ctx)

        if predicate(history):
            result = await then_guard(ctx)
        elif else_guard:
            result = await else_guard(ctx)
        else:
            result = Right_(ctx)

        return result

    return run

