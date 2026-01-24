"""
Tests for dataflow and taint tracking
"""

from heimdall.dataflow import (
    DataflowPolicy,
    DataflowRule,
    DataflowSink,
    DataflowSource,
    TaintMetadata,
    attach_taint_to_context,
    extract_taint_from_context,
    parse_dataflow_yaml,
    propagate_taint,
)


def test_dataflow_source():
    """Test DataflowSource creation"""
    source = DataflowSource(
        path="messages[*].content",
        classification={"pii", "user_input"},
        origin="user"
    )

    assert source.path == "messages[*].content"
    assert "pii" in source.classification
    assert source.origin == "user"


def test_dataflow_sink():
    """Test DataflowSink creation"""
    sink = DataflowSink(
        target="tool:email.send",
        sink_type="tool",
        allowed_classifications={"public"}
    )

    assert sink.target == "tool:email.send"
    assert sink.sink_type == "tool"
    assert "public" in sink.allowed_classifications


def test_dataflow_rule_matches():
    """Test DataflowRule matching"""
    rule = DataflowRule(
        rule_id="pii.to_email",
        source_pattern=r"db\.users\..*",
        sink_pattern=r"tool:email\..*",
        forbidden_classifications={"pii"}
    )

    source = DataflowSource(
        path="db.users.email",
        classification={"pii"}
    )

    sink = DataflowSink(
        target="tool:email.send",
        sink_type="tool"
    )

    assert rule.matches_flow(source, sink) is True


def test_dataflow_rule_no_match():
    """Test DataflowRule not matching"""
    rule = DataflowRule(
        rule_id="pii.to_email",
        source_pattern=r"db\.users\..*",
        sink_pattern=r"tool:email\..*",
        forbidden_classifications={"pii"}
    )

    source = DataflowSource(
        path="messages.content",  # Different source
        classification={"pii"}
    )

    sink = DataflowSink(
        target="tool:email.send",
        sink_type="tool"
    )

    assert rule.matches_flow(source, sink) is False


def test_taint_metadata():
    """Test TaintMetadata creation and manipulation"""
    taint = TaintMetadata(
        sources=[],
        classifications={"pii", "sensitive"},
        propagation_path=["step1", "step2"]
    )

    assert "pii" in taint.classifications
    assert len(taint.propagation_path) == 2


def test_taint_metadata_merge():
    """Test merging taint metadata"""
    taint1 = TaintMetadata(
        classifications={"pii"},
        propagation_path=["step1"]
    )

    taint2 = TaintMetadata(
        classifications={"sensitive"},
        propagation_path=["step2"]
    )

    merged = taint1.merge(taint2)

    assert "pii" in merged.classifications
    assert "sensitive" in merged.classifications
    assert len(merged.propagation_path) == 2


def test_taint_metadata_to_baggage():
    """Test converting taint to W3C baggage"""
    taint = TaintMetadata(
        classifications={"pii", "sensitive"},
        propagation_path=["step1", "step2", "step3"]
    )

    baggage = taint.to_baggage()

    assert "taint.classifications" in baggage
    assert "taint.source_count" in baggage
    assert "taint.path" in baggage

    # Classifications should be sorted
    assert "pii" in baggage["taint.classifications"]
    assert "sensitive" in baggage["taint.classifications"]


def test_taint_metadata_from_baggage():
    """Test parsing taint from W3C baggage"""
    baggage = {
        "taint.classifications": "pii,sensitive",
        "taint.source_count": "2",
        "taint.path": "step1|step2|step3"
    }

    taint = TaintMetadata.from_baggage(baggage)

    assert "pii" in taint.classifications
    assert "sensitive" in taint.classifications
    assert len(taint.propagation_path) == 3


def test_dataflow_policy():
    """Test DataflowPolicy creation and checking"""
    source = DataflowSource(
        path="db.users.email",
        classification={"pii"}
    )

    sink = DataflowSink(
        target="tool:email.send",
        sink_type="tool",
        allowed_classifications={"public"}
    )

    rule = DataflowRule(
        rule_id="pii.to_email",
        source_pattern=r"db\.users\..*",
        sink_pattern=r"tool:email\..*",
        forbidden_classifications={"pii"}
    )

    policy = DataflowPolicy(
        sources=[source],
        sinks=[sink],
        rules=[rule]
    )

    # Check flow violation
    taint = TaintMetadata(classifications={"pii"})
    violations = policy.check_flow("db.users.email", "tool:email.send", taint)

    assert len(violations) == 1
    assert violations[0].rule_id == "pii.to_email"


def test_dataflow_policy_classify_source():
    """Test classifying a source"""
    source = DataflowSource(
        path="db.users.email",
        classification={"pii", "sensitive"}
    )

    policy = DataflowPolicy(
        sources=[source],
        sinks=[],
        rules=[]
    )

    classifications = policy.classify_source("db.users.email")

    assert "pii" in classifications
    assert "sensitive" in classifications


def test_dataflow_policy_is_sink_allowed():
    """Test checking if sink allows classifications"""
    sink = DataflowSink(
        target="tool:logger",
        sink_type="tool",
        allowed_classifications={"public", "non_sensitive"}
    )

    policy = DataflowPolicy(
        sources=[],
        sinks=[sink],
        rules=[]
    )

    # Allowed classifications
    assert policy.is_sink_allowed("tool:logger", {"public"}) is True

    # Forbidden classifications
    assert policy.is_sink_allowed("tool:logger", {"pii"}) is False


def test_parse_dataflow_yaml():
    """Test parsing dataflow policy from YAML"""
    yaml_data = {
        "sources": [
            {
                "path": "messages[*].content",
                "classification": ["user_input"]
            }
        ],
        "sinks": [
            {
                "target": "tool:email.send",
                "type": "tool",
                "allowed": []
            }
        ],
        "rules": [
            {
                "id": "user_input.to_email",
                "from": r"messages\[.*\]\.content",
                "to": r"tool:email\..*",
                "forbid_if": ["pii"],
                "description": "Prevent PII in emails"
            }
        ]
    }

    policy = parse_dataflow_yaml(yaml_data)

    assert len(policy.sources) == 1
    assert len(policy.sinks) == 1
    assert len(policy.rules) == 1


def test_attach_and_extract_taint():
    """Test attaching and extracting taint from context"""
    ctx = {"user": "test"}
    taint = TaintMetadata(classifications={"pii"})

    # Attach
    ctx = attach_taint_to_context(ctx, taint)
    assert "_taint" in ctx

    # Extract
    extracted = extract_taint_from_context(ctx)
    assert extracted is not None
    assert "pii" in extracted.classifications


def test_propagate_taint():
    """Test taint propagation"""
    taint = TaintMetadata(
        classifications={"pii"},
        propagation_path=[]
    )

    ctx = attach_taint_to_context({"test": "data"}, taint)

    # Propagate through operation
    ctx = propagate_taint(ctx, "operation1")

    taint = extract_taint_from_context(ctx)
    assert "operation1" in taint.propagation_path

