"""
Kleisli Composition for Monadic Guard Chains

Pure functional composition using Kleisli arrows for Either monad.
Enables powerful monadic composition patterns with proper category theory.

Core Concepts:
- Kleisli Arrow: A -> M B (functions returning monadic values)
- Kleisli Composition: (>=>) operator for composing Kleisli arrows
- Monadic Bind: (>>=) for sequencing monadic operations
"""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from .types import (
    Ctx,
    Either,
    Guard,
    Left_,
    Right_,
    get_context,
    get_violations,
    is_left,
    is_right,
)

# Type variables
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')

# Kleisli arrow type: A -> Either[B]
KleisliArrow = Callable[[A], Awaitable[Either]]


def identity() -> Guard:
    """
    Identity morphism for Either monad
    id :: Ctx -> Either Ctx
    """
    async def run(ctx: Ctx) -> Either:
        return Right_(ctx)
    return run


def kleisli_compose(f: Guard, g: Guard) -> Guard:
    """
    Kleisli composition: (f >=> g)

    Compose two guards monadically:
    f :: Ctx -> Either Ctx
    g :: Ctx -> Either Ctx
    (f >=> g) :: Ctx -> Either Ctx

    Args:
        f: First guard
        g: Second guard

    Returns:
        Composed guard
    """
    async def composed(ctx: Ctx) -> Either:
        # Run first guard
        result_f = await f(ctx)

        # If Left, short-circuit
        if is_left(result_f):
            return result_f

        # Extract context and run second guard
        ctx_f = get_context(result_f)
        result_g = await g(ctx_f)

        return result_g

    return composed


def bind(either: Either, f: Guard) -> Awaitable[Either]:
    """
    Monadic bind (>>=)

    either >>= f

    If either is Right, apply f to the context
    If either is Left, propagate the violations

    Args:
        either: Result to bind over
        f: Guard to apply

    Returns:
        New Either result
    """
    async def bound() -> Either:
        if is_left(either):
            return either

        ctx = get_context(either)
        return await f(ctx)

    return bound()


def chain(*guards: Guard) -> Guard:
    """
    Chain multiple guards using Kleisli composition
    Equivalent to: g1 >=> g2 >=> g3 >=> ...

    Args:
        *guards: Guards to chain

    Returns:
        Chained guard
    """
    if not guards:
        return identity()

    if len(guards) == 1:
        return guards[0]

    def kleisli_reduce(acc: Guard, g: Guard) -> Guard:
        return kleisli_compose(acc, g)

    from functools import reduce
    return reduce(kleisli_reduce, guards)


def fmap(f: Callable[[Ctx], Ctx]) -> Callable[[Either], Either]:
    """
    Functor map for Either

    fmap :: (Ctx -> Ctx) -> Either Ctx -> Either Ctx

    Maps a pure function over the context inside Either,
    leaving Left values unchanged.

    Args:
        f: Pure transformation function

    Returns:
        Function that maps Either values
    """
    def mapped(either: Either) -> Either:
        if is_left(either):
            return either

        ctx = get_context(either)
        return Right_(f(ctx))

    return mapped


def lift(f: Callable[[Ctx], Ctx]) -> Guard:
    """
    Lift a pure function into a guard (Kleisli arrow)

    lift :: (Ctx -> Ctx) -> Guard

    Args:
        f: Pure function to lift

    Returns:
        Guard that applies f
    """
    async def lifted(ctx: Ctx) -> Either:
        try:
            result = f(ctx)
            return Right_(result)
        except Exception as e:
            from .types import Violation
            return Left_([Violation(
                rule_id="lift_error",
                severity="critical",
                message=f"Lifted function failed: {e}"
            )])

    return lifted


def kleisli_left_identity(a: Ctx, f: Guard) -> bool:
    """
    Verify Kleisli left identity law:
    return >=> f ≡ f

    This is for testing/verification purposes
    """
    import asyncio

    left_side = kleisli_compose(identity(), f)

    result_left = asyncio.run(left_side(a))
    result_right = asyncio.run(f(a))

    return result_left == result_right


def kleisli_right_identity(a: Ctx, f: Guard) -> bool:
    """
    Verify Kleisli right identity law:
    f >=> return ≡ f

    This is for testing/verification purposes
    """
    import asyncio

    right_side = kleisli_compose(f, identity())

    result_left = asyncio.run(right_side(a))
    result_right = asyncio.run(f(a))

    return result_left == result_right


def kleisli_associativity(a: Ctx, f: Guard, g: Guard, h: Guard) -> bool:
    """
    Verify Kleisli associativity law:
    (f >=> g) >=> h ≡ f >=> (g >=> h)

    This is for testing/verification purposes
    """
    import asyncio

    left_side = kleisli_compose(kleisli_compose(f, g), h)
    right_side = kleisli_compose(f, kleisli_compose(g, h))

    result_left = asyncio.run(left_side(a))
    result_right = asyncio.run(right_side(a))

    return result_left == result_right


def try_guard(guard: Guard, fallback_guard: Guard | None = None) -> Guard:
    """
    Try a guard, using fallback if it fails

    Similar to try/catch but in monadic style

    Args:
        guard: Primary guard to try
        fallback_guard: Optional fallback guard

    Returns:
        Guard that tries primary, falls back on failure
    """
    async def tried(ctx: Ctx) -> Either:
        try:
            result = await guard(ctx)

            # If Left and we have fallback, try fallback
            if is_left(result) and fallback_guard:
                return await fallback_guard(ctx)

            return result

        except Exception as e:
            if fallback_guard:
                return await fallback_guard(ctx)

            from .types import Violation
            return Left_([Violation(
                rule_id="guard_exception",
                severity="critical",
                message=f"Guard failed: {e}"
            )])

    return tried


def filter_violations(predicate: Callable[[dict], bool]) -> Callable[[Either], Either]:
    """
    Filter violations based on a predicate

    Args:
        predicate: Function that returns True for violations to keep

    Returns:
        Function that filters Either violations
    """
    def filtered(either: Either) -> Either:
        if is_right(either):
            return either

        violations = get_violations(either)
        filtered_violations = [v for v in violations if predicate(v)]

        if filtered_violations:
            return Left_(filtered_violations)

        # No violations after filtering - convert to Right
        return Right_({})

    return filtered


def merge_violations(either1: Either, either2: Either) -> Either:
    """
    Merge violations from two Either values

    If both are Right, return Right
    If one is Left, return that Left
    If both are Left, merge violations

    Args:
        either1: First Either
        either2: Second Either

    Returns:
        Merged Either
    """
    if is_right(either1) and is_right(either2):
        # Both succeeded - merge contexts
        ctx1 = get_context(either1)
        ctx2 = get_context(either2)
        return Right_({**ctx1, **ctx2})

    violations = []

    if is_left(either1):
        violations.extend(get_violations(either1))

    if is_left(either2):
        violations.extend(get_violations(either2))

    return Left_(violations)


def when(condition: Callable[[Ctx], bool], guard: Guard) -> Guard:
    """
    Conditionally apply a guard

    Args:
        condition: Predicate to check
        guard: Guard to apply if condition is True

    Returns:
        Conditional guard
    """
    async def conditional(ctx: Ctx) -> Either:
        if condition(ctx):
            return await guard(ctx)
        return Right_(ctx)

    return conditional


def unless_condition(condition: Callable[[Ctx], bool], guard: Guard) -> Guard:
    """
    Apply guard unless condition is True

    Args:
        condition: Predicate to check
        guard: Guard to apply if condition is False

    Returns:
        Conditional guard
    """
    async def conditional(ctx: Ctx) -> Either:
        if not condition(ctx):
            return await guard(ctx)
        return Right_(ctx)

    return conditional

