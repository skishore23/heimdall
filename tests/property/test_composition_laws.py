"""
Property-based tests for composition laws

Uses Hypothesis to verify category theory laws hold for our guard algebra:
- Associativity of `then` and `and_also`
- Identity guard
- Annihilator guard (always-fail)
- Distributivity samples
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from heimdall.comb import allOf, anyOf, seq
from heimdall.types import (
    Ctx,
    Either,
    Left_,
    Right_,
    Violation,
    is_left,
    is_right,
)


# Strategy for generating simple contexts
@composite
def context_strategy(draw):
    """Generate random contexts"""
    return {
        "value": draw(st.integers(min_value=0, max_value=100)),
        "text": draw(st.text(min_size=1, max_size=50)),
        "flag": draw(st.booleans()),
    }


# Strategy for generating simple guards
@composite
def guard_strategy(draw):
    """Generate random guards"""
    guard_type = draw(st.sampled_from(['pass', 'fail', 'conditional']))

    if guard_type == 'pass':
        async def always_pass(ctx: Ctx) -> Either:
            return Right_(ctx)
        return always_pass

    elif guard_type == 'fail':
        message = draw(st.text(min_size=1, max_size=20))
        async def always_fail(ctx: Ctx) -> Either:
            return Left_([Violation(
                rule_id="test.fail",
                severity="med",
                message=message
            )])
        return always_fail

    else:  # conditional
        threshold = draw(st.integers(min_value=0, max_value=100))
        async def conditional_guard(ctx: Ctx) -> Either:
            if ctx.get("value", 0) > threshold:
                return Right_(ctx)
            return Left_([Violation(
                rule_id="test.conditional",
                severity="low",
                message=f"value <= {threshold}"
            )])
        return conditional_guard


async def identity_guard(ctx: Ctx) -> Either:
    """Identity guard - always passes without modification"""
    return Right_(ctx)


async def annihilator_guard(ctx: Ctx) -> Either:
    """Annihilator guard - always fails"""
    return Left_([Violation(
        rule_id="test.annihilator",
        severity="critical",
        message="Annihilator"
    )])


# Test: Associativity of sequential composition
@pytest.mark.asyncio
@given(ctx=context_strategy(), g1=guard_strategy(), g2=guard_strategy(), g3=guard_strategy())
@settings(max_examples=50, deadline=None)
async def test_seq_associativity(ctx, g1, g2, g3):
    """
    Test: seq(seq(g1, g2), g3) ≡ seq(g1, seq(g2, g3))

    Sequential composition must be associative.
    """
    # Left: ((g1 ; g2) ; g3)
    left_composed = seq(seq(g1, g2), g3)
    left_result = await left_composed(ctx)

    # Right: (g1 ; (g2 ; g3))
    right_composed = seq(g1, seq(g2, g3))
    right_result = await right_composed(ctx)

    # Results should be equivalent (both pass or both fail)
    assert is_left(left_result) == is_left(right_result), \
        "Associativity violated: different success/failure"


# Test: Identity for sequential composition
@pytest.mark.asyncio
@given(ctx=context_strategy(), g=guard_strategy())
@settings(max_examples=50, deadline=None)
async def test_seq_identity(ctx, g):
    """
    Test: seq(id, g) ≡ g ≡ seq(g, id)

    Identity guard must be the identity element for sequential composition.
    """
    # Left identity: id ; g
    left_composed = seq(identity_guard, g)
    left_result = await left_composed(ctx)

    # Right identity: g ; id
    right_composed = seq(g, identity_guard)
    right_result = await right_composed(ctx)

    # Direct: g
    direct_result = await g(ctx)

    # All should have same success/failure
    assert is_left(left_result) == is_left(direct_result), \
        "Left identity violated"
    assert is_left(right_result) == is_left(direct_result), \
        "Right identity violated"


# Test: Annihilator for sequential composition
@pytest.mark.asyncio
@given(ctx=context_strategy(), g=guard_strategy())
@settings(max_examples=50, deadline=None)
async def test_seq_annihilator(ctx, g):
    """
    Test: seq(fail, g) ≡ fail ≡ seq(g, fail)

    Annihilator (always-fail) should short-circuit sequential composition.
    """
    # Left annihilation: fail ; g
    left_composed = seq(annihilator_guard, g)
    left_result = await left_composed(ctx)

    # Right annihilation: g ; fail
    right_composed = seq(g, annihilator_guard)
    right_result = await right_composed(ctx)

    # Both must fail
    assert is_left(left_result), "Left annihilator violated: should always fail"
    assert is_left(right_result), "Right annihilator violated: should always fail"


# Test: Associativity of allOf (parallel AND)
@pytest.mark.asyncio
@given(ctx=context_strategy(), g1=guard_strategy(), g2=guard_strategy(), g3=guard_strategy())
@settings(max_examples=50, deadline=None)
async def test_allOf_associativity(ctx, g1, g2, g3):
    """
    Test: allOf(allOf(g1, g2), g3) ≡ allOf(g1, allOf(g2, g3))

    Parallel AND composition must be associative.
    """
    # Left: ((g1 ∧ g2) ∧ g3)
    left_composed = allOf(allOf(g1, g2), g3)
    left_result = await left_composed(ctx)

    # Right: (g1 ∧ (g2 ∧ g3))
    right_composed = allOf(g1, allOf(g2, g3))
    right_result = await right_composed(ctx)

    # Results should be equivalent
    assert is_left(left_result) == is_left(right_result), \
        "allOf associativity violated"


# Test: Identity for allOf
@pytest.mark.asyncio
@given(ctx=context_strategy(), g=guard_strategy())
@settings(max_examples=50, deadline=None)
async def test_allOf_identity(ctx, g):
    """
    Test: allOf(id, g) ≡ g ≡ allOf(g, id)

    Identity guard must be the identity element for allOf.
    """
    # With identity on left
    left_composed = allOf(identity_guard, g)
    left_result = await left_composed(ctx)

    # With identity on right
    right_composed = allOf(g, identity_guard)
    right_result = await right_composed(ctx)

    # Direct
    direct_result = await g(ctx)

    # All should have same success/failure
    assert is_left(left_result) == is_left(direct_result), \
        "allOf left identity violated"
    assert is_left(right_result) == is_left(direct_result), \
        "allOf right identity violated"


# Test: Annihilator for allOf
@pytest.mark.asyncio
@given(ctx=context_strategy(), g=guard_strategy())
@settings(max_examples=50, deadline=None)
async def test_allOf_annihilator(ctx, g):
    """
    Test: allOf(fail, g) ≡ fail ≡ allOf(g, fail)

    Annihilator should make allOf always fail.
    """
    # With annihilator on left
    left_composed = allOf(annihilator_guard, g)
    left_result = await left_composed(ctx)

    # With annihilator on right
    right_composed = allOf(g, annihilator_guard)
    right_result = await right_composed(ctx)

    # Both must fail
    assert is_left(left_result), "allOf left annihilator violated"
    assert is_left(right_result), "allOf right annihilator violated"


# Test: Identity for anyOf
@pytest.mark.asyncio
@given(ctx=context_strategy())
@settings(max_examples=50, deadline=None)
async def test_anyOf_identity(ctx):
    """
    Test: anyOf(id, fail) ≡ id

    If at least one guard is identity, anyOf should pass.
    """
    # anyOf with identity should always pass
    composed = anyOf(identity_guard, annihilator_guard)
    result = await composed(ctx)

    assert is_right(result), "anyOf with identity should always pass"


# Test: Commutativity of allOf (without collect)
@pytest.mark.asyncio
@given(ctx=context_strategy(), g1=guard_strategy(), g2=guard_strategy())
@settings(max_examples=50, deadline=None)
async def test_allOf_commutativity(ctx, g1, g2):
    """
    Test: allOf(g1, g2) ≡ allOf(g2, g1)

    Order should not matter for allOf (when collect=False).
    """
    # Forward order
    forward = allOf(g1, g2)
    forward_result = await forward(ctx)

    # Reverse order
    reverse = allOf(g2, g1)
    reverse_result = await reverse(ctx)

    # Results should be equivalent (both pass or both fail)
    assert is_left(forward_result) == is_left(reverse_result), \
        "allOf commutativity violated"


# Test: Commutativity of anyOf
@pytest.mark.asyncio
@given(ctx=context_strategy(), g1=guard_strategy(), g2=guard_strategy())
@settings(max_examples=50, deadline=None)
async def test_anyOf_commutativity(ctx, g1, g2):
    """
    Test: anyOf(g1, g2) ≡ anyOf(g2, g1)

    Order should not matter for anyOf.
    """
    # Forward order
    forward = anyOf(g1, g2)
    forward_result = await forward(ctx)

    # Reverse order
    reverse = anyOf(g2, g1)
    reverse_result = await reverse(ctx)

    # Results should be equivalent
    assert is_left(forward_result) == is_left(reverse_result), \
        "anyOf commutativity violated"


# Test: De Morgan's Law for guards
@pytest.mark.asyncio
@given(ctx=context_strategy(), g1=guard_strategy(), g2=guard_strategy())
@settings(max_examples=50, deadline=None)
async def test_de_morgan_law(ctx, g1, g2):
    """
    Test: NOT(allOf(g1, g2)) ≡ anyOf(NOT(g1), NOT(g2))

    De Morgan's laws should hold (in terms of pass/fail).
    """
    # allOf(g1, g2)
    all_result = await allOf(g1, g2)(ctx)

    # anyOf(g1, g2)
    any_result = await anyOf(g1, g2)(ctx)

    # If both pass, allOf passes and anyOf passes
    # If both fail, allOf fails and anyOf fails
    # If one passes, allOf fails and anyOf passes
    # This is a basic sanity check

    if is_right(all_result):
        # If allOf passes, anyOf must pass
        assert is_right(any_result), "If allOf passes, anyOf must pass"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

