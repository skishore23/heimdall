"""
Dataflow and Taint Tracking Specification

Provides formal taxonomy for data sources, sinks, and taint propagation.
Integrates with W3C Trace Context baggage for distributed tracing.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class DataflowSource:
    """Data source specification"""
    path: str  # JSONPath or identifier (e.g., "messages[*].content", "db.users.email")
    classification: set[str] = field(default_factory=set)  # e.g., {"pii", "sensitive"}
    origin: str | None = None  # Origin system/service


@dataclass
class DataflowSink:
    """Data sink specification"""
    target: str  # Target identifier (e.g., "tool:email.send", "http:sendgrid.com")
    sink_type: Literal["tool", "http", "storage", "database", "api"]
    allowed_classifications: set[str] = field(default_factory=set)  # Allowed data classifications


@dataclass
class DataflowRule:
    """Data flow rule"""
    rule_id: str
    source_pattern: str  # Regex pattern for source paths
    sink_pattern: str  # Regex pattern for sink targets
    forbidden_classifications: set[str] = field(default_factory=set)
    required_guards: list[str] = field(default_factory=list)  # Guards that must pass
    description: str = ""

    def matches_flow(self, source: DataflowSource, sink: DataflowSink) -> bool:
        """Check if this rule matches a data flow"""
        source_match = re.match(self.source_pattern, source.path)
        sink_match = re.match(self.sink_pattern, sink.target)

        if not (source_match and sink_match):
            return False

        # Check if any forbidden classification is present
        return bool(source.classification & self.forbidden_classifications)


@dataclass
class TaintMetadata:
    """Taint metadata for tracking data flow"""
    sources: list[DataflowSource] = field(default_factory=list)
    classifications: set[str] = field(default_factory=set)
    propagation_path: list[str] = field(default_factory=list)  # Path through system

    def merge(self, other: "TaintMetadata") -> "TaintMetadata":
        """Merge taint metadata (for combining flows)"""
        return TaintMetadata(
            sources=self.sources + other.sources,
            classifications=self.classifications | other.classifications,
            propagation_path=self.propagation_path + other.propagation_path
        )

    def to_baggage(self) -> dict[str, str]:
        """Convert to W3C Trace Context baggage format"""
        return {
            "taint.classifications": ",".join(sorted(self.classifications)),
            "taint.source_count": str(len(self.sources)),
            "taint.path": "|".join(self.propagation_path[-5:])  # Last 5 hops
        }

    @classmethod
    def from_baggage(cls, baggage: dict[str, str]) -> "TaintMetadata":
        """Parse taint metadata from W3C baggage"""
        classifications_str = baggage.get("taint.classifications", "")
        classifications = set(classifications_str.split(",")) if classifications_str else set()

        path_str = baggage.get("taint.path", "")
        propagation_path = path_str.split("|") if path_str else []

        return cls(
            sources=[],  # Sources not fully serialized in baggage
            classifications=classifications,
            propagation_path=propagation_path
        )


class DataflowPolicy:
    """Data flow policy with sources, sinks, and rules"""

    def __init__(
        self,
        sources: list[DataflowSource],
        sinks: list[DataflowSink],
        rules: list[DataflowRule]
    ):
        self.sources = {src.path: src for src in sources}
        self.sinks = {sink.target: sink for sink in sinks}
        self.rules = rules

    def check_flow(
        self,
        source_path: str,
        sink_target: str,
        taint: TaintMetadata
    ) -> list[DataflowRule]:
        """
        Check if a data flow violates any rules

        Args:
            source_path: Source data path
            sink_target: Sink target
            taint: Taint metadata

        Returns:
            List of violated rules
        """
        violations = []

        # Find matching source and sink
        source = self.sources.get(source_path)
        sink = self.sinks.get(sink_target)

        if not source or not sink:
            # No policy for this flow
            return violations

        # Check each rule
        for rule in self.rules:
            if rule.matches_flow(source, sink):
                violations.append(rule)

        return violations

    def classify_source(self, source_path: str) -> set[str]:
        """Get classifications for a source path"""
        source = self.sources.get(source_path)
        return source.classification if source else set()

    def is_sink_allowed(self, sink_target: str, classifications: set[str]) -> bool:
        """Check if a sink allows given classifications"""
        sink = self.sinks.get(sink_target)
        if not sink:
            return True  # No policy = allow

        # Check if all classifications are allowed
        return classifications.issubset(sink.allowed_classifications)


def parse_dataflow_yaml(yaml_data: dict[str, Any]) -> DataflowPolicy:
    """
    Parse dataflow policy from YAML

    Example YAML:
    ```yaml
    sources:
      - path: "messages[*].content"
        classification: ["user_input"]
      - path: "db.users.email"
        classification: ["pii", "sensitive"]

    sinks:
      - target: "tool:email.send"
        type: "tool"
        allowed: []  # No sensitive data
      - target: "storage:s3://logs/*"
        type: "storage"
        allowed: ["user_input", "pii"]

    rules:
      - id: "pii.db_to_email"
        from: "db\\.users\\..*"
        to: "tool:email\\..*"
        forbid_if: ["pii"]
        description: "Prevent PII from DB going to email"
    ```
    """
    # Parse sources
    sources = []
    for src_data in yaml_data.get("sources", []):
        sources.append(DataflowSource(
            path=src_data["path"],
            classification=set(src_data.get("classification", [])),
            origin=src_data.get("origin")
        ))

    # Parse sinks
    sinks = []
    for sink_data in yaml_data.get("sinks", []):
        sinks.append(DataflowSink(
            target=sink_data["target"],
            sink_type=sink_data.get("type", "api"),
            allowed_classifications=set(sink_data.get("allowed", []))
        ))

    # Parse rules
    rules = []
    for rule_data in yaml_data.get("rules", []):
        rules.append(DataflowRule(
            rule_id=rule_data["id"],
            source_pattern=rule_data["from"],
            sink_pattern=rule_data["to"],
            forbidden_classifications=set(rule_data.get("forbid_if", [])),
            required_guards=rule_data.get("require_guards", []),
            description=rule_data.get("description", "")
        ))

    return DataflowPolicy(sources, sinks, rules)


def attach_taint_to_context(ctx: dict[str, Any], taint: TaintMetadata) -> dict[str, Any]:
    """Attach taint metadata to context"""
    ctx["_taint"] = taint
    return ctx


def extract_taint_from_context(ctx: dict[str, Any]) -> TaintMetadata | None:
    """Extract taint metadata from context"""
    return ctx.get("_taint")


def propagate_taint(
    ctx: dict[str, Any],
    operation: str
) -> dict[str, Any]:
    """
    Propagate taint through an operation

    Args:
        ctx: Context with taint metadata
        operation: Operation identifier (for tracking)

    Returns:
        Context with updated taint
    """
    taint = extract_taint_from_context(ctx)
    if taint:
        taint.propagation_path.append(operation)
    return ctx

