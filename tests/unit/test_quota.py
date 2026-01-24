"""
Tests for unified quota guard system
"""


import pytest

from heimdall.quota import MemoryQuotaBackend, QuotaConfig, QuotaGuard
from heimdall.types import is_left, is_right


@pytest.mark.asyncio
async def test_memory_backend_fixed_window():
    """Test fixed window quota tracking"""
    backend = MemoryQuotaBackend()

    # First request should pass
    allowed, remaining = await backend.check_fixed_window("user:123", window_seconds=60, limit=10)
    assert allowed is True
    assert remaining == 9

    # Subsequent requests
    for _i in range(9):
        allowed, remaining = await backend.check_fixed_window("user:123", window_seconds=60, limit=10)
        assert allowed is True

    # 11th request should fail
    allowed, remaining = await backend.check_fixed_window("user:123", window_seconds=60, limit=10)
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_memory_backend_sliding_window():
    """Test sliding window quota tracking"""
    backend = MemoryQuotaBackend()

    # Fill up quota
    for _i in range(5):
        allowed, remaining = await backend.check_sliding_window("user:456", window_seconds=60, limit=5)
        assert allowed is True

    # 6th request should fail
    allowed, remaining = await backend.check_sliding_window("user:456", window_seconds=60, limit=5)
    assert allowed is False


@pytest.mark.asyncio
async def test_memory_backend_token_bucket():
    """Test token bucket quota tracking"""
    backend = MemoryQuotaBackend()

    # Should start with full bucket
    allowed, remaining = await backend.check_token_bucket(
        "user:789", limit=10, burst=10, refill_rate=1.0
    )
    assert allowed is True
    assert remaining > 0


@pytest.mark.asyncio
async def test_quota_guard_creation():
    """Test creating quota guard"""
    quota = QuotaGuard(
        key=lambda ctx: ctx.get("user_id", "default"),
        window_s=60,
        limit=10,
        backend="memory"
    )

    guard = quota.create_guard()
    assert callable(guard)


@pytest.mark.asyncio
async def test_quota_guard_allows_within_limit():
    """Test quota guard allows requests within limit"""
    quota = QuotaGuard(
        key=lambda ctx: "test_user",
        window_s=60,
        limit=5,
        mode="sliding",
        backend="memory"
    )

    guard = quota.create_guard()

    # First 5 requests should pass
    for _i in range(5):
        result = await guard({"user_id": "test_user"})
        assert is_right(result)


@pytest.mark.asyncio
async def test_quota_guard_blocks_over_limit():
    """Test quota guard blocks requests over limit"""
    quota = QuotaGuard(
        key=lambda ctx: "test_user",
        window_s=60,
        limit=3,
        mode="sliding",
        backend="memory"
    )

    guard = quota.create_guard()

    # First 3 requests should pass
    for _i in range(3):
        result = await guard({"user_id": "test_user"})
        assert is_right(result)

    # 4th request should be blocked
    result = await guard({"user_id": "test_user"})
    assert is_left(result)


@pytest.mark.asyncio
async def test_quota_guard_per_user():
    """Test quota guard tracks per user"""
    quota = QuotaGuard(
        key=lambda ctx: ctx.get("user_id", "default"),
        window_s=60,
        limit=2,
        mode="sliding",
        backend="memory"
    )

    guard = quota.create_guard()

    # User 1: 2 requests (at limit)
    for _i in range(2):
        result = await guard({"user_id": "user1"})
        assert is_right(result)

    # User 1: 3rd request should fail
    result = await guard({"user_id": "user1"})
    assert is_left(result)

    # User 2: Should still be allowed
    result = await guard({"user_id": "user2"})
    assert is_right(result)


@pytest.mark.asyncio
async def test_quota_guard_tuple_key():
    """Test quota guard with tuple key"""
    quota = QuotaGuard(
        key=lambda ctx: (ctx.get("tenant_id"), ctx.get("user_id")),
        window_s=60,
        limit=5,
        backend="memory"
    )

    guard = quota.create_guard()

    result = await guard({"tenant_id": "tenant1", "user_id": "user1"})
    assert is_right(result)


@pytest.mark.asyncio
async def test_quota_guard_adds_metadata():
    """Test that quota guard adds remaining count to context"""
    quota = QuotaGuard(
        key=lambda ctx: "test",
        window_s=60,
        limit=10,
        backend="memory"
    )

    guard = quota.create_guard()

    result = await guard({"test": "data"})
    assert is_right(result)

    # Check metadata was added
    ctx = result["right"]
    assert "_quota_remaining" in ctx


@pytest.mark.asyncio
async def test_quota_config():
    """Test QuotaConfig dataclass"""
    config = QuotaConfig(
        window_seconds=60,
        limit=100,
        burst=20,
        mode="token_bucket",
        backend="memory"
    )

    assert config.window_seconds == 60
    assert config.limit == 100
    assert config.burst == 20
    assert config.mode == "token_bucket"


@pytest.mark.asyncio
async def test_quota_config_default_burst():
    """Test QuotaConfig default burst value"""
    config = QuotaConfig(
        window_seconds=60,
        limit=100
    )

    assert config.burst == 100  # Should default to limit

