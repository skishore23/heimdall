"""
Redis-backed Rate Limiter with Sliding Window

Provides production-ready rate limiting with:
- Sliding window algorithm for accurate rate limiting
- Token bucket with burst support
- Multi-tenant support with key tuples
- Fairness isolation between tenants
- Retry-After header calculation

Fail-fast design: if Redis is configured but unavailable, fail immediately.
"""

import time
from dataclasses import dataclass
from typing import Literal

from .types import Ctx, Either, Guard, Left_, Right_, Violation

# === Rate Limit Configuration ===

@dataclass(frozen=True)
class RateLimitConfig:
    """Immutable rate limit configuration"""
    max_requests: int
    window_seconds: int
    burst: int | None = None
    algorithm: Literal["sliding_window", "token_bucket", "fixed_window"] = "sliding_window"
    penalty_backoff_seconds: int = 0
    redis_url: str | None = None
    key_prefix: str = "ratelimit"


# === Redis Connection ===

class RedisRateLimiter:
    """Redis-backed rate limiter with sliding window"""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._redis = None

    async def initialize(self) -> None:
        """Initialize Redis connection"""
        try:
            import redis.asyncio as aioredis

            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

            # Test connection
            await self._redis.ping()

        except ImportError as e:
            raise ImportError(
                "Redis rate limiting requires redis package. "
                "Install with: pip install redis[asyncio]"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Redis at {self.redis_url}: {str(e)}") from e

    async def check_rate_limit_sliding_window(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, int, float]:
        """
        Check rate limit using sliding window algorithm

        Args:
            key: Rate limit key
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed, current_count, retry_after_seconds)
        """
        if not self._redis:
            raise RuntimeError("Redis connection not initialized")

        current_time = time.time()
        window_start = current_time - window_seconds

        # Use sorted set to track requests in window
        pipeline = self._redis.pipeline()

        # Remove old entries
        pipeline.zremrangebyscore(key, 0, window_start)

        # Count current requests in window
        pipeline.zcard(key)

        # Add current request
        pipeline.zadd(key, {str(current_time): current_time})

        # Set expiry on key
        pipeline.expire(key, window_seconds * 2)

        # Execute pipeline
        results = await pipeline.execute()
        current_count = results[1]  # Result of zcard

        # Check if rate limit exceeded
        if current_count >= max_requests:
            # Calculate retry-after
            oldest_in_window = await self._redis.zrange(key, 0, 0, withscores=True)
            if oldest_in_window:
                oldest_time = oldest_in_window[0][1]
                retry_after = oldest_time + window_seconds - current_time
                return (False, current_count, max(0, retry_after))
            return (False, current_count, window_seconds)

        return (True, current_count + 1, 0)

    async def check_rate_limit_token_bucket(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        burst: int
    ) -> tuple[bool, int, float]:
        """
        Check rate limit using token bucket algorithm

        Args:
            key: Rate limit key
            max_requests: Token refill rate
            window_seconds: Refill interval
            burst: Bucket capacity (max burst)

        Returns:
            Tuple of (allowed, tokens_remaining, retry_after_seconds)
        """
        if not self._redis:
            raise RuntimeError("Redis connection not initialized")

        current_time = time.time()
        bucket_key = f"{key}:bucket"
        last_refill_key = f"{key}:refill"

        # Get current bucket state
        bucket_data = await self._redis.mget([bucket_key, last_refill_key])
        tokens = float(bucket_data[0]) if bucket_data[0] else float(burst)
        last_refill = float(bucket_data[1]) if bucket_data[1] else current_time

        # Calculate token refill
        time_passed = current_time - last_refill
        refill_rate = max_requests / window_seconds
        tokens_to_add = time_passed * refill_rate
        tokens = min(burst, tokens + tokens_to_add)

        # Check if request can be served
        if tokens >= 1:
            # Consume one token
            tokens -= 1

            # Update bucket
            pipeline = self._redis.pipeline()
            pipeline.set(bucket_key, str(tokens))
            pipeline.set(last_refill_key, str(current_time))
            pipeline.expire(bucket_key, window_seconds * 2)
            pipeline.expire(last_refill_key, window_seconds * 2)
            await pipeline.execute()

            return (True, int(tokens), 0)
        else:
            # Calculate retry-after
            tokens_needed = 1 - tokens
            retry_after = tokens_needed / refill_rate
            return (False, 0, retry_after)

    async def close(self) -> None:
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()


# === In-Memory Rate Limiter (Fallback) ===

class MemoryRateLimiter:
    """In-memory rate limiter using sliding window"""

    def __init__(self):
        self._windows: dict[str, list[float]] = {}

    async def check_rate_limit_sliding_window(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, int, float]:
        """Check rate limit using in-memory sliding window"""
        current_time = time.time()
        window_start = current_time - window_seconds

        # Initialize window if needed
        if key not in self._windows:
            self._windows[key] = []

        # Remove old requests
        self._windows[key] = [
            t for t in self._windows[key]
            if t >= window_start
        ]

        # Check rate limit
        current_count = len(self._windows[key])

        if current_count >= max_requests:
            # Calculate retry-after
            oldest = self._windows[key][0]
            retry_after = oldest + window_seconds - current_time
            return (False, current_count, max(0, retry_after))

        # Add current request
        self._windows[key].append(current_time)

        return (True, current_count + 1, 0)

    async def check_rate_limit_token_bucket(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        burst: int
    ) -> tuple[bool, int, float]:
        """Check rate limit using in-memory token bucket"""
        # Simple implementation - just use sliding window for memory mode
        return await self.check_rate_limit_sliding_window(key, burst, window_seconds)


# === Rate Limiter Factory ===

_rate_limiters: dict[str, RedisRateLimiter | MemoryRateLimiter] = {}


async def get_rate_limiter(redis_url: str | None = None) -> RedisRateLimiter | MemoryRateLimiter:
    """
    Get or create rate limiter

    Args:
        redis_url: Redis URL (if None, use in-memory limiter)

    Returns:
        Rate limiter instance
    """
    if redis_url:
        if redis_url not in _rate_limiters:
            limiter = RedisRateLimiter(redis_url)
            await limiter.initialize()
            _rate_limiters[redis_url] = limiter
        return _rate_limiters[redis_url]
    else:
        if "memory" not in _rate_limiters:
            _rate_limiters["memory"] = MemoryRateLimiter()
        return _rate_limiters["memory"]


# === Guard Wrapper ===

def create_rate_limit_guard(
    key_fn: callable,
    config: RateLimitConfig,
    rule_id: str = "rate_limit"
) -> Guard:
    """
    Create a rate limit guard

    Args:
        key_fn: Function to extract rate limit key from context
        config: Rate limit configuration
        rule_id: Rule identifier

    Returns:
        Rate limit guard
    """
    async def run(ctx: Ctx) -> Either:
        # Extract key
        key_parts = key_fn(ctx)
        if isinstance(key_parts, tuple):
            key = ":".join(str(p) for p in key_parts)
        else:
            key = str(key_parts)

        # Add prefix
        full_key = f"{config.key_prefix}:{key}"

        # Get limiter
        limiter = await get_rate_limiter(config.redis_url)

        # Check rate limit
        if config.algorithm == "token_bucket" and config.burst:
            allowed, count, retry_after = await limiter.check_rate_limit_token_bucket(
                full_key,
                config.max_requests,
                config.window_seconds,
                config.burst
            )
        else:
            allowed, count, retry_after = await limiter.check_rate_limit_sliding_window(
                full_key,
                config.max_requests,
                config.window_seconds
            )

        if not allowed:
            return Left_([Violation(
                rule_id=rule_id,
                severity="high",
                message=f"Rate limit exceeded: {count}/{config.max_requests} requests in {config.window_seconds}s",
                code="RATE_LIMIT_EXCEEDED",
                evidence={
                    "key": key,
                    "current_count": count,
                    "max_requests": config.max_requests,
                    "window_seconds": config.window_seconds,
                    "retry_after_seconds": retry_after,
                    "algorithm": config.algorithm
                },
                remediation=f"Retry after {int(retry_after)} seconds"
            )])

        # Store rate limit info in context for response headers
        if "_rate_limit_info" not in ctx:
            ctx["_rate_limit_info"] = {}

        ctx["_rate_limit_info"] = {
            "limit": config.max_requests,
            "remaining": config.max_requests - count,
            "reset": int(time.time() + config.window_seconds)
        }

        return Right_(ctx)

    return run


# === Multi-Tenant Support ===

def multi_tenant_key(tenant_id: str, user_id: str, route: str) -> tuple[str, str, str]:
    """
    Create multi-tenant rate limit key

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        route: Route/endpoint

    Returns:
        Key tuple
    """
    return (tenant_id, user_id, route)


def tenant_isolation_key(tenant_id: str) -> str:
    """
    Create tenant isolation key for fairness

    Args:
        tenant_id: Tenant identifier

    Returns:
        Tenant key
    """
    return tenant_id


__all__ = [
    # Configuration
    "RateLimitConfig",
    # Limiters
    "RedisRateLimiter",
    "MemoryRateLimiter",
    "get_rate_limiter",
    # Guard
    "create_rate_limit_guard",
    # Key functions
    "multi_tenant_key",
    "tenant_isolation_key",
]

