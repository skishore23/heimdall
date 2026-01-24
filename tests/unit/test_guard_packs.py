"""
Unit tests for guard packs
"""

import pytest

from guards.pii.guards import pii_detect, pii_redact
from guards.politics.guards import politics_block
from guards.schema.guards import schema_validate_json
from guards.toxicity.guards import toxicity_block, toxicity_detect
from heimdall import get_violations, is_left


class TestPIIGuards:
    """Test PII guard implementations"""

    @pytest.mark.asyncio
    async def test_pii_redact_email(self):
        """Test PII redaction for emails"""
        guard = pii_redact(types=["EMAIL"], mode="mask")

        ctx = {"output": "Contact me at john@example.com for details"}
        result = await guard(ctx)

        assert not is_left(result)
        assert "[EMAIL]" in result["right"]["output"]
        assert "john@example.com" not in result["right"]["output"]

    @pytest.mark.asyncio
    async def test_pii_redact_remove(self):
        """Test PII removal"""
        guard = pii_redact(types=["EMAIL"], mode="remove")

        ctx = {"output": "Contact me at john@example.com for details"}
        result = await guard(ctx)

        assert not is_left(result)
        assert "john@example.com" not in result["right"]["output"]
        assert "Contact me at  for details" in result["right"]["output"]

    @pytest.mark.asyncio
    async def test_pii_detect(self):
        """Test PII detection"""
        guard = pii_detect(types=["EMAIL"], threshold=1)

        ctx = {"output": "Contact me at john@example.com for details"}
        result = await guard(ctx)

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "pii.detect"


class TestPoliticsGuards:
    """Test politics guard implementations"""

    @pytest.mark.asyncio
    async def test_politics_block_violation(self):
        """Test politics blocking with violation"""
        guard = politics_block(
            patterns_strong=["\\bvote for\\b", "\\belection\\b"],
            threshold=0.5
        )

        ctx = {"output": "You should vote for the candidate in the election"}
        result = await guard(ctx)

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "politics.block"

    @pytest.mark.asyncio
    async def test_politics_block_allowed(self):
        """Test politics blocking with allowed content"""
        guard = politics_block(
            patterns_strong=["\\bvote for\\b"],
            allow=["what is a constitution"],
            threshold=0.5
        )

        ctx = {"output": "What is a constitution and how does it work?"}
        result = await guard(ctx)

        assert not is_left(result)

    @pytest.mark.asyncio
    async def test_politics_block_safe_content(self):
        """Test politics blocking with safe content"""
        guard = politics_block(
            patterns_strong=["\\bvote for\\b"],
            threshold=0.5
        )

        ctx = {"output": "This is a normal conversation about the weather"}
        result = await guard(ctx)

        assert not is_left(result)


class TestSchemaGuards:
    """Test schema guard implementations"""

    @pytest.mark.asyncio
    async def test_schema_validate_success(self):
        """Test successful schema validation"""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"}
            },
            "required": ["name"]
        }

        guard = schema_validate_json(schema)

        ctx = {"output": {"name": "John", "age": 30}}
        result = await guard(ctx)

        assert not is_left(result)

    @pytest.mark.asyncio
    async def test_schema_validate_failure(self):
        """Test schema validation failure"""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"}
            },
            "required": ["name"]
        }

        guard = schema_validate_json(schema)

        ctx = {"output": {"age": "thirty"}}  # Missing required field, wrong type
        result = await guard(ctx)

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "schema.validate.json"

    @pytest.mark.asyncio
    async def test_schema_validate_string_input(self):
        """Test schema validation with string input"""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            }
        }

        guard = schema_validate_json(schema)

        ctx = {"output": '{"name": "John"}'}  # JSON string
        result = await guard(ctx)

        assert not is_left(result)

    @pytest.mark.asyncio
    async def test_schema_validate_invalid_json(self):
        """Test schema validation with invalid JSON"""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            }
        }

        guard = schema_validate_json(schema)

        ctx = {"output": '{"name": "John"'}  # Invalid JSON
        result = await guard(ctx)

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        assert "Invalid JSON" in violations[0]["message"]


class TestToxicityGuards:
    """Test toxicity guard implementations"""

    @pytest.mark.asyncio
    async def test_toxicity_detect_profanity(self):
        """Test toxicity detection for profanity"""
        guard = toxicity_detect(categories=["profanity"], threshold=0.1)

        ctx = {"output": "This is fucking ridiculous"}
        result = await guard(ctx)

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "toxicity.detect"
        assert "Toxic content detected" in violations[0]["message"]

    @pytest.mark.asyncio
    async def test_toxicity_detect_harassment(self):
        """Test toxicity detection for harassment"""
        guard = toxicity_detect(categories=["harassment"], threshold=0.1)

        ctx = {"output": "You are such an idiot"}
        result = await guard(ctx)

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "toxicity.detect"

    @pytest.mark.asyncio
    async def test_toxicity_detect_threats(self):
        """Test toxicity detection for threats"""
        guard = toxicity_detect(categories=["threats"], threshold=0.1)

        ctx = {"output": "I will hurt you if you don't comply"}
        result = await guard(ctx)

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "toxicity.detect"

    @pytest.mark.asyncio
    async def test_toxicity_detect_safe_content(self):
        """Test toxicity detection with safe content"""
        guard = toxicity_detect(categories=["profanity", "harassment"], threshold=0.3)

        ctx = {"output": "This is a normal conversation about the weather"}
        result = await guard(ctx)

        assert not is_left(result)

    @pytest.mark.asyncio
    async def test_toxicity_block_high_threshold(self):
        """Test toxicity blocking with high threshold"""
        guard = toxicity_block(categories=["harassment"], threshold=0.8)

        ctx = {"output": "You are an idiot"}  # Should not reach high threshold
        result = await guard(ctx)

        assert not is_left(result)  # Should pass due to high threshold

    @pytest.mark.asyncio
    async def test_toxicity_block_low_threshold(self):
        """Test toxicity blocking with low threshold"""
        guard = toxicity_block(categories=["harassment"], threshold=0.1)

        ctx = {"output": "You are an idiot"}  # Should be blocked with low threshold
        result = await guard(ctx)

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "toxicity.detect"  # Uses same rule_id as detect

    @pytest.mark.asyncio
    async def test_toxicity_multiple_categories(self):
        """Test toxicity detection with multiple categories"""
        guard = toxicity_detect(categories=["profanity", "harassment"], threshold=0.1)

        ctx = {"output": "You fucking idiot"}  # Contains both profanity and harassment
        result = await guard(ctx)

        assert is_left(result)
        violations = get_violations(result)
        assert len(violations) == 1
        # Should have higher score due to multiple categories
        assert violations[0]["score"] > 0.3
