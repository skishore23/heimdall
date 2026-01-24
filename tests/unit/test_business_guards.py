"""
Unit tests for business guard pack
"""


import pytest

from guards.business.guards import (
    brand_tone_enforcement,
    competitor_protection,
    financial_services_compliance,
    professional_liability_protection,
)
from heimdall import get_violations, is_left


class TestFinancialComplianceGuard:
    """Test financial services compliance guard"""

    @pytest.mark.asyncio
    async def test_blocks_direct_financial_advice_requests(self):
        """Test that direct financial advice requests are blocked in input phase"""
        guard = financial_services_compliance()

        # Test input context with financial advice request
        input_ctx = {
            "phase": "input",
            "output": "What stocks should I buy?"  # This is what lens extracts
        }

        result = await guard(input_ctx)

        assert is_left(result), "Should block financial advice requests"
        violations = get_violations(result)
        assert len(violations) == 1
        assert violations[0]["rule_id"] == "business.financial_compliance"
        assert "Direct financial advice request blocked" in violations[0]["message"]

    @pytest.mark.asyncio
    async def test_blocks_various_financial_requests(self):
        """Test various financial advice request patterns"""
        guard = financial_services_compliance()

        test_cases = [
            "What stocks should I buy?",
            "Which investments should I purchase?",
            "Recommend some good stocks for me",
            "What are the best stocks to buy?",
            "Should I invest in Apple stock?",
            "Tell me which stocks to buy for guaranteed profits"
        ]

        for test_input in test_cases:
            input_ctx = {
                "phase": "input",
                "output": test_input
            }

            result = await guard(input_ctx)
            assert is_left(result), f"Should block: '{test_input}'"
            violations = get_violations(result)
            assert len(violations) == 1
            assert violations[0]["rule_id"] == "business.financial_compliance"

    @pytest.mark.asyncio
    async def test_allows_general_financial_questions(self):
        """Test that general financial education questions are allowed"""
        guard = financial_services_compliance()

        safe_inputs = [
            "What is a stock?",
            "How does the stock market work?",
            "What is diversification?",
            "Can you explain what a mutual fund is?",
            "What are the risks of investing?"
        ]

        for test_input in safe_inputs:
            input_ctx = {
                "phase": "input",
                "output": test_input
            }

            result = await guard(input_ctx)
            assert not is_left(result), f"Should allow: '{test_input}'"

    @pytest.mark.asyncio
    async def test_requires_disclaimers_in_output(self):
        """Test that financial advice in output requires disclaimers"""
        guard = financial_services_compliance()

        # Output without disclaimer should be blocked
        output_ctx = {
            "phase": "output",
            "output": "You should buy Apple stock. It will give you great returns."
        }

        result = await guard(output_ctx)
        assert is_left(result), "Should block output without disclaimers"
        violations = get_violations(result)
        assert "without required disclaimers" in violations[0]["message"]

        # Output with disclaimer should be allowed
        output_with_disclaimer_ctx = {
            "phase": "output",
            "output": "I am not a financial advisor. You should consult with a professional before making investment decisions. Some people invest in Apple stock, but past performance doesn't guarantee future results."
        }

        result = await guard(output_with_disclaimer_ctx)
        assert not is_left(result), "Should allow output with disclaimers"


class TestCompetitorProtectionGuard:
    """Test competitor protection guard"""

    @pytest.mark.asyncio
    async def test_blocks_competitor_mentions(self):
        """Test that competitor mentions are blocked"""
        guard = competitor_protection(competitors=["Vanguard", "Fidelity"])

        test_cases = [
            "You should try Vanguard instead",
            "Fidelity has better rates",
            "Consider using Vanguard for your investments"
        ]

        for test_input in test_cases:
            ctx = {"output": test_input}
            result = await guard(ctx)

            assert is_left(result), f"Should block: '{test_input}'"
            violations = get_violations(result)
            assert violations[0]["rule_id"] == "business.competitor_protection"

    @pytest.mark.asyncio
    async def test_allows_non_competitor_content(self):
        """Test that non-competitor content is allowed"""
        guard = competitor_protection(competitors=["Vanguard", "Fidelity"])

        safe_inputs = [
            "We offer great investment options",
            "Our platform has competitive rates",
            "You can diversify your portfolio with us"
        ]

        for test_input in safe_inputs:
            ctx = {"output": test_input}
            result = await guard(ctx)
            assert not is_left(result), f"Should allow: '{test_input}'"


class TestProfessionalLiabilityGuard:
    """Test professional liability protection guard"""

    @pytest.mark.asyncio
    async def test_blocks_legal_advice(self):
        """Test that legal advice is blocked"""
        guard = professional_liability_protection(blocked_advice_types=["legal"])

        test_cases = [
            "You should sue them for damages",
            "This is clearly illegal behavior",
            "You have a strong legal case here"
        ]

        for test_input in test_cases:
            ctx = {"output": test_input}
            result = await guard(ctx)

            assert is_left(result), f"Should block: '{test_input}'"
            violations = get_violations(result)
            assert violations[0]["rule_id"] == "business.professional_liability"

    @pytest.mark.asyncio
    async def test_allows_general_information(self):
        """Test that general information is allowed"""
        guard = professional_liability_protection(blocked_advice_types=["legal"])

        safe_inputs = [
            "Laws vary by jurisdiction",
            "You may want to consult with a lawyer",
            "Legal matters can be complex"
        ]

        for test_input in safe_inputs:
            ctx = {"output": test_input}
            result = await guard(ctx)
            assert not is_left(result), f"Should allow: '{test_input}'"


class TestBrandToneGuard:
    """Test brand tone enforcement guard"""

    @pytest.mark.asyncio
    async def test_blocks_unprofessional_language(self):
        """Test that unprofessional language is blocked"""
        guard = brand_tone_enforcement()

        test_cases = [
            "Dude, that's awesome!",
            "This is so lit and fire!",
            "OMG, that's amazing!!!"
        ]

        for test_input in test_cases:
            ctx = {"output": test_input}
            result = await guard(ctx)

            assert is_left(result), f"Should block: '{test_input}'"
            violations = get_violations(result)
            assert violations[0]["rule_id"] == "business.brand_tone"

    @pytest.mark.asyncio
    async def test_allows_professional_language(self):
        """Test that professional language is allowed"""
        guard = brand_tone_enforcement()

        professional_inputs = [
            "That's an excellent point.",
            "We appreciate your feedback.",
            "Thank you for your inquiry."
        ]

        for test_input in professional_inputs:
            ctx = {"output": test_input}
            result = await guard(ctx)
            assert not is_left(result), f"Should allow: '{test_input}'"
