"""
Guardrails SDK

Lightweight, embeddable SDK for guard execution and policy enforcement.

For ONNX models and streaming proxy, use Bifrost gateway.
"""

from .core import (
    GuardViolation,
    HeimdallSDK,
    PolicyError,
    SDKConfig,
    load_policy,
    quick_guard,
)

# Version info
__version__ = "2.0.0"

# Export all public classes and functions
__all__ = [
    "HeimdallSDK",
    "SDKConfig",
    "PolicyError",
    "GuardViolation",
    "quick_guard",
    "load_policy",
    "__version__"
]
