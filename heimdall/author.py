"""
Guard Authoring DSL - Simple, Composable Runtime Checks

Write guards using builder patterns and compose them with intuitive operators.
"""

from collections.abc import Callable
from typing import Any

from .types import Ctx, Either, Guard, Left_, Right_, Violation

# === Core: Concise Builders ===

class FlowBuilder:
    """
    Build dataflow guards: flow(source).to(dest).forbid_if(predicate, msg)

    Prevents sensitive data from flowing to unintended destinations.
    """

    def __init__(self, source: str):
        self.source = source
        self._checks: list[tuple[str, Callable[[Any], bool], str]] = []

    def to(self, destination: str) -> 'FlowDestination':
        """Set destination path"""
        return FlowDestination(self.source, destination, self._checks)

    def build(self, rule_id: str) -> Guard:
        """Build the final guard"""
        if not self._checks:
            raise ValueError("No flow checks defined")

        async def guard(ctx: Ctx) -> Either:
            violations = []
            source_val = _get_nested(ctx, self.source)

            if source_val:
                for dest, predicate, msg in self._checks:
                    dest_val = _get_nested(ctx, dest)
                    # Check if data flows from source to dest and matches predicate
                    if dest_val is not None and predicate(source_val):
                        violations.append(Violation(
                            rule_id=rule_id,
                            severity="high",
                            message=msg,
                            span={
                                "source": self.source,
                                "destination": dest,
                                "source_value": str(source_val)[:100]
                            }
                        ))

            if violations:
                return Left_(violations)
            return Right_(ctx)

        return guard


class FlowDestination:
    """Intermediate builder after .to() is called"""

    def __init__(self, source: str, destination: str, checks: list):
        self.source = source
        self.destination = destination
        self._checks = checks
        self._builder = None

    def forbid_if(self, predicate: Callable[[Any], bool], msg: str) -> FlowBuilder:
        """Add a check for this flow"""
        self._checks.append((self.destination, predicate, msg))

        # Return a builder that can chain more .to() calls
        builder = FlowBuilder(self.source)
        builder._checks = self._checks
        return builder

    def build(self, rule_id: str) -> Guard:
        """Build with just this one check"""
        builder = FlowBuilder(self.source)
        builder._checks = self._checks
        return builder.build(rule_id)


class G:
    """
    Guard builder for creating runtime checks

    Examples:
        G("auth").require(lambda ctx: ctx.authenticated, "Must be authenticated")
        G("pii").forbid(lambda ctx: has_pii(ctx.input), "Input contains PII")
        G("rate").limit(key=lambda ctx: ctx.user_id, calls=100, window=60, store="redis")
    """

    def __init__(self, rule_id: str, severity: str = "high"):
        self.rule_id = rule_id
        self.severity = severity
        self._guards: list[Guard] = []

    def require(self, condition: Callable[[Ctx], bool], msg: str = None) -> 'G':
        """Require condition to be true"""
        message = msg or f"Required condition failed: {self.rule_id}"

        async def guard(ctx: Ctx) -> Either:
            try:
                result = condition(ctx)
                if result:
                    return Right_(ctx)
                return Left_([Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=message
                )])
            except Exception as e:
                return Left_([Violation(
                    rule_id=self.rule_id,
                    severity="critical",
                    message=f"{message}: {str(e)}"
                )])

        self._guards.append(guard)
        return self

    def forbid(self, condition: Callable[[Ctx], bool], msg: str = None) -> 'G':
        """Forbid condition (must be false)"""
        message = msg or f"Forbidden: {self.rule_id}"

        async def guard(ctx: Ctx) -> Either:
            try:
                result = condition(ctx)
                if not result:
                    return Right_(ctx)
                return Left_([Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=message
                )])
            except Exception as e:
                return Left_([Violation(
                    rule_id=self.rule_id,
                    severity="critical",
                    message=f"{message}: {str(e)}"
                )])

        self._guards.append(guard)
        return self

    def check(self, path: str, predicate: Callable[[Any], bool], msg: str = None) -> 'G':
        """Check predicate on value at path"""
        message = msg or f"Check failed: {path}"

        async def guard(ctx: Ctx) -> Either:
            try:
                value = _get_nested(ctx, path)
                if value is None:
                    return Right_(ctx)  # Skip check if path doesn't exist

                if predicate(value):
                    return Right_(ctx)
                return Left_([Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=message,
                    span={"path": path, "value": str(value)[:100]}
                )])
            except Exception as e:
                return Left_([Violation(
                    rule_id=self.rule_id,
                    severity="critical",
                    message=f"{message}: {str(e)}"
                )])

        self._guards.append(guard)
        return self

    def limit(
        self,
        key: Callable[[Ctx], tuple[str, ...]],
        calls: int,
        window: int,
        store: str = "memory",
        mode: str = "sliding_window",
        burst: int | None = None,
        msg: str = None
    ) -> 'G':
        """
        Rate limiting with explicit configuration

        Args:
            key: Function returning tuple identifying the rate limit bucket
            calls: Maximum number of calls allowed
            window: Time window in seconds
            store: Storage backend ("memory", "redis", "postgres")
            mode: Algorithm ("fixed_window", "sliding_window", "token_bucket")
            burst: Optional burst allowance
            msg: Custom violation message
        """
        message = msg or f"Rate limit exceeded: {calls} calls in {window}s"

        # For now, use existing temporal detection
        # TODO: Implement proper rate limiter with pluggable backends
        from datetime import timedelta

        from .temporal import TemporalChain, detect_retry_loop

        async def guard(ctx: Ctx) -> Either:
            try:
                # Get rate limit key
                limit_key = key(ctx)

                # Use temporal chain for detection
                chain = ctx.get("_temporal_chain") or TemporalChain()
                is_loop, info = detect_retry_loop(
                    chain,
                    max_retries=calls,
                    window=timedelta(seconds=window),
                    call_type=str(limit_key)
                )

                if is_loop:
                    return Left_([Violation(
                        rule_id=self.rule_id,
                        severity=self.severity,
                        message=f"{message} (detected {info['count']} calls)",
                        span={
                            "key": str(limit_key),
                            "count": info['count'],
                            "window": window,
                            "store": store,
                            "mode": mode
                        }
                    )])
                return Right_(ctx)
            except Exception as e:
                return Left_([Violation(
                    rule_id=self.rule_id,
                    severity="critical",
                    message=f"{message}: {str(e)}"
                )])

        self._guards.append(guard)
        return self

    def build(self) -> Guard:
        """Build final guard"""
        if not self._guards:
            raise ValueError("No guards defined")

        if len(self._guards) == 1:
            return self._guards[0]

        # Compose all guards (allOf semantics)
        from .comb import allOf
        return allOf(*self._guards)


# === Flow Builder ===

def flow(source: str) -> FlowBuilder:
    """
    Create dataflow guard builder

    Example:
        prevent_leak = (
            flow("db.users")
            .to("external.email")
            .forbid_if(has_pii, "PII leak detected")
            .build("pii.leak")
        )
    """
    return FlowBuilder(source)


def _get_nested(ctx: Ctx, path: str) -> Any:
    """Get nested value: 'db.users.email' -> ctx['db']['users']['email']"""
    parts = path.split('.')
    value = ctx
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
        if value is None:
            return None
    return value


# === Decorators for Even More Conciseness ===

def guard(rule_id: str, severity: str = "high", msg: str = None):
    """
    Decorator: turn function into guard

    @guard("pii.check")
    def no_pii(ctx):
        return not has_pii(ctx.get("input", ""))
    """
    def decorator(fn: Callable[[Ctx], bool]) -> Guard:
        message = msg or f"Guard failed: {rule_id}"

        async def guard_impl(ctx: Ctx) -> Either:
            try:
                result = fn(ctx)
                if callable(getattr(result, '__await__', None)):
                    result = await result

                if result:
                    return Right_(ctx)
                return Left_([Violation(
                    rule_id=rule_id,
                    severity=severity,
                    message=message
                )])
            except Exception as e:
                return Left_([Violation(
                    rule_id=rule_id,
                    severity="critical",
                    message=f"{message}: {str(e)}"
                )])

        return guard_impl
    return decorator


# === Composition Operators ===

class GuardChain:
    """
    Fluent composition builder for guards

    Methods use clear names instead of symbols:
    - then() for sequential composition (>>)
    - and_also() for conjunction (&)
    - or_else() for disjunction (|)
    - when() for conditional execution
    """

    def __init__(self, guard: Guard):
        self._guard = guard

    def then(self, other: Guard) -> 'GuardChain':
        """Sequential composition: run this guard, then the other"""
        from .comb import seq
        other_guard = other._guard if isinstance(other, GuardChain) else other
        return GuardChain(seq(self._guard, other_guard))

    def and_also(self, other: Guard, collect: bool = False, parallel: bool = False) -> 'GuardChain':
        """
        Conjunction: all must pass

        Args:
            other: The other guard to check
            collect: If True, collect all violations instead of short-circuiting
            parallel: If True and collect=True, execute guards concurrently
        """
        from .comb import allOf
        other_guard = other._guard if isinstance(other, GuardChain) else other

        # Use parallel execution when both collect and parallel are True
        use_parallel = collect and parallel
        return GuardChain(allOf(self._guard, other_guard, parallel=use_parallel))

    def or_else(self, other: Guard) -> 'GuardChain':
        """Disjunction: at least one must pass"""
        from .comb import anyOf
        other_guard = other._guard if isinstance(other, GuardChain) else other
        return GuardChain(anyOf(self._guard, other_guard))

    def when(self, condition: Callable[[Ctx], bool]) -> 'GuardChain':
        """Conditional execution: only run if condition is true"""
        from .kleisli import when as when_guard
        return GuardChain(when_guard(condition, self._guard))

    def build(self) -> Guard:
        """Extract the final composed guard"""
        return self._guard

    # Keep old operators for backwards compatibility but prefer methods
    def __rshift__(self, other: 'GuardChain') -> 'GuardChain':
        """>> operator (prefer .then() method)"""
        return self.then(other)

    def __and__(self, other: 'GuardChain') -> 'GuardChain':
        """& operator (prefer .and_also() method)"""
        return self.and_also(other)

    def __or__(self, other: 'GuardChain') -> 'GuardChain':
        """| operator (prefer .or_else() method)"""
        return self.or_else(other)


def chain(guard: Guard) -> GuardChain:
    """
    Start composing guards with fluent methods

    Example:
        pipeline = (
            chain(auth_guard)
            .then(input_guard)
            .and_also(rate_limit)
        ).build()
    """
    return GuardChain(guard)


# === Examples ===

"""
Example Usage:

1. Simple Guard:
    @guard("pii.check")
    def no_pii(ctx):
        return not has_pii(ctx.input)

2. Builder Pattern:
    auth = G("auth").require(
        lambda ctx: ctx.authenticated,
        "Must be authenticated"
    ).build()

3. Rate Limiting:
    rate_limit = G("rate").limit(
        key=lambda ctx: ctx.user_id,
        calls=100,
        window=60,
        store="redis",
        mode="sliding_window"
    ).build()

4. Dataflow Guards:
    prevent_leak = (
        flow("db.users")
        .to("external.email")
        .forbid_if(has_pii, "PII leak detected")
        .build("pii.leak")
    )

5. Composition:
    pipeline = (
        chain(auth)
        .then(no_pii)
        .and_also(rate_limit)
    ).build()
"""


__all__ = [
    # Main builder
    "G",
    # Decorators
    "guard",
    # Composition
    "chain",
    "GuardChain",
    # Flow helpers
    "flow",
    "FlowBuilder",
    "FlowDestination",
]
