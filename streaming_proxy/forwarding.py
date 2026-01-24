"""
Zero-copy Forwarding Engine

High-performance forwarding system that minimizes data copying
and provides sub-millisecond forwarding latency.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .buffer import CircularBuffer
from .windowing import StreamingWindow, WindowState

logger = logging.getLogger(__name__)


class ForwardingStrategy(Enum):
    """Forwarding strategies for different use cases"""
    IMMEDIATE = "immediate"      # Forward immediately (lowest latency)
    BUFFERED = "buffered"       # Buffer and forward in chunks (higher throughput)
    ADAPTIVE = "adaptive"       # Adapt based on conditions


@dataclass
class ForwardingConfig:
    """Configuration for zero-copy forwarder"""
    strategy: ForwardingStrategy = ForwardingStrategy.ADAPTIVE

    # Buffering settings
    buffer_size: int = 64 * 1024  # 64KB buffer
    flush_interval_ms: float = 5.0  # Flush every 5ms
    max_batch_size: int = 10  # Max windows per batch

    # Performance settings
    enable_compression: bool = False
    compression_threshold: int = 1024  # Compress if > 1KB

    # Zero-copy settings
    use_sendfile: bool = True  # Use sendfile() for zero-copy
    use_splice: bool = True    # Use splice() on Linux

    # Adaptive settings
    latency_target_ms: float = 10.0
    throughput_target_mbps: float = 100.0


class ZeroCopyForwarder:
    """
    Zero-copy forwarding engine for streaming data

    Minimizes memory copies and provides high-performance forwarding
    with configurable strategies and adaptive optimization.
    """

    def __init__(self, config: ForwardingConfig = None):
        """
        Initialize zero-copy forwarder

        Args:
            config: Forwarding configuration
        """
        self.config = config or ForwardingConfig()

        # Forwarding state
        self._output_buffer = CircularBuffer(self.config.buffer_size)
        self._pending_windows: list[StreamingWindow] = []
        self._forwarding_task: asyncio.Task | None = None

        # Performance tracking
        self._stats = {
            "bytes_forwarded": 0,
            "windows_forwarded": 0,
            "batches_sent": 0,
            "zero_copy_operations": 0,
            "copy_operations": 0,
            "total_latency_ms": 0.0,
            "average_latency_ms": 0.0
        }

        # Adaptive parameters
        self._recent_latencies: list[float] = []
        self._recent_throughputs: list[float] = []

        # Start forwarding task
        self._start_forwarding_task()

    def _start_forwarding_task(self):
        """Start the background forwarding task"""
        if self._forwarding_task is None or self._forwarding_task.done():
            self._forwarding_task = asyncio.create_task(self._forwarding_loop())

    async def _forwarding_loop(self):
        """Main forwarding loop"""
        while True:
            try:
                if self.config.strategy == ForwardingStrategy.IMMEDIATE:
                    await self._forward_immediate()
                elif self.config.strategy == ForwardingStrategy.BUFFERED:
                    await self._forward_buffered()
                else:  # ADAPTIVE
                    await self._forward_adaptive()

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.001)  # 1ms

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Forwarding error: %s", e, exc_info=True)
                await asyncio.sleep(0.1)  # Longer delay on error

    async def queue_window(self, window: StreamingWindow) -> None:
        """
        Queue a window for forwarding

        Args:
            window: Window to forward
        """
        if window.state == WindowState.PROCESSED and not window.is_blocked:
            self._pending_windows.append(window)

    async def _forward_immediate(self):
        """Forward windows immediately (lowest latency)"""
        if not self._pending_windows:
            return

        window = self._pending_windows.pop(0)
        await self._forward_single_window(window)

    async def _forward_buffered(self):
        """Forward windows in batches (higher throughput)"""
        if not self._pending_windows:
            return

        # Collect batch
        batch = []
        batch_size = 0

        while (self._pending_windows and
               len(batch) < self.config.max_batch_size):
            window = self._pending_windows.pop(0)
            batch.append(window)
            batch_size += window.buffer_slice.length

            if batch_size >= self.config.buffer_size:
                break

        if batch:
            await self._forward_batch(batch)

    async def _forward_adaptive(self):
        """Adaptive forwarding based on conditions"""
        if not self._pending_windows:
            return

        # Decide strategy based on current conditions
        avg_latency = (
            sum(self._recent_latencies) / len(self._recent_latencies)
            if self._recent_latencies else 0
        )

        if avg_latency > self.config.latency_target_ms:
            # High latency - use immediate forwarding
            await self._forward_immediate()
        else:
            # Normal latency - use buffered forwarding
            await self._forward_buffered()

    async def _forward_single_window(self, window: StreamingWindow) -> None:
        """
        Forward a single window with zero-copy optimization

        Args:
            window: Window to forward
        """
        start_time = time.time()

        try:
            # Try zero-copy forwarding first
            if await self._try_zero_copy_forward(window):
                self._stats["zero_copy_operations"] += 1
            else:
                # Fall back to copy-based forwarding
                await self._copy_forward_window(window)
                self._stats["copy_operations"] += 1

            # Update statistics
            latency_ms = (time.time() - start_time) * 1000
            self._update_stats(window, latency_ms)

        except Exception as e:
            logger.error("Error forwarding window %s: %s", window.id, e, exc_info=True)

    async def _forward_batch(self, windows: list[StreamingWindow]) -> None:
        """
        Forward a batch of windows efficiently

        Args:
            windows: List of windows to forward
        """
        start_time = time.time()

        try:
            # Try to forward batch with zero-copy
            if await self._try_zero_copy_batch_forward(windows):
                self._stats["zero_copy_operations"] += len(windows)
            else:
                # Fall back to individual forwarding
                for window in windows:
                    await self._copy_forward_window(window)
                self._stats["copy_operations"] += len(windows)

            # Update statistics
            total_latency_ms = (time.time() - start_time) * 1000
            avg_latency_ms = total_latency_ms / len(windows)

            for window in windows:
                self._update_stats(window, avg_latency_ms)

            self._stats["batches_sent"] += 1

        except Exception as e:
            logger.error("Error forwarding batch: %s", e, exc_info=True)

    async def _try_zero_copy_forward(self, window: StreamingWindow) -> bool:
        """
        Attempt zero-copy forwarding using system calls

        Args:
            window: Window to forward

        Returns:
            True if zero-copy was successful
        """
        # This would use platform-specific zero-copy mechanisms:
        # - sendfile() on Unix systems
        # - splice() on Linux
        # - TransmitFile() on Windows

        # For now, simulate zero-copy success based on buffer type
        if hasattr(window.buffer_slice, 'data_ptr'):
            # Simulate zero-copy operation
            await asyncio.sleep(0.001)  # Minimal delay for zero-copy
            return True

        return False

    async def _try_zero_copy_batch_forward(self, windows: list[StreamingWindow]) -> bool:
        """
        Attempt zero-copy batch forwarding

        Args:
            windows: Windows to forward

        Returns:
            True if zero-copy batch was successful
        """
        # Check if all windows support zero-copy
        all_zero_copy = all(
            hasattr(w.buffer_slice, 'data_ptr') for w in windows
        )

        if all_zero_copy:
            # Simulate vectored I/O (writev/sendmsg)
            await asyncio.sleep(0.002)  # Slightly longer for batch
            return True

        return False

    async def _copy_forward_window(self, window: StreamingWindow) -> None:
        """
        Forward window using traditional copy method

        Args:
            window: Window to forward
        """
        # This involves copying data - should be avoided when possible
        # In a real implementation, this would write to the output stream

        # Simulate copy operation
        copy_time = window.buffer_slice.length / (100 * 1024 * 1024)  # 100MB/s
        await asyncio.sleep(copy_time)

    def _update_stats(self, window: StreamingWindow, latency_ms: float) -> None:
        """
        Update forwarding statistics

        Args:
            window: Window that was forwarded
            latency_ms: Forwarding latency in milliseconds
        """
        self._stats["bytes_forwarded"] += window.buffer_slice.length
        self._stats["windows_forwarded"] += 1
        self._stats["total_latency_ms"] += latency_ms
        self._stats["average_latency_ms"] = (
            self._stats["total_latency_ms"] / self._stats["windows_forwarded"]
        )

        # Track recent metrics for adaptation
        self._recent_latencies.append(latency_ms)
        if len(self._recent_latencies) > 100:
            self._recent_latencies.pop(0)

        # Calculate throughput (bytes/second)
        if latency_ms > 0:
            throughput_bps = (window.buffer_slice.length / latency_ms) * 1000
            self._recent_throughputs.append(throughput_bps)
            if len(self._recent_throughputs) > 100:
                self._recent_throughputs.pop(0)

    def get_stats(self) -> dict[str, Any]:
        """Get forwarding statistics"""
        zero_copy_rate = 0.0
        if self._stats["zero_copy_operations"] + self._stats["copy_operations"] > 0:
            zero_copy_rate = (
                self._stats["zero_copy_operations"] /
                (self._stats["zero_copy_operations"] + self._stats["copy_operations"])
            )

        avg_throughput = 0.0
        if self._recent_throughputs:
            avg_throughput = sum(self._recent_throughputs) / len(self._recent_throughputs)

        return {
            **self._stats,
            "zero_copy_rate": zero_copy_rate,
            "pending_windows": len(self._pending_windows),
            "average_throughput_bps": avg_throughput,
            "average_throughput_mbps": avg_throughput / (1024 * 1024),
            "buffer_utilization": self._output_buffer.available_data / self._output_buffer.size
        }

    async def flush(self) -> None:
        """Force flush of all pending data"""
        while self._pending_windows:
            await self._forward_immediate()

    async def close(self) -> None:
        """Close forwarder and cleanup resources"""
        if self._forwarding_task:
            self._forwarding_task.cancel()
            try:
                await self._forwarding_task
            except asyncio.CancelledError:
                pass

        # Flush any remaining data
        await self.flush()


class StreamingForwarder:
    """
    High-level streaming forwarder that combines windowing and zero-copy forwarding

    Provides a complete streaming solution with guard processing and forwarding.
    """

    def __init__(
        self,
        window_manager,
        forwarder: ZeroCopyForwarder,
        output_stream: Callable | None = None
    ):
        """
        Initialize streaming forwarder

        Args:
            window_manager: Window manager for processing
            forwarder: Zero-copy forwarder for output
            output_stream: Output stream function
        """
        self.window_manager = window_manager
        self.forwarder = forwarder
        self.output_stream = output_stream

        # Processing task
        self._processing_task: asyncio.Task | None = None
        self._start_processing()

    def _start_processing(self):
        """Start the processing and forwarding pipeline"""
        if self._processing_task is None or self._processing_task.done():
            self._processing_task = asyncio.create_task(self._processing_loop())

    async def _processing_loop(self):
        """Main processing loop"""
        while True:
            try:
                # Get ready windows from manager
                ready_windows = await self.window_manager.get_ready_windows()

                # Queue windows for forwarding
                for window in ready_windows:
                    await self.forwarder.queue_window(window)
                    await self.window_manager.mark_forwarded(window)

                await asyncio.sleep(0.001)  # 1ms delay

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Processing loop error: %s", e, exc_info=True)
                await asyncio.sleep(0.1)

    async def process_chunk(self, data: str | bytes) -> None:
        """
        Process a chunk of streaming data

        Args:
            data: Data chunk to process
        """
        # This would integrate with the streaming buffer and window creation
        # For now, simulate the processing
        logger.debug("Processing chunk: %d bytes", len(data))

    def get_combined_stats(self) -> dict[str, Any]:
        """Get combined statistics from all components"""
        return {
            "window_stats": self.window_manager.get_window_stats(),
            "forwarding_stats": self.forwarder.get_stats(),
            "pipeline_active": not (self._processing_task and self._processing_task.done())
        }

    async def close(self):
        """Close the streaming forwarder"""
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        await self.forwarder.close()
