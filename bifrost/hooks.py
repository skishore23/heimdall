"""
Runtime Hook System for Bifrost Gateway

Provides uniform hook points for guard execution at key interception points:
- before_llm / after_llm: LLM request/response
- before_tool / after_tool: Tool call/output
- before_mcp / after_mcp: MCP request/response

Functional design with immutable hook registry.
"""

from dataclasses import dataclass, field
from enum import Enum

from heimdall.types import Ctx, Either, Guard

# === Hook Types ===

class HookPhase(str, Enum):
    """Standard hook phases"""
    BEFORE_LLM = "before_llm"
    AFTER_LLM = "after_llm"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    BEFORE_MCP = "before_mcp"
    AFTER_MCP = "after_mcp"
    BEFORE_EMBEDDING = "before_embedding"
    AFTER_EMBEDDING = "after_embedding"


# === Hook Registry ===

@dataclass(frozen=True)
class HookRegistration:
    """Immutable hook registration"""
    phase: HookPhase
    guard: Guard
    priority: int = 0  # Lower priority runs first
    rule_id: str = ""

    def __lt__(self, other: 'HookRegistration') -> bool:
        """Compare by priority for sorting"""
        return self.priority < other.priority


@dataclass
class HookRegistry:
    """
    Registry for runtime hooks

    Manages hook registrations per phase with priority ordering.
    """
    _hooks: dict[HookPhase, list[HookRegistration]] = field(default_factory=dict)

    def register(
        self,
        phase: HookPhase,
        guard: Guard,
        priority: int = 0,
        rule_id: str = ""
    ) -> None:
        """
        Register a guard at a specific phase

        Args:
            phase: Hook phase to register at
            guard: Guard function to execute
            priority: Execution priority (lower runs first)
            rule_id: Optional rule identifier
        """
        if phase not in self._hooks:
            self._hooks[phase] = []

        registration = HookRegistration(
            phase=phase,
            guard=guard,
            priority=priority,
            rule_id=rule_id
        )

        self._hooks[phase].append(registration)
        # Keep sorted by priority
        self._hooks[phase].sort()

    def get_hooks(self, phase: HookPhase) -> list[Guard]:
        """
        Get all guards registered for a phase (ordered by priority)

        Args:
            phase: Hook phase to query

        Returns:
            List of guards in priority order
        """
        if phase not in self._hooks:
            return []

        return [reg.guard for reg in self._hooks[phase]]

    def clear_phase(self, phase: HookPhase) -> None:
        """Clear all hooks for a phase"""
        if phase in self._hooks:
            del self._hooks[phase]

    def clear_all(self) -> None:
        """Clear all registered hooks"""
        self._hooks.clear()

    def list_phases(self) -> list[HookPhase]:
        """List all phases with registered hooks"""
        return list(self._hooks.keys())

    def count_hooks(self, phase: HookPhase) -> int:
        """Count hooks registered for a phase"""
        return len(self._hooks.get(phase, []))


# === Hook Executor ===

async def execute_hooks(
    registry: HookRegistry,
    phase: HookPhase,
    ctx: Ctx
) -> Either:
    """
    Execute all hooks for a phase sequentially

    Args:
        registry: Hook registry
        phase: Hook phase to execute
        ctx: Context to pass to hooks

    Returns:
        Either with final context or violations
    """
    from heimdall.comb import seq
    from heimdall.types import Right_

    hooks = registry.get_hooks(phase)

    if not hooks:
        return Right_(ctx)

    # Compose all hooks sequentially
    composed = seq(*hooks)
    return await composed(ctx)


# === Fluent Builder API ===

class HookBuilder:
    """
    Fluent builder for hook registration

    Example:
        bifrost = HookBuilder(registry)
        bifrost.on("before_llm", auth_guard) \\
               .on("after_llm", content_filter) \\
               .on("before_tool", tool_auth)
    """

    def __init__(self, registry: HookRegistry):
        self._registry = registry

    def on(
        self,
        phase: str | HookPhase,
        guard: Guard,
        priority: int = 0,
        rule_id: str = ""
    ) -> 'HookBuilder':
        """
        Register a guard at a phase

        Args:
            phase: Hook phase (string or enum)
            guard: Guard to register
            priority: Execution priority
            rule_id: Optional rule ID

        Returns:
            Self for chaining
        """
        # Convert string to enum if needed
        if isinstance(phase, str):
            phase = HookPhase(phase)

        self._registry.register(phase, guard, priority, rule_id)
        return self

    def before_llm(self, guard: Guard, priority: int = 0) -> 'HookBuilder':
        """Register guard for before_llm phase"""
        return self.on(HookPhase.BEFORE_LLM, guard, priority)

    def after_llm(self, guard: Guard, priority: int = 0) -> 'HookBuilder':
        """Register guard for after_llm phase"""
        return self.on(HookPhase.AFTER_LLM, guard, priority)

    def before_tool(self, guard: Guard, priority: int = 0) -> 'HookBuilder':
        """Register guard for before_tool phase"""
        return self.on(HookPhase.BEFORE_TOOL, guard, priority)

    def after_tool(self, guard: Guard, priority: int = 0) -> 'HookBuilder':
        """Register guard for after_tool phase"""
        return self.on(HookPhase.AFTER_TOOL, guard, priority)

    def before_mcp(self, guard: Guard, priority: int = 0) -> 'HookBuilder':
        """Register guard for before_mcp phase"""
        return self.on(HookPhase.BEFORE_MCP, guard, priority)

    def after_mcp(self, guard: Guard, priority: int = 0) -> 'HookBuilder':
        """Register guard for after_mcp phase"""
        return self.on(HookPhase.AFTER_MCP, guard, priority)

    def get_registry(self) -> HookRegistry:
        """Get the underlying registry"""
        return self._registry


# === Factory ===

def create_hook_builder() -> HookBuilder:
    """Create a new hook builder with empty registry"""
    return HookBuilder(HookRegistry())


__all__ = [
    # Enums
    "HookPhase",
    # Core types
    "HookRegistration",
    "HookRegistry",
    # Execution
    "execute_hooks",
    # Builder
    "HookBuilder",
    "create_hook_builder",
]

