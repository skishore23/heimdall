"""
Public API Surface for Guardrails v0.9+

This module defines the stable public API. All functions and classes exported here
are considered stable and follow semantic versioning.

Breaking changes will only occur on major version bumps.
"""


# Core types (stable since v0.9)
# Composition operators (stable since v0.9)
from .comb import (
    allOf,
    anyOf,
    chain,
    focus,
    kOf,
    lens,
    seq,
    unless,
)

# Compiler (stable since v0.9)
from .compiler import (
    compile_policy,
    compile_policy_from_file,
    validate_policy_structure,
)

# Mímir control plane (stable since v0.9)
from .mimir import (
    PolicyEnvelope,
    compile_and_sign_policy,
    generate_signing_keypair,
    verify_policy_signature,
)

# Plugin system (stable since v0.9)
from .plugin import (
    GuardPlugin,
    PluginRegistry,
    list_plugins,
    register_plugin,
    validate_plugin_compatibility,
)
from .registry import (
    get_guard,
    get_guard_metadata,
    get_guards_by_tier,
    has_guard,
    list_guards,
    register_guard,
)

# Registry (stable since v0.9)
from .registry import (
    guard as guard_decorator,
)
from .types import (
    Ctx,
    Either,
    Guard,
    Left,
    Left_,
    Right,
    Right_,
    Violation,
    get_context,
    get_violations,
    is_left,
    is_right,
)

# Version info
__version__ = "0.9.0"
__abi_version__ = "0.9"

__all__ = [
    # Version
    "__version__",
    "__abi_version__",
    # Types
    "Ctx",
    "Guard",
    "Violation",
    "Either",
    "Left",
    "Right",
    "Left_",
    "Right_",
    "is_left",
    "is_right",
    "get_violations",
    "get_context",
    # Combinators
    "chain",
    "seq",
    "allOf",
    "anyOf",
    "kOf",
    "unless",
    "lens",
    "focus",
    # Registry
    "guard_decorator",
    "register_guard",
    "get_guard",
    "get_guard_metadata",
    "list_guards",
    "has_guard",
    "get_guards_by_tier",
    # Compiler
    "compile_policy",
    "compile_policy_from_file",
    "validate_policy_structure",
    # Plugins
    "GuardPlugin",
    "PluginRegistry",
    "register_plugin",
    "list_plugins",
    "validate_plugin_compatibility",
    # Mímir
    "PolicyEnvelope",
    "compile_and_sign_policy",
    "verify_policy_signature",
    "generate_signing_keypair",
]

