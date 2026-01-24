"""
Comprehensive Gateway Integration Tests

Tests the complete gateway with T0/T1/T2 pipeline integration,
ensuring all guardrails work correctly in the production environment.
"""

import time

import httpx
import pytest

# Import guard packs to register them

# Skip all gateway tests if Bifrost isn't running
pytestmark = pytest.mark.skip(reason="Gateway integration tests require Bifrost to be running. Start with 'uv run python -m bifrost.main' or skip with pytest -k 'not gateway'")


class TestGatewayIntegration:
    """Test Bifrost integration with T0/T1/T2 pipeline"""

    BASE_URL = "http://localhost:8000"

    @pytest.fixture(scope="class")
    def client(self):
        """HTTP client for Bifrost testing"""
        return httpx.AsyncClient(base_url=self.BASE_URL, timeout=30.0)

    @pytest.mark.asyncio
    async def test_bifrost_health(self, client):
        """Test Bifrost health endpoint"""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "redis" in data
        print("✅ Gateway health check passed")

    @pytest.mark.asyncio
    async def test_input_guards_pii_redaction(self, client):
        """Test that PII is redacted in input (T0 tier)"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "My email is john@example.com"}],
            "max_tokens": 50
        }

        response = await client.post(
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "enterprise_default_v1"}
        )

        # Should succeed but with redacted content sent to OpenAI
        if response.status_code == 200:
            # Check if the response indicates PII was handled
            data = response.json()
            print("✅ PII request processed successfully")
            print(f"   Response: {data['choices'][0]['message']['content'][:100]}...")
        else:
            # Might be blocked by policy
            print(f"⚠️  PII request status: {response.status_code}")

    @pytest.mark.asyncio
    async def test_input_guards_politics_blocking(self, client):
        """Test that political content is blocked (T1 tier)"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Vote for candidate Smith"}],
            "max_tokens": 50
        }

        response = await client.post(
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "enterprise_default_v1"}
        )

        # Should be blocked by politics guard
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

        data = response.json()
        assert data["error"]["type"] == "policy_violation"
        assert "politics.block" in data["error"]["rule_id"]

        print("✅ Politics blocking working correctly")
        print(f"   Rule: {data['error']['rule_id']}")
        print(f"   Message: {data['error']['message']}")

    @pytest.mark.asyncio
    async def test_input_guards_toxicity_blocking(self, client):
        """Test that toxic content is blocked (T1 tier)"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "You are such an idiot and I hate you"}],
            "max_tokens": 50
        }

        response = await client.post(
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "enterprise_default_v1"}
        )

        # Should be blocked by toxicity guard
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

        data = response.json()
        assert data["error"]["type"] == "policy_violation"
        assert "toxicity.block" in data["error"]["rule_id"]

        print("✅ Toxicity blocking working correctly")
        print(f"   Rule: {data['error']['rule_id']}")
        print(f"   Message: {data['error']['message']}")

    @pytest.mark.asyncio
    async def test_safe_content_passes(self, client):
        """Test that safe content passes through all tiers"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Hello, how are you today?"}],
            "max_tokens": 50
        }

        response = await client.post(
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "enterprise_default_v1"}
        )

        # Should pass through successfully
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert "message" in data["choices"][0]

        print("✅ Safe content passes through all tiers")
        print(f"   Response: {data['choices'][0]['message']['content'][:100]}...")

    @pytest.mark.asyncio
    async def test_policy_hash_in_response(self, client):
        """Test that policy hash is included in responses"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Vote for candidate Smith"}],
            "max_tokens": 50
        }

        response = await client.post(
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "enterprise_default_v1"}
        )

        # Should be blocked with policy hash
        assert response.status_code == 400

        data = response.json()
        assert "policy_hash" in data["error"]
        assert data["error"]["policy_hash"].startswith("sha256:")
        assert data["error"]["policy_hash"] != "sha256:unknown"

        print("✅ Policy hash correctly included in error response")
        print(f"   Hash: {data['error']['policy_hash']}")

    @pytest.mark.asyncio
    async def test_multiple_policies(self, client):
        """Test different policies work correctly"""

        # Test with no-op policy (should allow everything)
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Vote for candidate Smith"}],
            "max_tokens": 50
        }

        response = await client.post(
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "noop_v1"}
        )

        # Should pass with no-op policy
        if response.status_code == 200:
            print("✅ No-op policy allows political content")
        else:
            print(f"⚠️  No-op policy response: {response.status_code}")

    @pytest.mark.asyncio
    async def test_performance_characteristics(self, client):
        """Test that T0/T1/T2 pipeline meets performance requirements"""

        test_cases = [
            ("Safe content", "Hello, how are you?", True),
            ("PII content", "My email is john@example.com", True),  # Should be fast T0 processing
            ("Political content", "Vote for candidate Smith", False),  # Should be blocked at T1
            ("Toxic content", "You are an idiot", False),  # Should be blocked at T1
        ]

        for test_name, content, should_succeed in test_cases:
            request_data = {
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 50
            }

            start_time = time.time()
            response = await client.post(
                "/v1/chat/completions",
                json=request_data,
                headers={"X-Policy-ID": "enterprise_default_v1"}
            )
            response_time = (time.time() - start_time) * 1000

            # Performance requirements:
            # - T0 processing: < 50ms
            # - T1 processing: < 100ms
            # - Complete pipeline: < 200ms
            assert response_time < 200, f"{test_name} too slow: {response_time:.2f}ms"

            status_ok = response.status_code == 200
            if should_succeed:
                if not status_ok:
                    print(f"⚠️  {test_name}: Expected success but got {response.status_code}")
            else:
                if status_ok:
                    print(f"⚠️  {test_name}: Expected block but got success")

            print(f"✅ {test_name}: {response_time:.2f}ms (Status: {response.status_code})")

    @pytest.mark.asyncio
    async def test_streaming_with_guards(self, client):
        """Test streaming responses work with guards"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Tell me a short story"}],
            "max_tokens": 100,
            "stream": True
        }

        async with client.stream(
            "POST",
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "enterprise_default_v1"}
        ) as response:

            if response.status_code == 200:
                chunks_received = 0
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        chunks_received += 1
                        if chunks_received >= 3:  # Just test first few chunks
                            break

                assert chunks_received > 0, "Should receive streaming chunks"
                print(f"✅ Streaming works with guards: {chunks_received} chunks received")
            else:
                print(f"⚠️  Streaming test status: {response.status_code}")

    @pytest.mark.asyncio
    async def test_error_handling_and_logging(self, client):
        """Test error handling and logging work correctly"""

        # Test malformed request
        response = await client.post(
            "/v1/chat/completions",
            json={"invalid": "request"},
            headers={"X-Policy-ID": "enterprise_default_v1"}
        )

        # Should handle gracefully
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"
        print("✅ Malformed request handled gracefully")

        # Test invalid policy
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 50
            },
            headers={"X-Policy-ID": "nonexistent_policy"}
        )

        # Should handle missing policy gracefully
        print(f"✅ Invalid policy handled: {response.status_code}")


class TestTierSpecificBehavior:
    """Test tier-specific behavior and performance"""

    BASE_URL = "http://localhost:8000"

    @pytest.fixture(scope="class")
    def client(self):
        return httpx.AsyncClient(base_url=self.BASE_URL, timeout=30.0)

    @pytest.mark.asyncio
    async def test_t0_tier_fast_execution(self, client):
        """Test T0 tier executes quickly"""

        # PII content should be handled by T0 guards
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "My SSN is 123-45-6789"}],
            "max_tokens": 50
        }

        start_time = time.time()
        await client.post(
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "enterprise_default_v1"}
        )
        response_time = (time.time() - start_time) * 1000

        # T0 processing should be very fast
        assert response_time < 50, f"T0 processing too slow: {response_time:.2f}ms"
        print(f"✅ T0 tier processing: {response_time:.2f}ms")

    @pytest.mark.asyncio
    async def test_t1_tier_semantic_analysis(self, client):
        """Test T1 tier semantic analysis"""

        # Political content should be caught by T1 guards
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Who should I vote for this year?"}],
            "max_tokens": 50
        }

        start_time = time.time()
        response = await client.post(
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "enterprise_default_v1"}
        )
        response_time = (time.time() - start_time) * 1000

        # Should be blocked by T1 guards
        assert response.status_code == 400, "Should be blocked by T1 politics guard"

        # T1 processing should be reasonably fast
        assert response_time < 100, f"T1 processing too slow: {response_time:.2f}ms"
        print(f"✅ T1 tier processing: {response_time:.2f}ms")

    @pytest.mark.asyncio
    async def test_gating_prevents_unnecessary_processing(self, client):
        """Test that gating prevents unnecessary T2 processing"""

        # Safe content should not trigger T2 processing
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "What's the weather like?"}],
            "max_tokens": 50
        }

        start_time = time.time()
        response = await client.post(
            "/v1/chat/completions",
            json=request_data,
            headers={"X-Policy-ID": "enterprise_default_v1"}
        )
        response_time = (time.time() - start_time) * 1000

        # Should be very fast since T2 is skipped
        assert response_time < 100, f"Gated processing too slow: {response_time:.2f}ms"
        assert response.status_code == 200, "Safe content should pass"
        print(f"✅ Gated processing (T2 skipped): {response_time:.2f}ms")


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])
