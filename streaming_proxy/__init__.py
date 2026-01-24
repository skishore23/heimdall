"""
Zero-copy Streaming Proxy

Advanced windowing and forwarding system for high-performance streaming
with minimal memory overhead and sub-millisecond latency.
"""

from .buffer import CircularBuffer, MemoryPool
from .forwarding import ForwardingStrategy, ZeroCopyForwarder
from .proxy import StreamingProxy, StreamingProxyConfig
from .windowing import StreamingWindow, WindowManager

# Aliases for SDK compatibility
ZeroCopyStreamingProxy = StreamingProxy

__all__ = [
    "StreamingProxy",
    "StreamingProxyConfig",
    "StreamingWindow",
    "WindowManager",
    "ZeroCopyForwarder",
    "ForwardingStrategy",
    "CircularBuffer",
    "MemoryPool",
    "ZeroCopyStreamingProxy"  # Alias for SDK
]
