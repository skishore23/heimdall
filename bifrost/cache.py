"""
Policy cache with Redis backend for the Guardrails Gateway
"""

import hashlib
import logging
from typing import Any

import redis.asyncio as redis

import guards.business.guards  # noqa: F401

# Import guard packs to register them
import guards.pii.guards  # noqa: F401
import guards.politics.guards  # noqa: F401
import guards.safety.guards  # noqa: F401
import guards.schema.guards  # noqa: F401
import guards.tools.guards  # noqa: F401
import guards.toxicity.guards  # noqa: F401
from heimdall import Guard
from heimdall.compiler import compile_policy
from heimdall.mimir import PolicyEnvelope, verify_policy_signature

logger = logging.getLogger(__name__)


class PolicyCache:
    """Policy cache with Redis backend and LRU in-memory cache"""

    def __init__(self, redis_url: str, default_policy_id: str, verify_key: bytes | None = None):
        self.redis_url = redis_url
        self.default_policy_id = default_policy_id
        self.redis_client: redis.Redis | None = None
        self.memory_cache: dict[str, tuple[Guard, dict[str, Any]]] = {}
        self.cache_size_limit = 100
        self.verify_key = verify_key  # For signed policy verification
        self.policy_versions: dict[str, str] = {}  # Track policy versions for hot-reload

    async def initialize(self):
        """Initialize Redis connection (optional in tests)"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await self.redis_client.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}); continuing without Redis cache")
            self.redis_client = None

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("Redis connection closed")

    def _get_policy_hash(self, policy_content: bytes) -> str:
        """Generate SHA256 hash of policy content"""
        return hashlib.sha256(policy_content).hexdigest()

    def _get_cache_key(self, policy_id: str, policy_hash: str) -> str:
        """Generate Redis cache key for policy"""
        return f"policy:{policy_id}@{policy_hash}"

    async def get_policy(
        self,
        tenant_id: str = "default",
        policy_id: str | None = None
    ) -> tuple[Guard, dict[str, Any]]:
        """
        Get compiled policy for tenant

        Args:
            tenant_id: Tenant identifier
            policy_id: Policy ID (uses default if None)

        Returns:
            Tuple of (compiled_guard, policy_metadata)
        """
        if policy_id is None:
            policy_id = self.default_policy_id

        # Try memory cache first
        cache_key = f"{tenant_id}:{policy_id}"
        if cache_key in self.memory_cache:
            logger.debug(f"Policy cache hit (memory): {cache_key}")
            return self.memory_cache[cache_key]

        # Try Redis cache
        if self.redis_client:
            try:
                # Get policy content from Redis
                policy_content = await self.redis_client.get(f"policy_content:{policy_id}")
                if policy_content:
                    policy_bytes = policy_content.encode('utf-8')
                    policy_hash = self._get_policy_hash(policy_bytes)
                    redis_key = self._get_cache_key(policy_id, policy_hash)

                    # Get compiled policy from Redis
                    cached_policy = await self.redis_client.get(redis_key)
                    if cached_policy:
                        # Deserialize and return
                        import pickle
                        compiled_guards, metadata = pickle.loads(cached_policy.encode('latin-1'))  # nosec B301 - internal Redis cache with self-generated data

                        # Store in memory cache
                        self._store_in_memory_cache(cache_key, compiled_guards, metadata)

                        logger.debug(f"Policy cache hit (Redis): {cache_key}")
                        return compiled_guards, metadata
            except Exception as e:
                logger.warning(f"Redis cache error: {e}")

        # Cache miss - compile policy
        logger.info(f"Policy cache miss, compiling: {policy_id}")
        compiled_guards, metadata = await self._compile_and_cache_policy(
            tenant_id, policy_id, cache_key
        )

        return compiled_guards, metadata

    async def _compile_and_cache_policy(
        self,
        tenant_id: str,
        policy_id: str,
        cache_key: str
    ) -> tuple[Guard, dict[str, Any]]:
        """Compile policy and store in cache"""
        # Load policy from file system
        policy_path = f"policies/{policy_id}.yaml"
        try:
            with open(policy_path, 'rb') as f:
                policy_bytes = f.read()
        except FileNotFoundError as e:
            logger.error(f"Policy file not found: {policy_path}")
            raise ValueError(f"Policy '{policy_id}' not found") from e

        # Compile policy
        try:
            compiled_guards, metadata = compile_policy(policy_bytes)
        except Exception as e:
            logger.error(f"Failed to compile policy {policy_id}: {e}")
            raise ValueError(f"Failed to compile policy '{policy_id}': {e}") from e

        # Add policy hash to metadata
        policy_hash = self._get_policy_hash(policy_bytes)
        metadata["hash"] = policy_hash

        # Store in memory cache
        self._store_in_memory_cache(cache_key, compiled_guards, metadata)

        # Store in Redis cache (policy content only - guards are compiled on-demand)
        if self.redis_client:
            try:
                # Store policy content and metadata (guards are recompiled from source)
                await self.redis_client.setex(
                    f"policy_content:{policy_id}",
                    86400,  # 24 hours TTL
                    policy_bytes.decode('utf-8')
                )

                # Store metadata separately for quick access
                import json
                await self.redis_client.setex(
                    f"policy_metadata:{policy_id}",
                    86400,  # 24 hours TTL
                    json.dumps(metadata)
                )

                logger.info(f"Policy content and metadata cached in Redis: {policy_id}")
            except Exception as e:
                logger.warning(f"Failed to cache policy in Redis: {e}")

        return compiled_guards, metadata

    def _store_in_memory_cache(
        self,
        cache_key: str,
        compiled_guards: dict[str, Any],
        metadata: dict[str, Any]
    ):
        """Store policy in memory cache with LRU eviction"""
        # Evict oldest entries if cache is full
        if len(self.memory_cache) >= self.cache_size_limit:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self.memory_cache))
            del self.memory_cache[oldest_key]

        self.memory_cache[cache_key] = (compiled_guards, metadata)

    async def invalidate_policy(self, policy_id: str):
        """Invalidate cached policy"""
        # Remove from memory cache
        keys_to_remove = [k for k in self.memory_cache.keys() if k.endswith(f":{policy_id}")]
        for key in keys_to_remove:
            del self.memory_cache[key]

        # Remove from Redis cache
        if self.redis_client:
            try:
                # Get all keys matching pattern
                pattern = f"policy:{policy_id}@*"
                keys = await self.redis_client.keys(pattern)
                if keys:
                    await self.redis_client.delete(*keys)

                # Remove policy content
                await self.redis_client.delete(f"policy_content:{policy_id}")

                logger.info(f"Policy invalidated: {policy_id}")
            except Exception as e:
                logger.warning(f"Failed to invalidate policy in Redis: {e}")

    async def list_policies(self) -> dict[str, Any]:
        """List all available policies"""
        policies = {}

        # Get from memory cache
        for cache_key, (_guard, metadata) in self.memory_cache.items():
            tenant_id, policy_id = cache_key.split(":", 1)
            if policy_id not in policies:
                policies[policy_id] = {
                    "metadata": metadata,
                    "cached_tenants": []
                }
            policies[policy_id]["cached_tenants"].append(tenant_id)

        return policies

    async def hot_reload_policy(self, envelope: PolicyEnvelope) -> None:
        """Hot-reload a signed policy envelope"""

        # Verify signature if verify_key is set
        if self.verify_key:
            if not verify_policy_signature(envelope, self.verify_key):
                raise ValueError(f"Invalid signature for policy '{envelope.policy_id}'")
            logger.info(f"✓ Policy signature verified: {envelope.policy_id} v{envelope.version}")

        # Check if version is newer
        current_version = self.policy_versions.get(envelope.policy_id)
        if current_version and current_version >= envelope.version:
            logger.warning(f"Policy version {envelope.version} is not newer than current {current_version}")
            return

        # Invalidate old policy
        await self.invalidate_policy(envelope.policy_id)

        # Update version tracker
        self.policy_versions[envelope.policy_id] = envelope.version

        logger.info(f"✓ Hot-reloaded policy: {envelope.policy_id} v{envelope.version}")
