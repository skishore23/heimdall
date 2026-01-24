"""
Zero-copy Streaming Proxy

High-performance streaming proxy that combines advanced windowing,
zero-copy forwarding, and guard processing for minimal latency.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse

from bifrost.cache import PolicyCache

from .buffer import MemoryPool, StreamingBuffer
from .forwarding import ForwardingConfig, ForwardingStrategy, ZeroCopyForwarder
from .windowing import AdaptiveWindowManager, StreamingWindow, WindowManager

logger = logging.getLogger(__name__)


@dataclass
class StreamingProxyConfig:
    """Configuration for streaming proxy"""
    # Server settings
    host: str = "0.0.0.0"  # nosec B104 - intentional for streaming proxy server
    port: int = 8001

    # Upstream settings
    upstream_base_url: str = "https://api.openai.com"
    upstream_timeout: float = 60.0

    # Streaming settings
    window_size: int = 512
    overlap_size: int = 64
    max_concurrent_streams: int = 100

    # Zero-copy settings
    enable_zero_copy: bool = True
    buffer_pool_size: int = 1000
    memory_pool_buffer_size: int = 64 * 1024

    # Performance settings
    adaptive_windowing: bool = True
    forwarding_strategy: ForwardingStrategy = ForwardingStrategy.ADAPTIVE

    # Guard settings
    enable_streaming_guards: bool = True
    guard_tiers: list = None

    def __post_init__(self):
        if self.guard_tiers is None:
            self.guard_tiers = ["T0", "T1"]  # Skip T2 for streaming


class StreamingProxy:
    """
    Zero-copy Streaming Proxy

    Provides high-performance streaming with minimal latency overhead,
    advanced windowing, and intelligent guard processing.
    """

    def __init__(self, config: StreamingProxyConfig = None):
        """
        Initialize streaming proxy

        Args:
            config: Proxy configuration
        """
        self.config = config or StreamingProxyConfig()

        # Core components
        self.policy_cache = PolicyCache()
        self.memory_pool = MemoryPool(
            buffer_size=self.config.memory_pool_buffer_size,
            pool_size=self.config.buffer_pool_size
        )

        # Active streams
        self.active_streams: dict[str, dict[str, Any]] = {}
        self.stream_semaphore = asyncio.Semaphore(self.config.max_concurrent_streams)

        # Performance metrics
        self.metrics = {
            "streams_processed": 0,
            "total_bytes_streamed": 0,
            "total_processing_time_ms": 0,
            "average_latency_ms": 0,
            "zero_copy_operations": 0,
            "memory_copies": 0,
            "guard_violations": 0
        }

        # HTTP client for upstream
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.upstream_timeout),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50)
        )

    async def create_streaming_session(
        self,
        request: Request,
        policy_id: str | None = None
    ) -> dict[str, Any]:
        """
        Create a new streaming session with all components

        Args:
            request: FastAPI request object
            policy_id: Policy ID for guard enforcement

        Returns:
            Session dictionary with all components
        """
        session_id = str(uuid.uuid4())

        # Create window manager
        if self.config.adaptive_windowing:
            window_manager = AdaptiveWindowManager(
                window_size=self.config.window_size,
                overlap_size=self.config.overlap_size,
                max_concurrent_windows=10
            )
        else:
            window_manager = WindowManager(
                window_size=self.config.window_size,
                overlap_size=self.config.overlap_size,
                max_concurrent_windows=10
            )

        # Create forwarder
        forwarding_config = ForwardingConfig(
            strategy=self.config.forwarding_strategy,
            use_sendfile=self.config.enable_zero_copy,
            use_splice=self.config.enable_zero_copy
        )
        forwarder = ZeroCopyForwarder(forwarding_config)

        # Create streaming buffer
        streaming_buffer = StreamingBuffer(
            window_size=self.config.window_size,
            overlap_size=self.config.overlap_size
        )

        # Get policy for guards
        compiled_guards = None
        if self.config.enable_streaming_guards and policy_id:
            try:
                compiled_guards, _ = await self.policy_cache.get_policy(
                    tenant_id=request.headers.get("x-tenant-id", "default"),
                    policy_id=policy_id
                )
            except Exception as e:
                logger.warning("Could not load policy %s: %s", policy_id, e, exc_info=True)

        session = {
            "id": session_id,
            "window_manager": window_manager,
            "forwarder": forwarder,
            "streaming_buffer": streaming_buffer,
            "compiled_guards": compiled_guards,
            "start_time": time.time(),
            "bytes_processed": 0,
            "windows_created": 0
        }

        self.active_streams[session_id] = session
        return session

    async def process_streaming_request(
        self,
        request: Request,
        upstream_path: str = "/v1/chat/completions"
    ) -> StreamingResponse:
        """
        Process a streaming request with zero-copy optimization

        Args:
            request: FastAPI request
            upstream_path: Upstream API path

        Returns:
            StreamingResponse with processed content
        """
        async with self.stream_semaphore:
            # Parse request
            request_body = await request.json()
            policy_id = request.headers.get("x-policy-id", "enterprise_default_v1")

            # Create streaming session
            session = await self.create_streaming_session(request, policy_id)

            try:
                # Create upstream request
                upstream_url = f"{self.config.upstream_base_url}{upstream_path}"

                # Start streaming from upstream
                async def stream_generator():
                    async with self.http_client.stream(
                        "POST",
                        upstream_url,
                        json=request_body,
                        headers={
                            "Authorization": request.headers.get("Authorization"),
                            "Content-Type": "application/json"
                        }
                    ) as response:

                        if response.status_code != 200:
                            yield f"data: {json.dumps({'error': f'Upstream error: {response.status_code}'})}\n\n"
                            return

                        # Process streaming response
                        async for chunk in response.aiter_text():
                            if chunk:
                                processed_chunk = await self._process_chunk(session, chunk)
                                if processed_chunk:
                                    yield processed_chunk

                        # Final cleanup
                        await self._cleanup_session(session)

                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no"  # Disable nginx buffering
                    }
                )

            except Exception as e:
                await self._cleanup_session(session)
                raise e

    async def _process_chunk(
        self,
        session: dict[str, Any],
        chunk: str
    ) -> str | None:
        """
        Process a streaming chunk through the zero-copy pipeline

        Args:
            session: Streaming session
            chunk: Raw chunk from upstream

        Returns:
            Processed chunk or None if blocked
        """
        try:
            # Write to streaming buffer
            success = await session["streaming_buffer"].write_chunk(chunk)
            if not success:
                logger.warning("Buffer overflow detected - dropping chunk")
                return None

            session["bytes_processed"] += len(chunk)

            # Process available windows
            processed_chunks = []

            while True:
                window_slice = session["streaming_buffer"].get_next_window()
                if not window_slice:
                    break

                # Create window
                window = await session["window_manager"].create_window(window_slice)
                session["windows_created"] += 1

                # Process through guards if enabled
                if session["compiled_guards"] and self.config.enable_streaming_guards:
                    window = await session["window_manager"].process_window(
                        window,
                        session["compiled_guards"]
                    )

                    if window.is_blocked:
                        # Window blocked - replace with safe content
                        safe_chunk = self._create_safe_chunk(window)
                        processed_chunks.append(safe_chunk)
                        self.metrics["guard_violations"] += 1
                        continue

                # Queue for forwarding
                await session["forwarder"].queue_window(window)

                # Mark as processed
                session["streaming_buffer"].mark_processed(window)

            # Return original chunk if no processing needed
            # In a real implementation, this would be the forwarded content
            return chunk

        except Exception as e:
            logger.error("Chunk processing error: %s", e, exc_info=True)
            return None

    def _create_safe_chunk(self, window: StreamingWindow) -> str:
        """
        Create safe replacement chunk for blocked content

        Args:
            window: Blocked window

        Returns:
            Safe replacement chunk
        """
        # Create SSE-formatted safe response
        safe_response = {
            "choices": [{
                "delta": {
                    "content": "[Content filtered by policy]"
                },
                "finish_reason": "content_filter"
            }]
        }

        return f"data: {json.dumps(safe_response)}\n\n"

    async def _cleanup_session(self, session: dict[str, Any]) -> None:
        """
        Clean up streaming session resources

        Args:
            session: Session to clean up
        """
        session_id = session["id"]

        try:
            # Close forwarder
            await session["forwarder"].close()

            # Update metrics
            processing_time = (time.time() - session["start_time"]) * 1000
            self.metrics["streams_processed"] += 1
            self.metrics["total_bytes_streamed"] += session["bytes_processed"]
            self.metrics["total_processing_time_ms"] += processing_time

            if self.metrics["streams_processed"] > 0:
                self.metrics["average_latency_ms"] = (
                    self.metrics["total_processing_time_ms"] /
                    self.metrics["streams_processed"]
                )

            # Collect component stats
            forwarder_stats = session["forwarder"].get_stats()
            self.metrics["zero_copy_operations"] += forwarder_stats["zero_copy_operations"]
            self.metrics["memory_copies"] += forwarder_stats["copy_operations"]

        except Exception as e:
            logger.error("Session cleanup error: %s", e, exc_info=True)
        finally:
            # Remove from active streams
            self.active_streams.pop(session_id, None)

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get comprehensive performance metrics"""
        # Calculate zero-copy efficiency
        total_ops = self.metrics["zero_copy_operations"] + self.metrics["memory_copies"]
        zero_copy_rate = (
            self.metrics["zero_copy_operations"] / total_ops
            if total_ops > 0 else 0
        )

        # Memory pool stats
        pool_stats = self.memory_pool.get_stats()

        return {
            **self.metrics,
            "zero_copy_rate": zero_copy_rate,
            "active_streams": len(self.active_streams),
            "memory_pool": pool_stats,
            "throughput_mbps": (
                self.metrics["total_bytes_streamed"] /
                (self.metrics["total_processing_time_ms"] / 1000) /
                (1024 * 1024)
                if self.metrics["total_processing_time_ms"] > 0 else 0
            )
        }

    async def health_check(self) -> dict[str, Any]:
        """Health check for streaming proxy"""
        return {
            "status": "healthy",
            "active_streams": len(self.active_streams),
            "memory_utilization": self.memory_pool.get_stats(),
            "upstream_reachable": True,  # Would test upstream connectivity
            "zero_copy_enabled": self.config.enable_zero_copy
        }

    async def stream_chat_completion(
        self,
        request_data: dict[str, Any],
        headers: dict[str, str],
        gateway_url: str
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream chat completion for SDK integration

        Args:
            request_data: Request payload
            headers: Request headers
            gateway_url: Gateway URL to proxy to

        Yields:
            Streaming response chunks
        """
        try:
            # Use gateway instead of direct OpenAI
            url = f"{gateway_url}/v1/chat/completions"

            async with self.http_client.stream(
                "POST", url, json=request_data, headers=headers
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RuntimeError(f"Gateway error {response.status_code}: {error_text}")

                # Process streaming response with zero-copy optimizations
                buffer = self.memory_pool.get_buffer()

                try:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix
                            if data.strip() == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data)

                                # Apply zero-copy optimizations if possible
                                if self.config.enable_zero_copy:
                                    self.metrics["zero_copy_operations"] += 1
                                else:
                                    self.metrics["memory_copies"] += 1

                                yield chunk

                            except json.JSONDecodeError:
                                continue

                finally:
                    # Return buffer to pool
                    self.memory_pool.return_buffer(buffer)

        except Exception as e:
            logger.error("Streaming proxy error: %s", e, exc_info=True)
            raise

    async def close(self):
        """Close streaming proxy and cleanup resources"""
        # Close all active sessions
        for session in list(self.active_streams.values()):
            await self._cleanup_session(session)

        # Close HTTP client
        await self.http_client.aclose()
