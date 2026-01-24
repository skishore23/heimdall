"""
Flow Context & Data Lineage Tracking

Category theory-based flow tracking that traces data through morphism chains.
Tracks transformations, origins, and relationships between data elements.

Core Concepts:
- Morphism: A -> B transformation with tracked lineage
- Flow: Sequence of morphisms with composition history
- Lineage: Complete provenance chain from source to destination
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar
from uuid import uuid4

from .types import Ctx, Either, Guard, Left_, Right_

# Type variables for morphisms
A = TypeVar('A')
B = TypeVar('B')
C = TypeVar('C')


@dataclass
class DataOrigin:
    """Tracks origin of data in the flow"""
    source_id: str
    source_type: str  # "input", "tool_call", "llm_output", "guard_transform"
    timestamp: datetime
    path: str  # JSONPath to the data
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Morphism:
    """
    Category theory morphism: A -> B
    Tracks transformation from one type to another with provenance
    """
    id: str
    source_type: str
    target_type: str
    transform: Callable[[Any], Any]
    origins: list[DataOrigin] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def compose(self, other: 'Morphism') -> 'Morphism':
        """Compose two morphisms: (f: A -> B) . (g: B -> C) = (g . f: A -> C)"""
        if self.target_type != other.source_type:
            raise TypeError(f"Cannot compose: {self.target_type} != {other.source_type}")

        def composed_transform(x: Any) -> Any:
            return other.transform(self.transform(x))

        return Morphism(
            id=f"{self.id}::{other.id}",
            source_type=self.source_type,
            target_type=other.target_type,
            transform=composed_transform,
            origins=self.origins + other.origins,
            metadata={"composed_from": [self.id, other.id]}
        )

    def __call__(self, x: A) -> B:
        """Apply morphism to input"""
        return self.transform(x)


@dataclass
class FlowEdge:
    """Edge in the flow graph representing data movement"""
    from_node: str
    to_node: str
    data_path: str
    morphism: Morphism | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FlowNode:
    """Node in the flow graph representing a computation point"""
    id: str
    node_type: str  # "input", "guard", "tool_call", "llm_call", "output"
    data: Any
    origins: list[DataOrigin] = field(default_factory=list)
    edges_in: list[FlowEdge] = field(default_factory=list)
    edges_out: list[FlowEdge] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


class FlowGraph:
    """
    Directed acyclic graph tracking data flow through the system
    Provides lineage queries and transformation tracking
    """

    def __init__(self):
        self.nodes: dict[str, FlowNode] = {}
        self.edges: list[FlowEdge] = []

    def add_node(self, node: FlowNode) -> None:
        """Add node to flow graph"""
        self.nodes[node.id] = node

    def add_edge(self, edge: FlowEdge) -> None:
        """Add edge connecting two nodes"""
        self.edges.append(edge)

        if edge.from_node in self.nodes:
            self.nodes[edge.from_node].edges_out.append(edge)
        if edge.to_node in self.nodes:
            self.nodes[edge.to_node].edges_in.append(edge)

    def get_lineage(self, node_id: str) -> list[FlowNode]:
        """Get complete lineage (ancestry) of a node"""
        if node_id not in self.nodes:
            return []

        lineage = []
        visited = set()

        def traverse(current_id: str):
            if current_id in visited:
                return
            visited.add(current_id)

            node = self.nodes[current_id]
            lineage.append(node)

            for edge in node.edges_in:
                traverse(edge.from_node)

        traverse(node_id)
        return lineage

    def get_descendants(self, node_id: str) -> list[FlowNode]:
        """Get all descendants (forward lineage) of a node"""
        if node_id not in self.nodes:
            return []

        descendants = []
        visited = set()

        def traverse(current_id: str):
            if current_id in visited:
                return
            visited.add(current_id)

            node = self.nodes[current_id]
            descendants.append(node)

            for edge in node.edges_out:
                traverse(edge.to_node)

        traverse(node_id)
        return descendants

    def find_path(self, from_id: str, to_id: str) -> list[FlowEdge] | None:
        """Find path between two nodes"""
        if from_id not in self.nodes or to_id not in self.nodes:
            return None

        visited = set()
        path = []

        def dfs(current_id: str) -> bool:
            if current_id == to_id:
                return True

            visited.add(current_id)
            node = self.nodes[current_id]

            for edge in node.edges_out:
                if edge.to_node not in visited:
                    path.append(edge)
                    if dfs(edge.to_node):
                        return True
                    path.pop()

            return False

        if dfs(from_id):
            return path
        return None

    def has_cycle(self) -> bool:
        """Check if graph has cycles (shouldn't in proper flow)"""
        visited = set()
        rec_stack = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)

            node = self.nodes[node_id]
            for edge in node.edges_out:
                if edge.to_node not in visited:
                    if dfs(edge.to_node):
                        return True
                elif edge.to_node in rec_stack:
                    return True

            rec_stack.remove(node_id)
            return False

        for node_id in self.nodes:
            if node_id not in visited:
                if dfs(node_id):
                    return True

        return False


@dataclass
class FlowContext:
    """
    Enhanced context with flow tracking capabilities
    Extends base Ctx with lineage and transformation history
    """
    base_ctx: Ctx
    flow_graph: FlowGraph
    current_node_id: str
    call_stack: list[str] = field(default_factory=list)
    data_lineage: dict[str, list[DataOrigin]] = field(default_factory=dict)

    def get_value(self, path: str) -> Any:
        """Get value from base context by path"""
        keys = path.split('.')
        current = self.base_ctx
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    def set_value(self, path: str, value: Any, origin: DataOrigin | None = None) -> None:
        """Set value in base context with lineage tracking"""
        keys = path.split('.')
        current = self.base_ctx

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

        if origin:
            if path not in self.data_lineage:
                self.data_lineage[path] = []
            self.data_lineage[path].append(origin)

    def track_call(self, call_id: str) -> None:
        """Track a call in the stack"""
        self.call_stack.append(call_id)

    def get_origins(self, path: str) -> list[DataOrigin]:
        """Get all origins for data at path"""
        return self.data_lineage.get(path, [])


def create_flow_context(ctx: Ctx, node_id: str | None = None) -> FlowContext:
    """Create a new flow context from base context"""
    return FlowContext(
        base_ctx=ctx,
        flow_graph=FlowGraph(),
        current_node_id=node_id or str(uuid4())
    )


def track_morphism(
    flow_ctx: FlowContext,
    source: str,
    target: str,
    transform: Callable[[Any], Any],
    source_type: str = "unknown",
    target_type: str = "unknown"
) -> FlowContext:
    """Track a morphism in the flow"""
    morphism_id = str(uuid4())

    morphism = Morphism(
        id=morphism_id,
        source_type=source_type,
        target_type=target_type,
        transform=transform
    )

    # Create nodes if they don't exist
    if source not in flow_ctx.flow_graph.nodes:
        flow_ctx.flow_graph.add_node(FlowNode(
            id=source,
            node_type=source_type,
            data=flow_ctx.get_value(source)
        ))

    target_node_id = str(uuid4())
    flow_ctx.flow_graph.add_node(FlowNode(
        id=target_node_id,
        node_type=target_type,
        data=None  # Will be set after transform
    ))

    # Add edge
    edge = FlowEdge(
        from_node=source,
        to_node=target_node_id,
        data_path=target,
        morphism=morphism
    )
    flow_ctx.flow_graph.add_edge(edge)

    # Update current node
    flow_ctx.current_node_id = target_node_id

    return flow_ctx


def check_data_flow(
    flow_ctx: FlowContext,
    from_pattern: str,
    to_pattern: str,
    predicate: Callable[[Any, Any], bool] | None = None
) -> bool:
    """
    Check if data flows from source to target matching patterns
    This enables Invariant-style flow rules: (out: ToolOutput) -> (call: ToolCall)
    """
    # Find all nodes matching from_pattern
    from_nodes = [
        node for node_id, node in flow_ctx.flow_graph.nodes.items()
        if node.node_type == from_pattern or from_pattern in str(node.metadata)
    ]

    # Find all nodes matching to_pattern
    to_nodes = [
        node for node_id, node in flow_ctx.flow_graph.nodes.items()
        if node.node_type == to_pattern or to_pattern in str(node.metadata)
    ]

    # Check if any path exists
    for from_node in from_nodes:
        for to_node in to_nodes:
            path = flow_ctx.flow_graph.find_path(from_node.id, to_node.id)
            if path:
                if predicate is None:
                    return True
                if predicate(from_node.data, to_node.data):
                    return True

    return False


def flow_guard(
    from_pattern: str,
    to_pattern: str,
    predicate: Callable[[Any, Any], bool],
    rule_id: str,
    message: str
) -> Guard:
    """
    Create a flow-based guard that checks data lineage
    Enables rules like: "PII from input should not flow to external API"
    """
    async def run(ctx: Ctx) -> Either:
        # Convert to flow context if needed
        if not isinstance(ctx, FlowContext):
            flow_ctx = create_flow_context(ctx)
        else:
            flow_ctx = ctx

        # Check flow
        has_flow = check_data_flow(flow_ctx, from_pattern, to_pattern, predicate)

        if has_flow:
            from .types import Violation
            return Left_([Violation(
                rule_id=rule_id,
                severity="high",
                message=message,
                evidence={"from": from_pattern, "to": to_pattern}
            )])

        return Right_(ctx)

    return run

