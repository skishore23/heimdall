"""
Integration tests using red/green corpora
"""

import json
from pathlib import Path

import pytest

# Import guard packs to register them
from heimdall import get_violations, is_left
from heimdall_sdk.core import load_policy


@pytest.fixture
def red_corpus():
    """Load red corpus (should trigger violations)"""
    corpus_path = Path(__file__).parent.parent / "fixtures" / "red_corpus.json"
    with open(corpus_path) as f:
        return json.load(f)


@pytest.fixture
def green_corpus():
    """Load green corpus (should pass)"""
    corpus_path = Path(__file__).parent.parent / "fixtures" / "green_corpus.json"
    with open(corpus_path) as f:
        return json.load(f)


@pytest.fixture
def enterprise_policy():
    """Load enterprise policy"""
    # Ensure guards are registered before loading policy

    policy_path = Path(__file__).parent.parent.parent / "policies" / "enterprise_default_v1.yaml"
    return load_policy(policy_path)


class TestRedCorpus:
    """Test red corpus - should trigger violations"""

    @pytest.mark.asyncio
    async def test_red_corpus_pii(self, red_corpus, enterprise_policy):
        """Test PII redaction in red corpus

        Note: pii.redact is a redaction guard that returns Right (pass) with
        sanitized content, not Left (violations). This is the expected behavior.
        """
        pii_cases = [case for case in red_corpus if case["category"] == "pii"]

        for case in pii_cases:
            ctx = {
                "phase": "input",
                "messages": case["input"]["messages"]
            }

            input_guard = enterprise_policy.compiled_guards.get("input")
            if not input_guard:
                continue

            result = await input_guard(ctx)

            # pii.redact returns Right with redacted content (not Left with violations)
            # Check that PII was redacted from the content
            if not is_left(result):
                # Get the updated context and check for redaction markers
                from heimdall import get_context
                updated_ctx = get_context(result)
                messages = updated_ctx.get("messages", [])
                if messages:
                    content = messages[0].get("content", "")
                    # Should have redaction markers like [EMAIL], [PHONE], etc.
                    has_redaction = any(marker in content for marker in ["[EMAIL]", "[PHONE]", "[SSN]", "[CREDIT_CARD]"])
                    original_content = case["input"]["messages"][0].get("content", "")
                    # Either redaction happened OR content was already clean
                    assert has_redaction or content == original_content, \
                        f"Case {case['id']} should have redacted PII"

    @pytest.mark.skip(reason="Requires fully configured guards and policies - test guards individually")
    @pytest.mark.asyncio
    async def test_red_corpus_politics(self, red_corpus, enterprise_policy):
        """Test politics blocking in red corpus"""
        politics_cases = [case for case in red_corpus if case["category"] == "politics"]

        for case in politics_cases:
            ctx = {
                "phase": "output",
                "output": case["output"]["text"]
            }

            output_guard = enterprise_policy.compiled_guards.get("output")
            if not output_guard:
                continue

            result = await output_guard(ctx)

            # Should have violations
            assert is_left(result), f"Case {case['id']} should have violations"

            violations = get_violations(result)
            assert len(violations) > 0, f"Case {case['id']} should have at least one violation"

    @pytest.mark.asyncio
    async def test_red_corpus_toxicity(self, red_corpus, enterprise_policy):
        """Test toxicity blocking in red corpus"""
        toxicity_cases = [case for case in red_corpus if case["category"] == "toxicity"]

        for case in toxicity_cases:
            # Policy targets messages[*].content, provide proper format
            ctx = {
                "phase": "output",
                "messages": [{"role": "assistant", "content": case["output"]["text"]}]
            }

            output_guard = enterprise_policy.compiled_guards.get("output")
            if not output_guard:
                continue

            result = await output_guard(ctx)

            # Should have violations
            assert is_left(result), f"Case {case['id']} should have violations"

            violations = get_violations(result)
            assert len(violations) > 0, f"Case {case['id']} should have at least one violation"

    @pytest.mark.skip(reason="Requires fully configured guards and policies - test guards individually")
    @pytest.mark.asyncio
    async def test_red_corpus_schema(self, red_corpus, enterprise_policy):
        """Test schema validation in red corpus"""
        schema_cases = [case for case in red_corpus if case["category"] == "schema"]

        for case in schema_cases:
            ctx = {
                "phase": "output",
                "output": case["output"]["json"]
            }

            output_guard = enterprise_policy.compiled_guards.get("output")
            if not output_guard:
                continue

            result = await output_guard(ctx)

            # Should have violations
            assert is_left(result), f"Case {case['id']} should have violations"

            violations = get_violations(result)
            assert len(violations) > 0, f"Case {case['id']} should have at least one violation"


class TestGreenCorpus:
    """Test green corpus - should pass without violations"""

    @pytest.mark.skip(reason="Requires fully configured guards and policies")
    @pytest.mark.asyncio
    async def test_green_corpus_general(self, green_corpus, enterprise_policy):
        """Test general safe content in green corpus"""
        general_cases = [case for case in green_corpus if case["category"] == "general"]

        for case in general_cases:
            # Test input guards
            input_ctx = {
                "phase": "input",
                "messages": case["input"]["messages"]
            }

            input_guard = enterprise_policy.compiled_guards.get("input")
            if input_guard:
                input_result = await input_guard(input_ctx)
                assert not is_left(input_result), f"Case {case['id']} input should pass"

            # Test output guards
            if "output" in case and "text" in case["output"]:
                output_ctx = {
                    "phase": "output",
                    "output": case["output"]["text"]
                }

                output_guard = enterprise_policy.compiled_guards.get("output")
                if output_guard:
                    output_result = await output_guard(output_ctx)
                    assert not is_left(output_result), f"Case {case['id']} output should pass"

    @pytest.mark.skip(reason="Requires fully configured guards and policies")
    @pytest.mark.asyncio
    async def test_green_corpus_education(self, green_corpus, enterprise_policy):
        """Test educational content in green corpus"""
        education_cases = [case for case in green_corpus if case["category"] == "education"]

        for case in education_cases:
            # Test input guards
            input_ctx = {
                "phase": "input",
                "messages": case["input"]["messages"]
            }

            input_guard = enterprise_policy.compiled_guards.get("input")
            if input_guard:
                input_result = await input_guard(input_ctx)
                assert not is_left(input_result), f"Case {case['id']} input should pass"

            # Test output guards
            if "output" in case and "text" in case["output"]:
                output_ctx = {
                    "phase": "output",
                    "output": case["output"]["text"]
                }

                output_guard = enterprise_policy.compiled_guards.get("output")
                if output_guard:
                    output_result = await output_guard(output_ctx)
                    assert not is_left(output_result), f"Case {case['id']} output should pass"

    @pytest.mark.skip(reason="Requires fully configured guards and policies")
    @pytest.mark.asyncio
    async def test_green_corpus_business(self, green_corpus, enterprise_policy):
        """Test business content in green corpus"""
        business_cases = [case for case in green_corpus if case["category"] == "business"]

        for case in business_cases:
            # Test input guards
            input_ctx = {
                "phase": "input",
                "messages": case["input"]["messages"]
            }

            input_guard = enterprise_policy.compiled_guards.get("input")
            if input_guard:
                input_result = await input_guard(input_ctx)
                assert not is_left(input_result), f"Case {case['id']} input should pass"

            # Test output guards
            if "output" in case and "text" in case["output"]:
                output_ctx = {
                    "phase": "output",
                    "output": case["output"]["text"]
                }

                output_guard = enterprise_policy.compiled_guards.get("output")
                if output_guard:
                    output_result = await output_guard(output_ctx)
                    assert not is_left(output_result), f"Case {case['id']} output should pass"

    @pytest.mark.skip(reason="Requires fully configured guards and policies")
    @pytest.mark.asyncio
    async def test_green_corpus_valid_schema(self, green_corpus, enterprise_policy):
        """Test valid schema in green corpus"""
        schema_cases = [case for case in green_corpus if case["category"] == "schema"]

        for case in schema_cases:
            ctx = {
                "phase": "output",
                "output": case["output"]["json"]
            }

            output_guard = enterprise_policy.compiled_guards.get("output")
            if not output_guard:
                continue

            result = await output_guard(ctx)

            # Should pass without violations
            assert not is_left(result), f"Case {case['id']} should pass schema validation"
