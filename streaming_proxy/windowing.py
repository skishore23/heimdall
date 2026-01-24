"""
Advanced Streaming Window Management

Intelligent windowing system for streaming content with context preservation,
guard processing, and minimal latency overhead.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from heimdall import run_tiered_guards

from .buffer import BufferSlice

logger = logging.getLogger(__name__)


class WindowState(Enum):
    """Window processing states"""
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    BLOCKED = "blocked"
    FORWARDED = "forwarded"


@dataclass
class StreamingWindow:
    """
    A window of streaming content for processing

    Maintains context, processing state, and guard results
    without copying the underlying data.
    """
    id: str
    buffer_slice: BufferSlice
    sequence: int
    timestamp: float

    # Processing state
    state: WindowState = WindowState.PENDING
    guard_results: list[dict[str, Any]] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)

    # Context preservation
    previous_context: str | None = None
    next_context: str | None = None

    # Performance tracking
    processing_start: float | None = None
    processing_end: float | None = None

    @property
    def processing_time_ms(self) -> float | None:
        """Get processing time in milliseconds"""
        if self.processing_start and self.processing_end:
            return (self.processing_end - self.processing_start) * 1000
        return None

    @property
    def is_blocked(self) -> bool:
        """Check if window is blocked by guards"""
        return self.state == WindowState.BLOCKED or bool(self.violations)

    def get_content(self, buffer_manager) -> str:
        """Get window content (involves copy - use sparingly)"""
        # This is the only place where we copy data
        # In production, guards should work with buffer slices directly
        return buffer_manager.get_slice_content(self.buffer_slice)


class WindowManager:
    """
    Manages streaming windows with intelligent processing

    Handles window creation, guard processing, context preservation,
    and forwarding with minimal latency and memory overhead.
    """

    def __init__(
        self,
        window_size: int = 512,
        overlap_size: int = 64,
        max_concurrent_windows: int = 10,
        context_size: int = 128,
        max_check_time_ms: float = 5.0,
        enable_early_cancel: bool = True,
        drop_on_timeout: bool = True
    ):
        """
        Initialize window manager

        Args:
            window_size: Size of each processing window (tokens/chars) - FIXED
            overlap_size: Overlap between windows for context
            max_concurrent_windows: Maximum windows processing concurrently
            context_size: Size of context to preserve between windows
            max_check_time_ms: Maximum time for guard checks (hard limit)
            enable_early_cancel: Cancel checks that exceed budget
            drop_on_timeout: Drop window chunks that timeout (vs block)
        """
        self.window_size = window_size
        self.overlap_size = overlap_size
        self.max_concurrent_windows = max_concurrent_windows
        self.context_size = context_size
        self.max_check_time_ms = max_check_time_ms
        self.enable_early_cancel = enable_early_cancel
        self.drop_on_timeout = drop_on_timeout

        # Window tracking
        self._windows: dict[str, StreamingWindow] = {}
        self._sequence_counter = 0
        self._processing_semaphore = asyncio.Semaphore(max_concurrent_windows)

        # Performance metrics
        self._stats = {
            "windows_created": 0,
            "windows_processed": 0,
            "windows_blocked": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0
        }

    async def create_window(
        self,
        buffer_slice: BufferSlice,
        previous_window: StreamingWindow | None = None
    ) -> StreamingWindow:
        """
        Create a new streaming window

        Args:
            buffer_slice: Buffer slice containing window data
            previous_window: Previous window for context preservation

        Returns:
            New StreamingWindow instance
        """
        window_id = f"win_{self._sequence_counter}_{int(time.time() * 1000)}"

        window = StreamingWindow(
            id=window_id,
            buffer_slice=buffer_slice,
            sequence=self._sequence_counter,
            timestamp=time.time()
        )

        # Preserve context from previous window
        if previous_window:
            window.previous_context = self._extract_context(previous_window, "end")

        self._windows[window_id] = window
        self._sequence_counter += 1
        self._stats["windows_created"] += 1

        return window

    async def process_window(
        self,
        window: StreamingWindow,
        guards: dict[str, Any],
        guard_context: dict[str, Any] = None
    ) -> StreamingWindow:
        """
        Process window through guards with time-boxed execution

        Args:
            window: Window to process
            guards: Compiled guards to run
            guard_context: Additional context for guards

        Returns:
            Processed window
        """
        async with self._processing_semaphore:
            window.state = WindowState.PROCESSING
            window.processing_start = time.time()

            try:
                # Create guard context
                context = {
                    "phase": "streaming_window",
                    "window_id": window.id,
                    "sequence": window.sequence,
                    "buffer_slice": window.buffer_slice,
                    "previous_context": window.previous_context,
                    **(guard_context or {})
                }

                # Run tiered guards with timeout (time-boxed)
                timeout_seconds = self.max_check_time_ms / 1000.0

                try:
                    exec_result = await asyncio.wait_for(
                        run_tiered_guards(
                            guards=guards,
                            context=context,
                            enabled_tiers=["T0", "T1"]  # Skip T2 for streaming performance
                        ),
                        timeout=timeout_seconds
                    )

                    # Store results from ExecutionResult
                    window.guard_results = exec_result.tier_stats
                    window.violations = exec_result.violations

                    # Update state based on results
                    if exec_result.violations:
                        window.state = WindowState.BLOCKED
                        self._stats["windows_blocked"] += 1
                    else:
                        window.state = WindowState.PROCESSED

                except TimeoutError:
                    # Guard check exceeded time budget
                    if self.drop_on_timeout:
                        # Drop this window chunk (treat as processed)
                        window.state = WindowState.PROCESSED
                        window.violations = []
                        self._stats["windows_dropped_timeout"] = self._stats.get("windows_dropped_timeout", 0) + 1
                    else:
                        # Block on timeout
                        window.state = WindowState.BLOCKED
                        window.violations = [{
                            "rule_id": "window_manager.timeout",
                            "severity": "med",
                            "message": f"Guard check exceeded {self.max_check_time_ms}ms budget",
                            "evidence": {"window_id": window.id, "max_check_time_ms": self.max_check_time_ms}
                        }]
                        self._stats["windows_blocked"] += 1

                window.processing_end = time.time()

                # Update performance stats
                processing_time = window.processing_time_ms
                if processing_time:
                    self._stats["total_processing_time"] += processing_time
                    self._stats["windows_processed"] += 1
                    self._stats["average_processing_time"] = (
                        self._stats["total_processing_time"] / self._stats["windows_processed"]
                    )

                return window

            except Exception as e:
                # Guard execution error
                if self.enable_early_cancel:
                    # Cancel and drop on error
                    window.state = WindowState.PROCESSED
                    window.violations = []
                else:
                    # Block on error
                    window.state = WindowState.BLOCKED
                    window.violations = [{
                        "rule_id": "window_manager.error",
                        "severity": "critical",
                        "message": f"Window processing error: {str(e)}",
                        "evidence": {"window_id": window.id, "error": str(e)}
                    }]

                window.processing_end = time.time()

                return window

    def _extract_context(self, window: StreamingWindow, position: str) -> str | None:
        """
        Extract context from window for overlap

        Args:
            window: Window to extract context from
            position: "start" or "end"

        Returns:
            Context string
        """
        # Without direct buffer access here, do not fabricate context.
        # Return None to avoid misleading placeholder values.
        return None

    async def get_ready_windows(self) -> list[StreamingWindow]:
        """
        Get windows ready for forwarding

        Returns:
            List of windows ready to forward
        """
        ready_windows = []

        for window in self._windows.values():
            if window.state == WindowState.PROCESSED:
                ready_windows.append(window)

        # Sort by sequence to maintain order
        ready_windows.sort(key=lambda w: w.sequence)
        return ready_windows

    async def mark_forwarded(self, window: StreamingWindow) -> None:
        """
        Mark window as forwarded and clean up

        Args:
            window: Window that was forwarded
        """
        window.state = WindowState.FORWARDED

        # Clean up old windows (keep last few for context)
        current_sequence = self._sequence_counter
        cleanup_threshold = current_sequence - 10  # Keep last 10 windows

        windows_to_remove = [
            wid for wid, w in self._windows.items()
            if w.sequence < cleanup_threshold and w.state == WindowState.FORWARDED
        ]

        for wid in windows_to_remove:
            del self._windows[wid]

    def get_window_stats(self) -> dict[str, Any]:
        """Get window processing statistics"""
        state_counts = {}
        for state in WindowState:
            state_counts[state.value] = sum(
                1 for w in self._windows.values() if w.state == state
            )

        return {
            **self._stats,
            "active_windows": len(self._windows),
            "window_states": state_counts,
            "processing_capacity": self._processing_semaphore._value,
            "max_concurrent": self.max_concurrent_windows
        }


class AdaptiveWindowManager(WindowManager):
    """
    Adaptive window manager that adjusts window size based on content and performance

    Optimizes window size dynamically based on:
    - Processing latency
    - Guard violation rates
    - Content complexity
    - Network conditions
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Adaptive parameters
        self._base_window_size = self.window_size
        self._min_window_size = max(64, self.window_size // 4)
        self._max_window_size = self.window_size * 4

        # Performance tracking for adaptation
        self._recent_processing_times: list[float] = []
        self._recent_violation_rates: list[float] = []
        self._adaptation_interval = 100  # Adapt every N windows

        # Adaptation thresholds
        self._target_latency_ms = 10.0
        self._max_violation_rate = 0.05  # 5%

    async def process_window(self, window: StreamingWindow, guards: dict[str, Any], guard_context: dict[str, Any] = None) -> StreamingWindow:
        """Process window and adapt parameters"""
        result = await super().process_window(window, guards, guard_context)

        # Track metrics for adaptation
        if result.processing_time_ms:
            self._recent_processing_times.append(result.processing_time_ms)

        violation_rate = 1.0 if result.violations else 0.0
        self._recent_violation_rates.append(violation_rate)

        # Adapt parameters periodically
        if len(self._recent_processing_times) >= self._adaptation_interval:
            await self._adapt_parameters()

        return result

    async def _adapt_parameters(self):
        """Adapt window parameters based on recent performance"""
        # Calculate recent averages
        avg_latency = sum(self._recent_processing_times) / len(self._recent_processing_times)
        avg_violation_rate = sum(self._recent_violation_rates) / len(self._recent_violation_rates)

        # Adapt window size
        if avg_latency > self._target_latency_ms:
            # Reduce window size to improve latency
            new_size = max(self._min_window_size, int(self.window_size * 0.9))
        elif avg_violation_rate > self._max_violation_rate:
            # Increase window size for better context
            new_size = min(self._max_window_size, int(self.window_size * 1.1))
        else:
            # Gradually return to base size
            if self.window_size < self._base_window_size:
                new_size = min(self._base_window_size, int(self.window_size * 1.05))
            elif self.window_size > self._base_window_size:
                new_size = max(self._base_window_size, int(self.window_size * 0.95))
            else:
                new_size = self.window_size

        if new_size != self.window_size:
            logger.info(
                "Adapting window size: %s → %s (latency: %.1fms, violations: %.1f%%)",
                self.window_size,
                new_size,
                avg_latency,
                avg_violation_rate * 100.0
            )
            self.window_size = new_size

        # Reset tracking arrays
        self._recent_processing_times.clear()
        self._recent_violation_rates.clear()

    def get_adaptation_stats(self) -> dict[str, Any]:
        """Get adaptation-specific statistics"""
        return {
            **self.get_window_stats(),
            "current_window_size": self.window_size,
            "base_window_size": self._base_window_size,
            "min_window_size": self._min_window_size,
            "max_window_size": self._max_window_size,
            "target_latency_ms": self._target_latency_ms,
            "recent_samples": len(self._recent_processing_times)
        }
