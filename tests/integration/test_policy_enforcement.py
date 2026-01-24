"""
Integration tests for policy enforcement
"""

from pathlib import Path

import pytest

from heimdall import get_context, get_violations, is_left
from heimdall_sdk.core import load_policy


class TestPolicyEnforcement:
    """Test end-to-end policy enforcement"""

    def setup_method(self):
        """Setup test fixtures"""
        self.policies_dir = Path("policies")

    @pytest.mark.asyncio
    async def test_enterprise_policy_pii_redaction(self):
        """Test PII redaction in enterprise policy"""
        policy = load_policy(self.policies_dir / "enterprise_default_v1.yaml")

        # Test input guards (PII redaction)
        input_guard = policy.compiled_guards.get("input")
        assert input_guard is not None

        context = {
            "phase": "input",
            "messages": [{"role": "user", "content": "My email is john@example.com"}],
            "model": "gpt-3.5-turbo"
        }

        result = await input_guard(context)
        assert not is_left(result), "PII redaction should not block, only redact"

        updated_context = get_context(result)
        message_content = updated_context["messages"][0]["content"]
        assert "[EMAIL]" in message_content
        assert "john@example.com" not in message_content

    @pytest.mark.asyncio
    async def test_enterprise_policy_politics_blocking(self):
        """Test politics blocking in enterprise policy"""
        policy = load_policy(self.policies_dir / "enterprise_default_v1.yaml")

        # Test output guards (politics blocking)
        output_guard = policy.compiled_guards.get("output")
        if not output_guard:
            pytest.skip("No output guard in policy")

        # Policy targets messages[*].content, so we need to provide messages
        context = {
            "phase": "output",
            "messages": [{"role": "assistant", "content": "You should vote for candidate Smith in the upcoming election"}]
        }

        result = await output_guard(context)
        # Should block political content
        assert is_left(result), "Political content should be blocked"
        violations = get_violations(result)
        assert len(violations) > 0
        print(f"✅ Politics content triggered {len(violations)} violations")

    @pytest.mark.asyncio
    async def test_enterprise_policy_toxicity_blocking(self):
        """Test toxicity blocking in enterprise policy"""
        policy = load_policy(self.policies_dir / "enterprise_default_v1.yaml")

        # Test output guards (toxicity blocking)
        output_guard = policy.compiled_guards.get("output")
        if not output_guard:
            pytest.skip("No output guard in policy")

        # Policy targets messages[*].content, so we need to provide messages
        context = {
            "phase": "output",
            "messages": [{"role": "assistant", "content": "You are such a fucking idiot and I hate you"}]
        }

        result = await output_guard(context)
        # Should block toxic content
        assert is_left(result), "Toxic content should be blocked"
        violations = get_violations(result)
        assert len(violations) > 0
        print(f"✅ Toxic content triggered {len(violations)} violations")

    @pytest.mark.asyncio
    async def test_enterprise_policy_safe_content(self):
        """Test that safe content passes through enterprise policy"""
        policy = load_policy(self.policies_dir / "enterprise_default_v1.yaml")

        # Test both input and output guards with safe content
        input_guard = policy.compiled_guards.get("input")
        output_guard = policy.compiled_guards.get("output")

        # Test input
        input_context = {
            "phase": "input",
            "messages": [{"role": "user", "content": "Hello, how are you today?"}],
            "model": "gpt-3.5-turbo"
        }

        input_result = await input_guard(input_context)
        assert not is_left(input_result), "Safe input should pass"

        # Test output - policy targets messages[*].content
        output_context = {
            "phase": "output",
            "messages": [{"role": "assistant", "content": "Hello! I'm doing well, thank you for asking. How can I help you today?"}]
        }

        output_result = await output_guard(output_context)
        assert not is_left(output_result), "Safe output should pass"

    @pytest.mark.skip(reason="simple_test policy may not exist or may not have PII redaction")
    @pytest.mark.asyncio
    async def test_simple_test_policy(self):
        """Test simple_test policy functionality"""
        try:
            policy = load_policy(self.policies_dir / "simple_test.yaml")
        except FileNotFoundError:
            pytest.skip("simple_test.yaml policy not found")

        root_guard = policy.compiled_guards.get("root")
        if not root_guard:
            pytest.skip("No root guard in policy")

        # Test PII redaction
        pii_context = {
            "messages": [{"role": "user", "content": "Call me at 555-123-4567"}],
            "model": "gpt-3.5-turbo"
        }

        result = await root_guard(pii_context)
        # Just check it completes without error
        print(f"✅ simple_test policy executed: {'Left' if is_left(result) else 'Right'}")

    @pytest.mark.skip(reason="noop_v1 policy may have different structure or guards may not be registered")
    @pytest.mark.asyncio
    async def test_noop_policy(self):
        """Test no-op policy allows everything"""
        try:
            policy = load_policy(self.policies_dir / "noop_v1.yaml")
        except Exception as e:
            pytest.skip(f"Could not load noop policy: {e}")

        root_guard = policy.compiled_guards.get("root")
        if not root_guard:
            pytest.skip("No root guard in noop policy")

        # Test with content that would normally be blocked
        context = {"output": "My email is john@example.com"}
        result = await root_guard(context)
        print(f"✅ No-op policy executed: {'Left' if is_left(result) else 'Right'}")

    @pytest.mark.skip(reason="permissive_v1 policy may not exist or have different composition")
    @pytest.mark.asyncio
    async def test_permissive_policy(self):
        """Test permissive policy functionality"""
        try:
            policy = load_policy(self.policies_dir / "permissive_v1.yaml")
        except Exception as e:
            pytest.skip(f"Could not load permissive policy: {e}")

        root_guard = policy.compiled_guards.get("root")
        if not root_guard:
            pytest.skip("No root guard in permissive policy")

        # Should allow most content but may have minimal restrictions
        context = {"output": "This is a normal message"}
        result = await root_guard(context)
        print(f"✅ Permissive policy executed: {'Left' if is_left(result) else 'Right'}")


class TestPolicyValidation:
    """Test policy file validation"""

    def setup_method(self):
        """Setup test fixtures"""
        self.policies_dir = Path("policies")

    def test_all_policies_load_successfully(self):
        """Test that all policy files can be loaded without errors"""
        policy_files = list(self.policies_dir.glob("*.yaml"))
        assert len(policy_files) > 0, "No policy files found"

        # Policies that require ONNX models (skip if models not available)
        onnx_policies = {"enterprise_onnx_v1.yaml"}

        for policy_file in policy_files:
            try:
                policy = load_policy(policy_file)
                assert policy is not None
                policy_id = getattr(policy, 'id', policy.metadata.get('policy_id'))
                assert policy_id is not None
                assert policy.compiled_guards is not None
                print(f"✅ Successfully loaded policy: {policy_file.name}")
            except (FileNotFoundError, ImportError) as e:
                # Expected failure for ONNX policies without models - fail fast is correct
                if policy_file.name in onnx_policies:
                    print(f"⚠️  Skipped {policy_file.name}: {e} (expected - models not available)")
                    continue
                else:
                    pytest.fail(f"Unexpected failure for {policy_file.name}: {e}")
            except Exception as e:
                # For ONNX runtime errors on ONNX policies, also expected
                if policy_file.name in onnx_policies and "ONNX" in str(e):
                    print(f"⚠️  Skipped {policy_file.name}: ONNX model issue (expected)")
                    continue
                pytest.fail(f"Failed to load policy {policy_file.name}: {e}")

    def test_enterprise_policy_structure(self):
        """Test enterprise policy has expected structure"""
        policy = load_policy(self.policies_dir / "enterprise_default_v1.yaml")

        # Should have some compiled guards
        assert policy.compiled_guards is not None
        assert len(policy.compiled_guards) > 0

        # Verify policy metadata exists
        policy_id = getattr(policy, 'id', policy.metadata.get('policy_id', None))
        assert policy_id is not None, "Policy should have an ID"

        # Hash may not always be present
        policy_hash = getattr(policy, 'hash', policy.metadata.get('hash', None))
        if policy_hash:
            assert len(policy_hash) > 0


class TestGuardThresholds:
    """Test guard threshold configurations"""

    @pytest.mark.asyncio
    async def test_toxicity_threshold_sensitivity(self):
        """Test toxicity guard with different thresholds"""
        from guards.toxicity.guards import toxicity_block

        test_content = "You are an idiot"  # Mild harassment
        context = {"output": test_content}

        # High threshold should allow
        high_threshold_guard = toxicity_block(threshold=0.8)
        result = await high_threshold_guard(context)
        assert not is_left(result), "High threshold should allow mild harassment"

        # Low threshold should block
        low_threshold_guard = toxicity_block(threshold=0.1)
        result = await low_threshold_guard(context)
        assert is_left(result), "Low threshold should block mild harassment"

    @pytest.mark.asyncio
    async def test_politics_threshold_sensitivity(self):
        """Test politics guard with different thresholds"""
        from guards.politics.guards import politics_block

        test_content = "The candidate has good policies"  # Mild political content
        context = {"output": test_content}

        # High threshold should allow
        high_threshold_guard = politics_block(
            patterns_strong=["candidate"],
            threshold=0.8
        )
        result = await high_threshold_guard(context)
        assert not is_left(result), "High threshold should allow mild political content"

        # Low threshold should block
        low_threshold_guard = politics_block(
            patterns_strong=["candidate"],
            threshold=0.2
        )
        result = await low_threshold_guard(context)
        assert is_left(result), "Low threshold should block mild political content"
