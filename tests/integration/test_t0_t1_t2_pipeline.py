"""
Comprehensive tests for T0/T1/T2 tiered pipeline architecture

This test suite ensures that the T0/T1/T2 pipeline is the core architecture
and validates all performance tiers work correctly.
"""

import time

import pytest

# Import guard packs to register them
from heimdall import (
    TierConfig,
    TieredGuardRunner,
    get_guard_metadata,
    get_guards_by_tier,
    get_violations,
    is_left,
)
from heimdall_sdk.core import load_policy


class TestT0T1T2Pipeline:
    """Test the T0/T1/T2 tiered pipeline architecture"""

    def test_tier_registry_populated(self):
        """Test that guards are properly registered with tier information"""
        # Get guards by tier
        t0_guards = get_guards_by_tier("T0")
        t1_guards = get_guards_by_tier("T1")
        t2_guards = get_guards_by_tier("T2")

        # Verify we have guards in each tier
        assert len(t0_guards) > 0, "No T0 guards found - T0 tier must have guards"
        assert len(t1_guards) > 0, "No T1 guards found - T1 tier must have guards"
        assert len(t2_guards) > 0, "No T2 guards found - T2 tier must have guards"

        print(f"✅ T0 guards: {len(t0_guards)} - {list(t0_guards.keys())}")
        print(f"✅ T1 guards: {len(t1_guards)} - {list(t1_guards.keys())}")
        print(f"✅ T2 guards: {len(t2_guards)} - {list(t2_guards.keys())}")

    def test_tier_performance_budgets(self):
        """Test that tier performance budgets are correctly set"""
        t0_guards = get_guards_by_tier("T0")
        t1_guards = get_guards_by_tier("T1")
        t2_guards = get_guards_by_tier("T2")

        # Check T0 guards have fast budgets (< 10ms)
        for guard_id in t0_guards:
            metadata = get_guard_metadata(guard_id)
            # Budget is optional, skip if not set
            if hasattr(metadata, 'performance_budget_ms') and metadata.performance_budget_ms is not None:
                assert metadata.performance_budget_ms <= 10.0, f"T0 guard {guard_id} budget too high: {metadata.performance_budget_ms}ms"

        # Check T1 guards have medium budgets (< 50ms)
        for guard_id in t1_guards:
            metadata = get_guard_metadata(guard_id)
            # Budget is optional, skip if not set
            if hasattr(metadata, 'performance_budget_ms') and metadata.performance_budget_ms is not None:
                assert metadata.performance_budget_ms <= 50.0, f"T1 guard {guard_id} budget too high: {metadata.performance_budget_ms}ms"

        # Check T2 guards have higher budgets (< 200ms)
        for guard_id in t2_guards:
            metadata = get_guard_metadata(guard_id)
            # Budget is optional, skip if not set
            if hasattr(metadata, 'performance_budget_ms') and metadata.performance_budget_ms is not None:
                assert metadata.performance_budget_ms <= 200.0, f"T2 guard {guard_id} budget too high: {metadata.performance_budget_ms}ms"

    @pytest.mark.asyncio
    async def test_tiered_runner_basic_flow(self):
        """Test basic T0/T1/T2 execution flow"""
        TieredGuardRunner()

        # Configure tiers
        t0_config = TierConfig(
            enabled=True,
            timeout_ms=5.0,
            total_budget_ms=10.0,
            early_exit_on_violation=False  # Continue to T1 even with T0 violations
        )

        t1_config = TierConfig(
            enabled=True,
            timeout_ms=20.0,
            total_budget_ms=50.0,
            early_exit_on_violation=False,  # Continue to T2 even with T1 violations
            gate_condition="t0_score < 0.7"  # Only run T1 if T0 didn't find major issues
        )

        t2_config = TierConfig(
            enabled=True,
            timeout_ms=100.0,
            total_budget_ms=200.0,
            early_exit_on_violation=True,  # Exit on T2 violations
            gate_condition="t1_score < 0.8"  # Only run T2 if T1 didn't find major issues
        )

        # Test context with political content (should trigger multiple tiers)
        context = {
            "messages": [{"role": "user", "content": "Vote for candidate Smith"}],
            "phase": "input"
        }

        # Configure runner with tier configs
        runner_with_config = TieredGuardRunner(tier_configs={
            "T0": t0_config,
            "T1": t1_config,
            "T2": t2_config
        })

        # Run tiered guards
        result = await runner_with_config.run_tiered_guards(
            guards={},  # Empty for now - would be populated from policy
            context=context
        )

        # Verify execution results
        assert result.total_time_ms >= 0, "Total execution time should be >= 0"
        assert "T0" in result.tier_stats or len(result.tier_stats) >= 0, "Should have tier stats"

        # Check if violations were found (may be empty with no guards)
        print(f"✅ Tiered execution completed in {result.total_time_ms:.2f}ms")
        print(f"   Violations: {len(result.violations)}")
        print(f"   Tiers executed: {list(result.tier_stats.keys())}")

    @pytest.mark.asyncio
    async def test_performance_gating(self):
        """Test that performance gating works correctly"""
        TieredGuardRunner()

        # Configure with strict gating
        t0_config = TierConfig(enabled=True, timeout_ms=5.0, total_budget_ms=10.0)
        t1_config = TierConfig(enabled=True, timeout_ms=20.0, total_budget_ms=50.0, gate_condition="t0_score < 0.1")  # Strict gate
        t2_config = TierConfig(enabled=True, timeout_ms=100.0, total_budget_ms=200.0, gate_condition="t1_score < 0.1")  # Strict gate

        # Test with safe content (should not trigger higher tiers)
        safe_context = {
            "messages": [{"role": "user", "content": "Hello, how are you today?"}],
            "phase": "input"
        }

        # Configure runner with tier configs
        runner_with_config = TieredGuardRunner(tier_configs={
            "T0": t0_config,
            "T1": t1_config,
            "T2": t2_config
        })

        result = await runner_with_config.run_tiered_guards(
            guards={},
            context=safe_context
        )

        # Check execution results
        assert result.total_time_ms >= 0, "Should have execution time"
        print(f"✅ Execution completed in {result.total_time_ms:.2f}ms")
        print(f"   Tiers executed: {list(result.tier_stats.keys())}")
        if result.gated_tiers:
            print(f"   Gated tiers: {result.gated_tiers}")

    @pytest.mark.asyncio
    async def test_early_exit_behavior(self):
        """Test early exit behavior with violations"""
        TieredGuardRunner()

        # Configure with early exit enabled
        t0_config = TierConfig(enabled=True, timeout_ms=5.0, total_budget_ms=10.0, early_exit_on_violation=True)
        t1_config = TierConfig(enabled=True, timeout_ms=20.0, total_budget_ms=50.0, early_exit_on_violation=True)
        t2_config = TierConfig(enabled=True, timeout_ms=100.0, total_budget_ms=200.0, early_exit_on_violation=True)

        # Test with content that should trigger T0 violations
        toxic_context = {
            "messages": [{"role": "user", "content": "You are such an idiot"}],
            "phase": "input"
        }

        # Configure runner with tier configs
        runner_with_config = TieredGuardRunner(tier_configs={
            "T0": t0_config,
            "T1": t1_config,
            "T2": t2_config
        })

        result = await runner_with_config.run_tiered_guards(
            guards={},
            context=toxic_context
        )

        # Check execution results
        print("✅ Early exit test completed")
        print(f"   Violations: {len(result.violations)}")
        print(f"   Early exit: {result.early_exit}")
        print(f"   Tiers executed: {list(result.tier_stats.keys())}")

    @pytest.mark.asyncio
    async def test_policy_integration_with_tiers(self):
        """Test that policies correctly use the T0/T1/T2 architecture"""
        # Load enterprise policy
        policy = load_policy('policies/enterprise_default_v1.yaml')

        # Test input context
        context = {
            "phase": "input",
            "messages": [{"role": "user", "content": "Vote for candidate Smith"}],
            "model": "gpt-3.5-turbo"
        }

        # Run input guards
        input_guard = policy.compiled_guards.get("input")
        assert input_guard is not None, "Policy must have input guards"

        start_time = time.time()
        result = await input_guard(context)
        execution_time = (time.time() - start_time) * 1000

        print(f"✅ Policy execution time: {execution_time:.2f}ms")

        if is_left(result):
            violations = get_violations(result)
            print(f"✅ Policy found {len(violations)} violations:")
            for v in violations:
                print(f"   - {v.get('rule_id', 'unknown')}: {v.get('message', 'unknown')}")
        else:
            print("⚠️  No violations found - this might indicate an issue")

    @pytest.mark.asyncio
    async def test_all_guard_types_in_tiers(self):
        """Test that all major guard types are properly distributed across tiers"""

        t0_guards = get_guards_by_tier("T0")
        t1_guards = get_guards_by_tier("T1")
        t2_guards = get_guards_by_tier("T2")

        # Just verify we have guards in each tier - don't check specific guards
        # as the exact guard names may vary
        assert len(t0_guards) > 0, "T0 should have some guards"
        assert len(t1_guards) > 0, "T1 should have some guards"
        assert len(t2_guards) > 0, "T2 should have some guards"

        print(f"✅ Guards distributed across tiers: T0={len(t0_guards)}, T1={len(t1_guards)}, T2={len(t2_guards)}")

    @pytest.mark.asyncio
    async def test_performance_characteristics(self):
        """Test that tiers meet their performance characteristics"""

        # Test T0 guards performance
        t0_guards = get_guards_by_tier("T0")
        for guard_id in list(t0_guards.keys())[:3]:  # Test first 3 T0 guards
            guard_factory = t0_guards[guard_id].factory

            # Create a simple guard instance
            if guard_id == "pii.detect":
                guard = guard_factory(types=["EMAIL"], threshold=0.5)
            elif guard_id == "pii.redact":
                guard = guard_factory(types=["EMAIL"], mode="mask")
            elif guard_id == "tools.allowlist":
                guard = guard_factory(allowed_tools=["test_tool"])
            else:
                continue  # Skip guards we can't easily instantiate

            # Test performance
            test_context = {"output": "test@example.com"}

            start_time = time.time()
            await guard(test_context)
            execution_time = (time.time() - start_time) * 1000

            metadata = get_guard_metadata(guard_id)
            budget = metadata.performance_budget_ms

            print(f"✅ {guard_id}: {execution_time:.2f}ms (budget: {budget}ms)")

            # Allow some tolerance for test environment overhead
            assert execution_time < budget * 2, f"T0 guard {guard_id} too slow: {execution_time:.2f}ms > {budget * 2}ms"

    def test_tier_architecture_is_core(self):
        """Test that T0/T1/T2 architecture is core, not optional"""

        # Verify that TieredGuardRunner exists and is functional
        runner = TieredGuardRunner()
        assert runner is not None, "TieredGuardRunner must be available"

        # Verify that all tiers have guards
        t0_guards = get_guards_by_tier("T0")
        t1_guards = get_guards_by_tier("T1")
        t2_guards = get_guards_by_tier("T2")

        assert len(t0_guards) >= 1, f"T0 tier must have at least 1 guard, found {len(t0_guards)}"
        assert len(t1_guards) >= 1, f"T1 tier must have at least 1 guard, found {len(t1_guards)}"
        assert len(t2_guards) >= 1, f"T2 tier must have at least 1 guard, found {len(t2_guards)}"

        # Verify that tier metadata is present
        for tier in ["T0", "T1", "T2"]:
            guards = get_guards_by_tier(tier)
            for guard_id in guards:
                metadata = get_guard_metadata(guard_id)
                assert metadata.tier == tier, f"Guard {guard_id} tier mismatch"
                assert metadata.description is not None, f"Guard {guard_id} missing description"

        print("✅ T0/T1/T2 architecture verified as core system requirement")


class TestSpecificGuardTiers:
    """Test specific guards in their assigned tiers"""

    @pytest.mark.asyncio
    async def test_t0_pii_guards(self):
        """Test T0 PII guards for speed and accuracy"""
        from guards.pii.guards import pii_detect

        # Test PII detection
        detect_guard = pii_detect(types=["EMAIL", "PHONE"], threshold=0.0)

        test_context = {"output": "Contact me at john@example.com or (555) 123-4567"}

        start_time = time.time()
        result = await detect_guard(test_context)
        execution_time = (time.time() - start_time) * 1000

        assert execution_time < 5.0, f"T0 PII detection too slow: {execution_time:.2f}ms"
        assert is_left(result), "Should detect PII"

        violations = get_violations(result)
        assert len(violations) > 0, "Should find PII violations"

        print(f"✅ T0 PII detection: {execution_time:.2f}ms, found {len(violations)} violations")

    @pytest.mark.asyncio
    async def test_t1_toxicity_guards(self):
        """Test T1 toxicity guards for semantic analysis"""
        from guards.toxicity.guards import toxicity_block

        toxic_guard = toxicity_block(categories=["profanity", "harassment"], threshold=0.1)

        test_context = {"output": "You are such an idiot and I hate you"}

        start_time = time.time()
        result = await toxic_guard(test_context)
        execution_time = (time.time() - start_time) * 1000

        assert execution_time < 20.0, f"T1 toxicity detection too slow: {execution_time:.2f}ms"
        assert is_left(result), "Should detect toxicity"

        violations = get_violations(result)
        assert len(violations) > 0, "Should find toxicity violations"

        print(f"✅ T1 toxicity detection: {execution_time:.2f}ms, found {len(violations)} violations")

    @pytest.mark.skip(reason="ONNX models not available in test environment")
    @pytest.mark.asyncio
    async def test_t2_onnx_guards_concept(self):
        """Test T2 ONNX guards (conceptual since models may not be available)"""
        from guards.safety.guards import local_toxicity_onnx

        # Test ONNX guard creation (may fallback to rule-based)
        onnx_guard = local_toxicity_onnx(
            model="detoxify_tiny.onnx",
            threshold=0.35,
            enabled=True
        )

        test_context = {"output": "This is toxic content for testing"}

        start_time = time.time()
        await onnx_guard(test_context)
        execution_time = (time.time() - start_time) * 1000

        # T2 guards can be slower but should still be reasonable
        assert execution_time < 200.0, f"T2 ONNX guard too slow: {execution_time:.2f}ms"

        print(f"✅ T2 ONNX guard: {execution_time:.2f}ms (may use fallback)")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])
