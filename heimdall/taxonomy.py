"""
Source/Sink Taxonomy for Dataflow Tracking

Defines standard sources and sinks for dataflow analysis,
enabling fine-grained control over data movement.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

# === Source/Sink Types ===

class SourceType(str, Enum):
    """Standard data source types"""
    USER_INPUT = "user_input"
    HTTP_REQUEST = "http_request"
    DATABASE = "database"
    FILE_SYSTEM = "file_system"
    ENVIRONMENT_VAR = "environment_var"
    TOOL_OUTPUT = "tool_output"
    LLM_OUTPUT = "llm_output"
    MCP_SERVER = "mcp_server"
    API_RESPONSE = "api_response"
    CACHE = "cache"
    MEMORY = "memory"
    CONFIGURATION = "configuration"


class SinkType(str, Enum):
    """Standard data sink types"""
    HTTP_RESPONSE = "http_response"
    DATABASE = "database"
    FILE_SYSTEM = "file_system"
    EXTERNAL_API = "external_api"
    LLM_PROMPT = "llm_prompt"
    TOOL_CALL = "tool_call"
    MCP_REQUEST = "mcp_request"
    LOG_OUTPUT = "log_output"
    CACHE = "cache"
    MEMORY = "memory"
    USER_DISPLAY = "user_display"


class DataSensitivity(str, Enum):
    """Data sensitivity classifications"""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    PII = "pii"
    PHI = "phi"  # Protected Health Information
    PCI = "pci"  # Payment Card Industry data


# === Taxonomy Definitions ===

@dataclass(frozen=True)
class Source:
    """Immutable source definition"""
    id: str
    source_type: SourceType
    domain: str | None = None  # e.g., "api.example.com"
    path: str | None = None     # e.g., "users.email"
    sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    labels: frozenset[str] = frozenset()

    def matches(self, pattern: str) -> bool:
        """Check if this source matches a pattern"""
        if pattern == "*":
            return True
        if pattern == self.id:
            return True
        if self.domain and pattern in self.domain:
            return True
        if self.path and pattern in self.path:
            return True
        return pattern in self.labels


@dataclass(frozen=True)
class Sink:
    """Immutable sink definition"""
    id: str
    sink_type: SinkType
    domain: str | None = None  # e.g., "api.partner.com"
    path: str | None = None     # e.g., "external.analytics"
    trust_level: Literal["trusted", "internal", "external", "untrusted"] = "internal"
    labels: frozenset[str] = frozenset()

    def matches(self, pattern: str) -> bool:
        """Check if this sink matches a pattern"""
        if pattern == "*":
            return True
        if pattern == self.id:
            return True
        if self.domain and pattern in self.domain:
            return True
        if self.path and pattern in self.path:
            return True
        return pattern in self.labels


# === Flow Rules ===

@dataclass(frozen=True)
class FlowRule:
    """Immutable flow rule definition"""
    id: str
    from_source: str  # Source pattern
    to_sink: str      # Sink pattern
    action: Literal["allow", "deny", "redact", "audit"]
    sensitivity_required: DataSensitivity | None = None
    message: str = ""

    def applies_to(self, source: Source, sink: Sink) -> bool:
        """Check if this rule applies to given source/sink pair"""
        source_match = source.matches(self.from_source)
        sink_match = sink.matches(self.to_sink)

        sensitivity_match = (
            self.sensitivity_required is None or
            source.sensitivity == self.sensitivity_required
        )

        return source_match and sink_match and sensitivity_match


# === Predefined Sources ===

SOURCE_USER_INPUT = Source(
    id="user_input",
    source_type=SourceType.USER_INPUT,
    sensitivity=DataSensitivity.INTERNAL,
    labels=frozenset(["untrusted", "user_generated"])
)

SOURCE_DATABASE = Source(
    id="database",
    source_type=SourceType.DATABASE,
    sensitivity=DataSensitivity.CONFIDENTIAL,
    labels=frozenset(["internal", "persistent"])
)

SOURCE_ENVIRONMENT = Source(
    id="environment",
    source_type=SourceType.ENVIRONMENT_VAR,
    sensitivity=DataSensitivity.SECRET,
    labels=frozenset(["configuration", "secrets"])
)

SOURCE_LLM_OUTPUT = Source(
    id="llm_output",
    source_type=SourceType.LLM_OUTPUT,
    sensitivity=DataSensitivity.INTERNAL,
    labels=frozenset(["generated", "llm"])
)

SOURCE_MCP_SERVER = Source(
    id="mcp_server",
    source_type=SourceType.MCP_SERVER,
    sensitivity=DataSensitivity.INTERNAL,
    labels=frozenset(["tool", "external"])
)


# === Predefined Sinks ===

SINK_EXTERNAL_API = Sink(
    id="external_api",
    sink_type=SinkType.EXTERNAL_API,
    trust_level="external",
    labels=frozenset(["external", "network"])
)

SINK_LLM_PROMPT = Sink(
    id="llm_prompt",
    sink_type=SinkType.LLM_PROMPT,
    trust_level="external",
    labels=frozenset(["llm", "external"])
)

SINK_LOG_OUTPUT = Sink(
    id="log_output",
    sink_type=SinkType.LOG_OUTPUT,
    trust_level="internal",
    labels=frozenset(["logging", "internal"])
)

SINK_USER_DISPLAY = Sink(
    id="user_display",
    sink_type=SinkType.USER_DISPLAY,
    trust_level="trusted",
    labels=frozenset(["response", "user"])
)

SINK_DATABASE = Sink(
    id="database",
    sink_type=SinkType.DATABASE,
    trust_level="trusted",
    labels=frozenset(["internal", "persistent"])
)


# === Common Flow Rules ===

RULE_NO_PII_TO_EXTERNAL = FlowRule(
    id="no_pii_to_external",
    from_source="*",
    to_sink="external_api",
    action="deny",
    sensitivity_required=DataSensitivity.PII,
    message="PII cannot flow to external APIs"
)

RULE_NO_SECRETS_TO_LLM = FlowRule(
    id="no_secrets_to_llm",
    from_source="environment",
    to_sink="llm_prompt",
    action="deny",
    sensitivity_required=DataSensitivity.SECRET,
    message="Secrets cannot be sent to LLM prompts"
)

RULE_NO_DB_TO_LOGS = FlowRule(
    id="no_db_to_logs",
    from_source="database",
    to_sink="log_output",
    action="redact",
    sensitivity_required=DataSensitivity.CONFIDENTIAL,
    message="Database content must be redacted in logs"
)

RULE_AUDIT_PII_FLOWS = FlowRule(
    id="audit_pii_flows",
    from_source="*",
    to_sink="*",
    action="audit",
    sensitivity_required=DataSensitivity.PII,
    message="All PII flows must be audited"
)


# === Taxonomy Registry ===

class TaxonomyRegistry:
    """Registry for sources, sinks, and flow rules"""

    def __init__(self):
        self._sources: dict[str, Source] = {}
        self._sinks: dict[str, Sink] = {}
        self._rules: dict[str, FlowRule] = {}

        # Register defaults
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register predefined sources, sinks, and rules"""
        # Sources
        self.register_source(SOURCE_USER_INPUT)
        self.register_source(SOURCE_DATABASE)
        self.register_source(SOURCE_ENVIRONMENT)
        self.register_source(SOURCE_LLM_OUTPUT)
        self.register_source(SOURCE_MCP_SERVER)

        # Sinks
        self.register_sink(SINK_EXTERNAL_API)
        self.register_sink(SINK_LLM_PROMPT)
        self.register_sink(SINK_LOG_OUTPUT)
        self.register_sink(SINK_USER_DISPLAY)
        self.register_sink(SINK_DATABASE)

        # Rules
        self.register_rule(RULE_NO_PII_TO_EXTERNAL)
        self.register_rule(RULE_NO_SECRETS_TO_LLM)
        self.register_rule(RULE_NO_DB_TO_LOGS)
        self.register_rule(RULE_AUDIT_PII_FLOWS)

    def register_source(self, source: Source) -> None:
        """Register a source"""
        self._sources[source.id] = source

    def register_sink(self, sink: Sink) -> None:
        """Register a sink"""
        self._sinks[sink.id] = sink

    def register_rule(self, rule: FlowRule) -> None:
        """Register a flow rule"""
        self._rules[rule.id] = rule

    def get_source(self, source_id: str) -> Source | None:
        """Get source by ID"""
        return self._sources.get(source_id)

    def get_sink(self, sink_id: str) -> Sink | None:
        """Get sink by ID"""
        return self._sinks.get(sink_id)

    def get_rule(self, rule_id: str) -> FlowRule | None:
        """Get rule by ID"""
        return self._rules.get(rule_id)

    def find_applicable_rules(self, source: Source, sink: Sink) -> list[FlowRule]:
        """Find all rules applicable to a source/sink pair"""
        return [
            rule for rule in self._rules.values()
            if rule.applies_to(source, sink)
        ]

    def list_sources(self) -> list[Source]:
        """List all registered sources"""
        return list(self._sources.values())

    def list_sinks(self) -> list[Sink]:
        """List all registered sinks"""
        return list(self._sinks.values())

    def list_rules(self) -> list[FlowRule]:
        """List all registered rules"""
        return list(self._rules.values())


# Global registry instance
_global_registry = TaxonomyRegistry()


def get_registry() -> TaxonomyRegistry:
    """Get the global taxonomy registry"""
    return _global_registry


__all__ = [
    # Enums
    "SourceType",
    "SinkType",
    "DataSensitivity",
    # Core types
    "Source",
    "Sink",
    "FlowRule",
    # Predefined sources
    "SOURCE_USER_INPUT",
    "SOURCE_DATABASE",
    "SOURCE_ENVIRONMENT",
    "SOURCE_LLM_OUTPUT",
    "SOURCE_MCP_SERVER",
    # Predefined sinks
    "SINK_EXTERNAL_API",
    "SINK_LLM_PROMPT",
    "SINK_LOG_OUTPUT",
    "SINK_USER_DISPLAY",
    "SINK_DATABASE",
    # Predefined rules
    "RULE_NO_PII_TO_EXTERNAL",
    "RULE_NO_SECRETS_TO_LLM",
    "RULE_NO_DB_TO_LOGS",
    "RULE_AUDIT_PII_FLOWS",
    # Registry
    "TaxonomyRegistry",
    "get_registry",
]

