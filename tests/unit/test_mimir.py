"""
Tests for Mímir control plane (policy signing and hot-reload)

Note: Requires PyNaCl. Install with: pip install PyNaCl
"""

import pytest

try:
    from heimdall.mimir import (
        NACL_AVAILABLE,
        PolicyEnvelope,
        compile_and_sign_policy,
        compute_policy_hash,
        generate_signing_keypair,
        load_and_verify_policy,
        sign_policy_envelope,
        verify_policy_signature,
    )
    MIMIR_TESTS_ENABLED = NACL_AVAILABLE
except ImportError:
    MIMIR_TESTS_ENABLED = False


pytestmark = pytest.mark.skipif(
    not MIMIR_TESTS_ENABLED,
    reason="PyNaCl not installed. Install with: pip install PyNaCl"
)


def test_generate_signing_keypair():
    """Test Ed25519 keypair generation"""
    signing_key, verify_key = generate_signing_keypair()

    assert isinstance(signing_key, bytes)
    assert isinstance(verify_key, bytes)
    assert len(signing_key) > 0
    assert len(verify_key) > 0


def test_compute_policy_hash():
    """Test SHA256 hash computation"""
    policy_data = {"test": "data", "version": "1.0"}

    hash1 = compute_policy_hash(policy_data)
    hash2 = compute_policy_hash(policy_data)

    assert hash1 == hash2  # Deterministic
    assert len(hash1) == 64  # SHA256 hex string


def test_policy_envelope_serialization():
    """Test PolicyEnvelope serialization"""
    envelope = PolicyEnvelope(
        policy_id="test_policy",
        version="1.0.0",
        compiled_graph={"root": "test"},
        thresholds={"t0": {"gate_t1": 0.3}},
        models=[],
        signing={"alg": "Ed25519", "sig": "test"}
    )

    envelope_dict = envelope.to_dict()

    assert envelope_dict["policy_id"] == "test_policy"
    assert envelope_dict["version"] == "1.0.0"
    assert "compiled_graph" in envelope_dict

    envelope_json = envelope.to_json()
    assert isinstance(envelope_json, str)
    assert "test_policy" in envelope_json


def test_sign_and_verify_policy():
    """Test policy signing and verification"""
    signing_key, verify_key = generate_signing_keypair()

    envelope_data = {
        "policy_id": "test_policy",
        "version": "1.0.0",
        "compiled_graph": {"root": "test"},
        "thresholds": {},
        "models": [],
        "signing": {"alg": "Ed25519"}
    }

    # Sign envelope
    signature = sign_policy_envelope(envelope_data, signing_key)
    assert isinstance(signature, str)
    assert len(signature) > 0

    # Create full envelope
    envelope_data["signing"]["sig"] = signature
    envelope = PolicyEnvelope(**envelope_data)

    # Verify signature
    is_valid = verify_policy_signature(envelope, verify_key)
    assert is_valid is True


def test_load_and_verify_policy():
    """Test loading and verifying policy from JSON"""
    signing_key, verify_key = generate_signing_keypair()

    # Create signed envelope
    envelope_data = {
        "policy_id": "test_policy",
        "version": "1.0.0",
        "compiled_graph": {"root": "test"},
        "thresholds": {},
        "models": [],
        "signing": {"alg": "Ed25519"}
    }

    signature = sign_policy_envelope(envelope_data, signing_key)
    envelope_data["signing"]["sig"] = signature

    envelope = PolicyEnvelope(**envelope_data)
    envelope_json = envelope.to_json()

    # Load and verify
    loaded_envelope, is_valid = load_and_verify_policy(envelope_json, verify_key)

    assert is_valid is True
    assert loaded_envelope.policy_id == "test_policy"
    assert loaded_envelope.version == "1.0.0"

