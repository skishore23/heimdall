"""
Enhanced Streaming SDK

Integrates zero-copy streaming proxy with guardrails for high-performance
real-time content moderation.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import HeimdallSDK, SDKConfig

logger = logging.getLogger(__name__)


@dataclass
class StreamingConfig:
    """Configuration for streaming operations"""
    buffer_size: int = 8192
    window_size: int = 1024
    chunk_size: int = 512
    performance_budget_ms: float = 100.0
    enable_zero_copy: bool = True
    enable_adaptive_windowing: bool = True
    enable_guard_streaming: bool = True
    guard_frequency: int = 5  # Run guards every N chunks


class StreamingGuardrailsSDK(HeimdallSDK):
    """
    Enhanced SDK with advanced streaming capabilities

    Features:
    - Zero-copy streaming proxy integration
    - Per-token guard evaluation
    - Adaptive windowing for context preservation
    - Real-time violation detection
    - Streaming policy enforcement
    """

    def __init__(self, config: SDKConfig | None = None, streaming_config: StreamingConfig | None = None):
        super().__init__(config)
        self.streaming_config = streaming_config or StreamingConfig()
        self.streaming_proxy = None
        self.active_streams = {}

        # Initialize enhanced streaming proxy
        if self.streaming_config.enable_zero_copy:
            self._init_enhanced_streaming_proxy()

    def _init_enhanced_streaming_proxy(self):
        """Initialize enhanced zero-copy streaming proxy"""
        try:
            from streaming_proxy.buffer import StreamingBuffer
            from streaming_proxy.proxy import ZeroCopyStreamingProxy
            from streaming_proxy.windowing import AdaptiveWindowManager

            # Create streaming buffer
            buffer = StreamingBuffer(
                size=self.streaming_config.buffer_size,
                chunk_size=self.streaming_config.chunk_size
            )

            # Create adaptive window manager
            window_manager = AdaptiveWindowManager(
                initial_size=self.streaming_config.window_size,
                max_size=self.streaming_config.window_size * 4,
                performance_budget_ms=self.streaming_config.performance_budget_ms
            ) if self.streaming_config.enable_adaptive_windowing else None

            # Initialize proxy
            self.streaming_proxy = ZeroCopyStreamingProxy(
                buffer=buffer,
                window_manager=window_manager,
                performance_budget_ms=self.streaming_config.performance_budget_ms
            )

            logger.info("Enhanced streaming proxy initialized")

        except ImportError as e:
            logger.warning("Enhanced streaming proxy not available: %s", e)
            self.streaming_proxy = None

    async def stream_chat_with_guards(
        self,
        messages: list[dict[str, str]],
        policy_id: str,
        model: str = "gpt-3.5-turbo",
        **kwargs
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream chat completion with real-time guard evaluation

        Args:
            messages: Chat messages
            policy_id: Policy to apply
            model: Model to use
            **kwargs: Additional OpenAI parameters

        Yields:
            Streaming chunks with guard status
        """
        if policy_id not in self.loaded_policies:
            raise ValueError(f"Policy not loaded: {policy_id}")

        policy = self.loaded_policies[policy_id]
        compiled_guards = policy["compiled"]

        # Run input guards first
        input_context = {
            "phase": "input",
            "messages": messages,
            **kwargs
        }

        input_guard = compiled_guards.get("input")
        if input_guard:
            input_result = await input_guard(input_context)
            if input_result.get("_tag") == "Left":
                violations = input_result.get("left", [])
                yield {
                    "type": "guard_violation",
                    "phase": "input",
                    "violations": violations,
                    "blocked": True
                }
                return

        # Start streaming with output guards
        stream_id = f"stream_{asyncio.get_event_loop().time()}"
        self.active_streams[stream_id] = {
            "policy_id": policy_id,
            "accumulated_text": "",
            "chunk_count": 0,
            "guard_results": []
        }

        try:
            # Stream chat completion
            async for chunk in self.chat_completion(
                messages=messages,
                model=model,
                policy_id=policy_id,
                stream=True,
                **kwargs
            ):
                # Process chunk
                processed_chunk = await self._process_streaming_chunk(
                    chunk, stream_id, compiled_guards
                )

                if processed_chunk:
                    yield processed_chunk

                    # Check if chunk was blocked
                    if processed_chunk.get("blocked"):
                        break

        finally:
            # Clean up stream
            if stream_id in self.active_streams:
                del self.active_streams[stream_id]

    async def _process_streaming_chunk(
        self,
        chunk: dict[str, Any],
        stream_id: str,
        compiled_guards: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Process a streaming chunk with guard evaluation

        Args:
            chunk: Streaming chunk from LLM
            stream_id: Stream identifier
            compiled_guards: Compiled policy guards

        Returns:
            Processed chunk with guard information
        """
        stream_state = self.active_streams.get(stream_id)
        if not stream_state:
            return chunk

        # Extract content from chunk
        content = ""
        if "choices" in chunk and chunk["choices"]:
            choice = chunk["choices"][0]
            if "delta" in choice and "content" in choice["delta"]:
                content = choice["delta"]["content"]

        if not content:
            return chunk

        # Update accumulated text
        stream_state["accumulated_text"] += content
        stream_state["chunk_count"] += 1

        # Run guards periodically or if streaming guards are enabled
        should_run_guards = (
            self.streaming_config.enable_guard_streaming and
            (stream_state["chunk_count"] % self.streaming_config.guard_frequency == 0)
        )

        guard_result = None
        if should_run_guards:
            guard_result = await self._run_streaming_guards(
                stream_state["accumulated_text"],
                compiled_guards
            )

            if guard_result and guard_result.get("violations"):
                # Block the stream
                return {
                    "type": "guard_violation",
                    "phase": "output_streaming",
                    "violations": guard_result["violations"],
                    "blocked": True,
                    "accumulated_text": stream_state["accumulated_text"],
                    "chunk_count": stream_state["chunk_count"]
                }

        # Return enhanced chunk with guard information
        enhanced_chunk = chunk.copy()
        enhanced_chunk.update({
            "guard_status": "checked" if should_run_guards else "pending",
            "accumulated_length": len(stream_state["accumulated_text"]),
            "chunk_count": stream_state["chunk_count"]
        })

        if guard_result:
            enhanced_chunk["guard_result"] = guard_result

        return enhanced_chunk

    async def _run_streaming_guards(
        self,
        accumulated_text: str,
        compiled_guards: dict[str, Any]
    ) -> dict[str, Any] | None:
        """
        Run guards on accumulated streaming text

        Args:
            accumulated_text: Text accumulated so far
            compiled_guards: Compiled policy guards

        Returns:
            Guard result with violations if any
        """
        output_guard = compiled_guards.get("output")
        if not output_guard:
            return None

        # Create context for output guard
        output_context = {
            "phase": "output_streaming",
            "output": accumulated_text
        }

        try:
            # Run guard with timeout for streaming performance
            result = await asyncio.wait_for(
                output_guard(output_context),
                timeout=self.streaming_config.performance_budget_ms / 1000.0
            )

            # Either type from regular guard
            if result.get("_tag") == "Left":
                violations = result.get("left", [])
                return {
                    "status": "blocked",
                    "violations": violations,
                    "text_length": len(accumulated_text)
                }
            else:
                return {
                    "status": "passed",
                    "text_length": len(accumulated_text)
                }

        except TimeoutError:
            # Guard took too long, allow content through
            return {
                "status": "timeout",
                "text_length": len(accumulated_text),
                "warning": "Guard evaluation timed out"
            }
        except Exception as e:
            # Guard failed, allow content through with warning
            return {
                "status": "error",
                "error": str(e),
                "text_length": len(accumulated_text)
            }

    async def stream_with_zero_copy(
        self,
        messages: list[dict[str, str]],
        policy_id: str | None = None,
        model: str = "gpt-3.5-turbo",
        **kwargs
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream using zero-copy proxy for maximum performance

        Args:
            messages: Chat messages
            policy_id: Optional policy to apply
            model: Model to use
            **kwargs: Additional parameters

        Yields:
            High-performance streaming chunks
        """
        if not self.streaming_proxy:
            # Fallback to standard streaming
            async for chunk in self.chat_completion(
                messages=messages,
                model=model,
                policy_id=policy_id,
                stream=True,
                **kwargs
            ):
                yield chunk
            return

        # Prepare request for zero-copy streaming
        request_data = {
            "model": model,
            "messages": messages,
            "stream": True,
            **kwargs
        }

        headers = {"Content-Type": "application/json"}
        if policy_id:
            headers["X-Policy-ID"] = policy_id
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        # Use zero-copy streaming proxy
        try:
            async for chunk in self.streaming_proxy.stream_chat_completion(
                request_data, headers, self.config.gateway_url
            ):
                yield chunk
        except Exception as e:
            logger.warning("Zero-copy streaming failed, falling back: %s", e)
            # Fallback to standard streaming
            async for chunk in self.chat_completion(
                messages=messages,
                model=model,
                policy_id=policy_id,
                stream=True,
                **kwargs
            ):
                yield chunk

    async def stream_with_adaptive_windowing(
        self,
        messages: list[dict[str, str]],
        policy_id: str,
        model: str = "gpt-3.5-turbo",
        context_preservation: bool = True,
        **kwargs
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream with adaptive windowing for context preservation

        Args:
            messages: Chat messages
            policy_id: Policy to apply
            model: Model to use
            context_preservation: Whether to preserve context across windows
            **kwargs: Additional parameters

        Yields:
            Streaming chunks with adaptive windowing
        """
        if not self.streaming_proxy or not hasattr(self.streaming_proxy, 'window_manager'):
            # Fallback to regular streaming with guards
            async for chunk in self.stream_chat_with_guards(
                messages, policy_id, model, **kwargs
            ):
                yield chunk
            return

        window_manager = self.streaming_proxy.window_manager
        accumulated_content = ""
        window_count = 0

        async for chunk in self.stream_chat_with_guards(
            messages, policy_id, model, **kwargs
        ):
            # Handle guard violations
            if chunk.get("blocked"):
                yield chunk
                break

            # Extract content
            content = ""
            if "choices" in chunk and chunk["choices"]:
                choice = chunk["choices"][0]
                if "delta" in choice and "content" in choice["delta"]:
                    content = choice["delta"]["content"]

            if content:
                accumulated_content += content

                # Check if we need to adjust window size
                if window_manager and len(accumulated_content) > window_manager.current_size:
                    # Adaptive window sizing based on content complexity
                    complexity_score = self._calculate_content_complexity(accumulated_content)
                    new_window_size = window_manager.adjust_window_size(
                        complexity_score,
                        performance_ms=chunk.get("processing_time", 0)
                    )

                    window_count += 1

                    # Add windowing information to chunk
                    chunk["windowing"] = {
                        "window_count": window_count,
                        "window_size": new_window_size,
                        "complexity_score": complexity_score,
                        "content_length": len(accumulated_content)
                    }

            yield chunk

    def _calculate_content_complexity(self, content: str) -> float:
        """
        Calculate content complexity for adaptive windowing

        Args:
            content: Text content to analyze

        Returns:
            Complexity score (0.0 to 1.0)
        """
        if not content:
            return 0.0

        # Simple complexity metrics
        word_count = len(content.split())
        unique_words = len(set(content.lower().split()))
        avg_word_length = sum(len(word) for word in content.split()) / max(word_count, 1)

        # Normalize metrics
        complexity = min(
            (unique_words / max(word_count, 1)) * 0.4 +  # Vocabulary diversity
            (avg_word_length / 10.0) * 0.3 +             # Word complexity
            (len(content) / 1000.0) * 0.3,               # Length factor
            1.0
        )

        return complexity

    async def get_streaming_stats(self) -> dict[str, Any]:
        """Get statistics about active streams"""
        return {
            "active_streams": len(self.active_streams),
            "streaming_proxy_enabled": self.streaming_proxy is not None,
            "zero_copy_enabled": self.streaming_config.enable_zero_copy,
            "adaptive_windowing_enabled": self.streaming_config.enable_adaptive_windowing,
            "guard_streaming_enabled": self.streaming_config.enable_guard_streaming,
            "performance_budget_ms": self.streaming_config.performance_budget_ms,
            "buffer_size": self.streaming_config.buffer_size,
            "window_size": self.streaming_config.window_size
        }

    async def close(self):
        """Clean up streaming resources"""
        # Close active streams
        for stream_id in list(self.active_streams.keys()):
            del self.active_streams[stream_id]

        # Close streaming proxy
        if self.streaming_proxy:
            await self.streaming_proxy.close()

        # Close parent resources
        await super().close()


# Convenience functions for streaming
async def quick_stream_guard(
    messages: list[dict[str, str]],
    policy_path: str,
    model: str = "gpt-3.5-turbo",
    **kwargs
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Quick streaming guard function

    Args:
        messages: Chat messages
        policy_path: Path to policy file
        model: Model to use
        **kwargs: Additional parameters

    Yields:
        Streaming chunks with guard evaluation
    """
    sdk = StreamingGuardrailsSDK()

    try:
        # Load policy
        await sdk.load_policy(policy_path)
        policy_id = Path(policy_path).stem

        # Stream with guards
        async for chunk in sdk.stream_chat_with_guards(
            messages, policy_id, model, **kwargs
        ):
            yield chunk

    finally:
        await sdk.close()


async def quick_zero_copy_stream(
    messages: list[dict[str, str]],
    model: str = "gpt-3.5-turbo",
    **kwargs
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Quick zero-copy streaming function

    Args:
        messages: Chat messages
        model: Model to use
        **kwargs: Additional parameters

    Yields:
        High-performance streaming chunks
    """
    streaming_config = StreamingConfig(enable_zero_copy=True)
    sdk = StreamingGuardrailsSDK(streaming_config=streaming_config)

    try:
        async for chunk in sdk.stream_with_zero_copy(
            messages, model=model, **kwargs
        ):
            yield chunk

    finally:
        await sdk.close()


# Export streaming classes and functions
__all__ = [
    "StreamingGuardrailsSDK",
    "StreamingConfig",
    "quick_stream_guard",
    "quick_zero_copy_stream"
]
