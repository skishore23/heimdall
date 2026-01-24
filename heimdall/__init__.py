"""
Composable Guard Algebra (Heimdall) Core

This module provides the foundational types and combinators for building
composable guard systems using functional programming principles.
"""

# Guard Authoring DSL (More concise than Invariant, powered by CT)
from .author import (
    G,
    GuardChain,
    chain,
    flow,
    guard,
)
from .comb import (
    allOf,
    anyOf,
    focus,
    kOf,
    lens,
    seq,
    unless,
)
from .comonad import (
    ComonadContext,
    EnvironmentComonad,
    HistoryComonad,
    conditional_on_history,
    environment_aware_guard,
    history_aware_guard,
    rate_limiting_guard,
    stateful_guard,
    trend_detection_guard,
    windowed_guard,
)
from .compiler import compile_policy

# ONNX guards moved to guard_packs/onnx/
# Import from there if needed: from guards.onnx import universal_onnx_guard
# Practical composition modules
from .flow import (
    DataOrigin,
    FlowContext,
    FlowEdge,
    FlowGraph,
    FlowNode,
    Morphism,
    check_data_flow,
    create_flow_context,
    flow_guard,
    track_morphism,
)
from .kleisli import (
    bind,
    chain,
    filter_violations,
    fmap,
    identity,
    kleisli_compose,
    lift,
    merge_violations,
    try_guard,
    unless_condition,
    when,
)
from .onnx_registry import (
    ONNXModelInfo,
    ONNXModelRegistry,
    get_model_info,
    get_onnx_registry,
    list_available_models,
    load_onnx_model,
)
from .optics import (
    Iso,
    Lens,
    Prism,
    Traversal,
    attr_lens,
    dict_values_traversal,
    identity_iso,
    index_lens,
    json_string_iso,
    lens_guard,
    list_traversal,
    optional_prism,
    path_lens,
    prism_guard,
    traversal_guard,
)
from .orchestrate import (
    FlowRuleBuilder,
    GuardBuilder,
    TemporalRuleBuilder,
    flow_rule,
    orchestrate,
    sophisticated_pii_guard,
    sophisticated_rate_limiter,
    sophisticated_tool_guard,
    temporal_rule,
)

# Performance measurement and optimization
from .profiler import (
    GuardProfile,
    PerformanceProfiler,
    benchmark_guard,
    get_profiler,
)
from .profiler import (
    profile_guard as measure,  # Public API: measure performance and optimize
)
from .registry import (
    REGISTRY,
    clear_registry,
    get_guard,
    get_guard_metadata,
    get_guards_by_tier,
    get_registry,
    register_factory,
    register_guard,
)
from .sdk_advanced import (
    AdvancedGuardSDK,
    advanced_sdk,
    circular_dependency_guard,
    content_filtering_pipeline,
    pii_flow_guard,
    rate_limit_guard,
    retry_prevention_guard,
    sophisticated_tool_enforcement_guard,
)
from .temporal import (
    CallPattern,
    TemporalChain,
    TemporalConstraint,
    TemporalEvent,
    detect_circular_dependency,
    detect_retry_loop,
    enforce_rate_limit,
    require_sequence,
)
from .tiered_runner import (
    ExecutionResult,
    TierConfig,
    TieredGuardRunner,
    run_tiered_guards,
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

__version__ = "0.9.0"

__all__ = [
    # Types
    "Ctx",
    "Violation",
    "Either",
    "Left",
    "Right",
    "Guard",
    "Left_",
    "Right_",
    "is_left",
    "is_right",
    "get_violations",
    "get_context",
    # Combinators
    "seq",
    "allOf",
    "anyOf",
    "kOf",
    "unless",
    "focus",
    "lens",
    # Registry
    "REGISTRY",
    "register_factory",
    "register_guard",
    "get_guard",
    "get_guard_metadata",
    "get_guards_by_tier",
    "get_registry",
    "clear_registry",
    # Compiler
    "compile_policy",
    # Tiered Runner
    "TieredGuardRunner",
    "TierConfig",
    "ExecutionResult",
    "run_tiered_guards",
    # ONNX Registry
    "get_onnx_registry",
    "list_available_models",
    "get_model_info",
    "load_onnx_model",
    "ONNXModelInfo",
    "ONNXModelRegistry",
    # Flow Tracking
    "FlowContext",
    "FlowGraph",
    "FlowNode",
    "FlowEdge",
    "Morphism",
    "DataOrigin",
    "create_flow_context",
    "track_morphism",
    "check_data_flow",
    "flow_guard",
    # Kleisli Composition
    "identity",
    "kleisli_compose",
    "bind",
    "chain",
    "fmap",
    "lift",
    "try_guard",
    "filter_violations",
    "merge_violations",
    "when",
    "unless_condition",
    # Temporal Tracking
    "TemporalChain",
    "TemporalEvent",
    "CallPattern",
    "TemporalConstraint",
    "detect_retry_loop",
    "detect_circular_dependency",
    "enforce_rate_limit",
    "require_sequence",
    # Optics
    "Lens",
    "Prism",
    "Traversal",
    "Iso",
    "attr_lens",
    "index_lens",
    "path_lens",
    "optional_prism",
    "list_traversal",
    "dict_values_traversal",
    "identity_iso",
    "json_string_iso",
    "lens_guard",
    "prism_guard",
    "traversal_guard",
    # Comonads
    "ComonadContext",
    "HistoryComonad",
    "EnvironmentComonad",
    "history_aware_guard",
    "environment_aware_guard",
    "windowed_guard",
    "stateful_guard",
    "rate_limiting_guard",
    "trend_detection_guard",
    "conditional_on_history",
    # Orchestration
    "GuardBuilder",
    "FlowRuleBuilder",
    "TemporalRuleBuilder",
    "orchestrate",
    "flow_rule",
    "temporal_rule",
    "sophisticated_pii_guard",
    "sophisticated_rate_limiter",
    "sophisticated_tool_guard",
    # Advanced SDK
    "AdvancedGuardSDK",
    "advanced_sdk",
    "pii_flow_guard",
    "retry_prevention_guard",
    "circular_dependency_guard",
    "rate_limit_guard",
    "sophisticated_tool_enforcement_guard",
    "content_filtering_pipeline",
    # Performance
    "measure",
    "benchmark_guard",
    "PerformanceProfiler",
    "GuardProfile",
    "get_profiler",
    # Guard Authoring DSL
    "G",
    "guard",
    "chain",
    "GuardChain",
    "flow",
]
