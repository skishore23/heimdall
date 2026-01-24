"""
Unified Quota Guard System

Combines temporal and rate limiting into a single, configurable guard.
Supports multiple window types, burst limits, and Redis-backed distributed quotas.
"""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from .types import Ctx, Either, Guard, Left_, Right_, Violation


@dataclass
class QuotaConfig:
    """Configuration for quota guard"""
    window_seconds: int  # Time window size (e.g., 60 for per-minute)
    limit: int  # Max requests in window
    burst: int | None = None  # Burst allowance (defaults to limit)
    mode: Literal["fixed", "sliding", "token_bucket"] = "sliding"
    key_fn: Callable[[Ctx], str] | None = None  # Extract quota key from context
    backend: Literal["memory", "redis"] = "memory"
    redis_url: str | None = None

    def __post_init__(self):
        if self.burst is None:
            self.burst = self.limit


class MemoryQuotaBackend:
    """In-memory quota tracking (single-instance only)"""

    def __init__(self):
        # key -> deque of timestamps
        self._fixed_windows: dict[str, tuple[int, int]] = {}  # key -> (window_start, count)
        self._sliding_windows: dict[str, deque] = {}  # key -> deque of timestamps
        self._token_buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_update)

    async def check_fixed_window(
        self,
        key: str,
        window_seconds: int,
        limit: int
    ) -> tuple[bool, int]:
        """Check fixed window quota"""
        now = int(time.time())
        window_start = (now // window_seconds) * window_seconds

        if key not in self._fixed_windows:
            self._fixed_windows[key] = (window_start, 0)

        stored_window, count = self._fixed_windows[key]

        # Reset if new window
        if stored_window != window_start:
            self._fixed_windows[key] = (window_start, 1)
            return True, limit - 1

        # Check limit
        if count < limit:
            self._fixed_windows[key] = (window_start, count + 1)
            return True, limit - (count + 1)

        return False, 0

    async def check_sliding_window(
        self,
        key: str,
        window_seconds: int,
        limit: int
    ) -> tuple[bool, int]:
        """Check sliding window quota"""
        now = time.time()
        cutoff = now - window_seconds

        if key not in self._sliding_windows:
            self._sliding_windows[key] = deque()

        window = self._sliding_windows[key]

        # Remove old timestamps
        while window and window[0] < cutoff:
            window.popleft()

        # Check limit
        if len(window) < limit:
            window.append(now)
            return True, limit - len(window)

        return False, 0

    async def check_token_bucket(
        self,
        key: str,
        limit: int,
        burst: int,
        refill_rate: float
    ) -> tuple[bool, int]:
        """Check token bucket quota"""
        now = time.time()

        if key not in self._token_buckets:
            self._token_buckets[key] = (float(burst), now)

        tokens, last_update = self._token_buckets[key]

        # Refill tokens
        elapsed = now - last_update
        tokens = min(float(burst), tokens + (elapsed * refill_rate))

        # Check if token available
        if tokens >= 1.0:
            self._token_buckets[key] = (tokens - 1.0, now)
            return True, int(tokens - 1.0)

        self._token_buckets[key] = (tokens, now)
        return False, 0


class RedisQuotaBackend:
    """Redis-backed quota tracking (distributed)"""

    def __init__(self, redis_url: str):
        if not REDIS_AVAILABLE:
            raise RuntimeError("Redis not available")
        self.redis_url = redis_url
        self.client: redis.Redis | None = None

    async def initialize(self):
        """Initialize Redis connection"""
        self.client = redis.from_url(self.redis_url, decode_responses=True)

    async def close(self):
        """Close Redis connection"""
        if self.client:
            await self.client.close()

    async def check_fixed_window(
        self,
        key: str,
        window_seconds: int,
        limit: int
    ) -> tuple[bool, int]:
        """Check fixed window quota (Redis)"""
        now = int(time.time())
        window_start = (now // window_seconds) * window_seconds
        redis_key = f"quota:fixed:{key}:{window_start}"

        # Increment counter
        count = await self.client.incr(redis_key)

        # Set expiry on first access
        if count == 1:
            await self.client.expire(redis_key, window_seconds)

        if count <= limit:
            return True, limit - count

        return False, 0

    async def check_sliding_window(
        self,
        key: str,
        window_seconds: int,
        limit: int
    ) -> tuple[bool, int]:
        """Check sliding window quota (Redis sorted set)"""
        now = time.time()
        cutoff = now - window_seconds
        redis_key = f"quota:sliding:{key}"

        # Remove old entries
        await self.client.zremrangebyscore(redis_key, 0, cutoff)

        # Count entries in window
        count = await self.client.zcard(redis_key)

        if count < limit:
            # Add new entry
            await self.client.zadd(redis_key, {str(now): now})
            await self.client.expire(redis_key, window_seconds)
            return True, limit - (count + 1)

        return False, 0

    async def check_token_bucket(
        self,
        key: str,
        limit: int,
        burst: int,
        refill_rate: float
    ) -> tuple[bool, int]:
        """Check token bucket quota (Redis with Lua script)"""
        # Lua script for atomic token bucket check
        lua_script = """
        local key = KEYS[1]
        local burst = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])

        local bucket = redis.call('HMGET', key, 'tokens', 'last_update')
        local tokens = tonumber(bucket[1]) or burst
        local last_update = tonumber(bucket[2]) or now

        -- Refill tokens
        local elapsed = now - last_update
        tokens = math.min(burst, tokens + (elapsed * refill_rate))

        -- Check if token available
        if tokens >= 1.0 then
            redis.call('HMSET', key, 'tokens', tokens - 1.0, 'last_update', now)
            redis.call('EXPIRE', key, 60)
            return {1, math.floor(tokens - 1.0)}
        end

        redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
        redis.call('EXPIRE', key, 60)
        return {0, 0}
        """

        redis_key = f"quota:bucket:{key}"
        now = time.time()

        result = await self.client.eval(
            lua_script,
            1,
            redis_key,
            str(burst),
            str(refill_rate),
            str(now)
        )

        allowed = bool(result[0])
        remaining = int(result[1])

        return allowed, remaining


class QuotaGuard:
    """
    Unified quota guard combining temporal and rate limiting

    Example:
        ```python
        # Per-user rate limit: 100 requests per minute with burst of 20
        quota = QuotaGuard(
            key=lambda ctx: (ctx.get('tenant_id'), ctx.get('user_id')),
            window_s=60,
            limit=100,
            burst=20,
            backend="redis",
            redis_url="redis://localhost:6379"
        )

        guard = quota.create_guard()
        ```
    """

    def __init__(
        self,
        key: Callable[[Ctx], tuple[str, ...]] | Callable[[Ctx], str],
        window_s: int,
        limit: int,
        burst: int | None = None,
        mode: Literal["fixed", "sliding", "token_bucket"] = "sliding",
        backend: Literal["memory", "redis"] = "memory",
        redis_url: str | None = None
    ):
        """
        Initialize quota guard

        Args:
            key: Function to extract quota key from context
            window_s: Window size in seconds
            limit: Maximum requests in window
            burst: Burst allowance (defaults to limit)
            mode: Window mode (fixed/sliding/token_bucket)
            backend: Storage backend (memory/redis)
            redis_url: Redis URL (required if backend="redis")
        """
        self.key_fn = key
        self.window_s = window_s
        self.limit = limit
        self.burst = burst if burst is not None else limit
        self.mode = mode
        self.backend_type = backend

        # Initialize backend
        if backend == "memory":
            self.backend = MemoryQuotaBackend()
        elif backend == "redis":
            if not redis_url:
                raise ValueError("redis_url required for Redis backend")
            self.backend = RedisQuotaBackend(redis_url)
        else:
            raise ValueError(f"Unknown backend: {backend}")

    async def initialize(self):
        """Initialize backend (call before use)"""
        if hasattr(self.backend, 'initialize'):
            await self.backend.initialize()

    async def close(self):
        """Close backend"""
        if hasattr(self.backend, 'close'):
            await self.backend.close()

    def _extract_key(self, ctx: Ctx) -> str:
        """Extract quota key from context"""
        key_parts = self.key_fn(ctx)

        if isinstance(key_parts, str):
            return key_parts

        # Join tuple into key
        return ":".join(str(p) for p in key_parts)

    def create_guard(self) -> Guard:
        """Create guard function"""

        async def quota_guard(ctx: Ctx) -> Either:
            # Extract quota key
            key = self._extract_key(ctx)

            # Check quota based on mode
            if self.mode == "fixed":
                allowed, remaining = await self.backend.check_fixed_window(
                    key, self.window_s, self.limit
                )
            elif self.mode == "sliding":
                allowed, remaining = await self.backend.check_sliding_window(
                    key, self.window_s, self.limit
                )
            elif self.mode == "token_bucket":
                refill_rate = self.limit / self.window_s
                allowed, remaining = await self.backend.check_token_bucket(
                    key, self.limit, self.burst, refill_rate
                )
            else:
                raise ValueError(f"Unknown mode: {self.mode}")

            if allowed:
                # Add quota metadata to context
                ctx["_quota_remaining"] = remaining
                return Right_(ctx)

            # Quota exceeded
            return Left_([Violation(
                rule_id="quota.exceeded",
                severity="med",
                message=f"Quota exceeded for key '{key}': {self.limit} per {self.window_s}s",
                span={
                    "quota_key": key,
                    "limit": self.limit,
                    "window_seconds": self.window_s,
                    "mode": self.mode,
                    "remaining": remaining
                }
            )])

        return quota_guard

