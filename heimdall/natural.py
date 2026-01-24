"""
Essential Guard Transformations

Simple, practical transformations for guards.
Only what's necessary - no theoretical showcase.
"""

from .types import (
    Ctx,
    Either,
    Guard,
    Left_,
    Right_,
    get_context,
    get_violations,
    is_left,
)


def promote_tier(guard: Guard, tier: str, metadata: dict | None = None) -> Guard:
    """
    Promote guard to a specific tier

    Args:
        guard: Guard to promote
        tier: Target tier ("fast", "medium", "slow")
        metadata: Optional metadata to add

    Returns:
        Promoted guard
    """
    async def promoted(ctx: Ctx) -> Either:
        result = await guard(ctx)

        if is_left(result):
            violations = get_violations(result)
            for v in violations:
                if isinstance(v, dict):
                    v["tier"] = tier
                    if metadata:
                        v["tier_metadata"] = metadata
            return result

        new_ctx = get_context(result)
        new_ctx["_tier"] = tier
        if metadata:
            new_ctx["_tier_metadata"] = metadata

        return Right_(new_ctx)

    return promoted


def with_timeout(guard: Guard, timeout_ms: float) -> Guard:
    """
    Add timeout to guard execution

    Args:
        guard: Guard to wrap
        timeout_ms: Timeout in milliseconds

    Returns:
        Guard with timeout
    """
    async def timed(ctx: Ctx) -> Either:
        import asyncio

        from .types import Violation

        try:
            result = await asyncio.wait_for(
                guard(ctx),
                timeout=timeout_ms / 1000.0
            )
            return result
        except TimeoutError:
            return Left_([Violation(
                rule_id="timeout",
                severity="high",
                message=f"Guard timed out after {timeout_ms}ms"
            )])

    return timed


def with_retry(guard: Guard, max_retries: int, backoff_ms: float = 100.0) -> Guard:
    """
    Add retry logic to guard

    Args:
        guard: Guard to wrap
        max_retries: Maximum number of retries
        backoff_ms: Backoff time in milliseconds (exponential)

    Returns:
        Guard with retry logic
    """
    async def retried(ctx: Ctx) -> Either:
        import asyncio

        from .types import Violation

        last_error = None

        for attempt in range(max_retries + 1):
            try:
                result = await guard(ctx)

                # If success or last attempt, return
                if not is_left(result) or attempt == max_retries:
                    return result

                last_error = result

                # Exponential backoff
                await asyncio.sleep(backoff_ms * (2 ** attempt) / 1000.0)

            except Exception as e:
                if attempt == max_retries:
                    return Left_([Violation(
                        rule_id="retry_failed",
                        severity="critical",
                        message=f"Guard failed after {max_retries} retries: {e}"
                    )])

                await asyncio.sleep(backoff_ms * (2 ** attempt) / 1000.0)

        return last_error if last_error else Left_([Violation(
            rule_id="retry_exhausted",
            severity="high",
            message="Retries exhausted"
        )])

    return retried


def to_permissive(guard: Guard) -> Guard:
    """
    Transform guard to permissive mode
    Logs violations but doesn't block

    Args:
        guard: Guard to make permissive

    Returns:
        Permissive guard
    """
    async def permissive(ctx: Ctx) -> Either:
        result = await guard(ctx)

        if is_left(result):
            violations = get_violations(result)

            # Mark as permissive
            for v in violations:
                if isinstance(v, dict):
                    v["mode"] = "permissive"
                    v["blocked"] = False

            # Return Right with violations logged
            new_ctx = ctx.copy()
            new_ctx["_logged_violations"] = violations
            return Right_(new_ctx)

        return result

    return permissive


def to_blocking(guard: Guard) -> Guard:
    """
    Transform guard to blocking mode
    Blocks on any violation

    Args:
        guard: Guard to make blocking

    Returns:
        Blocking guard
    """
    async def blocking(ctx: Ctx) -> Either:
        result = await guard(ctx)

        if is_left(result):
            violations = get_violations(result)
            for v in violations:
                if isinstance(v, dict):
                    v["mode"] = "blocking"
                    v["blocked"] = True
            return result

        return result

    return blocking


# Aliases for backward compatibility
def promote_to_t1(g, m=None):
    return promote_tier(g, "medium", m)
def promote_to_t2(g, m=None):
    return promote_tier(g, "slow", m)
