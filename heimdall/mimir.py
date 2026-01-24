"""
Mímir Control Plane - Policy Signing and Hot-Reload

Provides signed policy envelopes with version control and hot-reload capabilities.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

try:
    import nacl.encoding
    import nacl.signing
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False
    nacl = None

from .compiler import compile_policy


@dataclass
class PolicyEnvelope:
    """Signed policy envelope with versioning and integrity"""
    policy_id: str
    version: str
    compiled_graph: dict[str, Any]
    thresholds: dict[str, dict[str, float]]
    models: list[dict[str, str]]
    signing: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def compute_policy_hash(policy_data: dict[str, Any]) -> str:
    """Compute SHA256 hash of policy data"""
    canonical = json.dumps(policy_data, sort_keys=True).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def generate_signing_keypair() -> tuple[bytes, bytes]:
    """Generate Ed25519 signing keypair"""
    if not NACL_AVAILABLE:
        raise RuntimeError("PyNaCl not installed. Install with: pip install PyNaCl")
    signing_key = nacl.signing.SigningKey.generate()
    verify_key = signing_key.verify_key
    return (
        signing_key.encode(encoder=nacl.encoding.Base64Encoder),
        verify_key.encode(encoder=nacl.encoding.Base64Encoder)
    )


def sign_policy_envelope(
    envelope_data: dict[str, Any],
    signing_key: bytes
) -> str:
    """Sign policy envelope with Ed25519"""
    if not NACL_AVAILABLE:
        raise RuntimeError("PyNaCl not installed. Install with: pip install PyNaCl")
    key = nacl.signing.SigningKey(signing_key, encoder=nacl.encoding.Base64Encoder)
    canonical = json.dumps(envelope_data, sort_keys=True).encode('utf-8')
    signed = key.sign(canonical)
    return signed.signature.hex()


def verify_policy_signature(
    envelope: PolicyEnvelope,
    verify_key: bytes
) -> bool:
    """Verify policy envelope signature"""
    if not NACL_AVAILABLE:
        raise RuntimeError("PyNaCl not installed. Install with: pip install PyNaCl")
    vk = nacl.signing.VerifyKey(verify_key, encoder=nacl.encoding.Base64Encoder)

    # Extract envelope data without signature
    envelope_dict = envelope.to_dict()
    signature_hex = envelope_dict['signing']['sig']

    # Remove signature for verification
    envelope_without_sig = envelope_dict.copy()
    envelope_without_sig['signing'] = {'alg': envelope_dict['signing']['alg']}

    canonical = json.dumps(envelope_without_sig, sort_keys=True).encode('utf-8')
    signature = bytes.fromhex(signature_hex)

    try:
        vk.verify(canonical, signature)
        return True
    except nacl.exceptions.BadSignatureError:
        return False


def compile_and_sign_policy(
    yaml_bytes: bytes,
    policy_id: str,
    signing_key: bytes,
    version: str | None = None,
    thresholds: dict[str, dict[str, float]] | None = None,
    models: list[dict[str, str]] | None = None
) -> PolicyEnvelope:
    """Compile YAML policy and create signed envelope"""

    # Compile policy to guard graph
    compiled_guards, policy_metadata = compile_policy(yaml_bytes)

    # Generate version if not provided
    if version is None:
        timestamp = datetime.utcnow().strftime("%Y.%m.%d-%H%M%S")
        version = f"{timestamp}-signed"

    # Extract thresholds from policy metadata if not provided
    if thresholds is None:
        thresholds = policy_metadata.get('thresholds', {
            "t0": {"gate_t1": 0.30, "gate_t2": 0.80},
            "t1": {"gate_t2": 0.50}
        })

    # Extract model info if not provided
    if models is None:
        models = []
        if 'onnx_models' in policy_metadata:
            for model_info in policy_metadata['onnx_models']:
                models.append({
                    'id': model_info.get('id', ''),
                    'sha256': model_info.get('sha256', ''),
                    'quant': model_info.get('quant', 'fp32')
                })

    # Serialize compiled graph (phases and guard IDs)
    compiled_graph = {
        phase: f"<compiled_guard_{phase}>"
        for phase in compiled_guards.keys()
    }

    # Create envelope without signature
    envelope_data = {
        'policy_id': policy_id,
        'version': version,
        'compiled_graph': compiled_graph,
        'thresholds': thresholds,
        'models': models,
        'signing': {'alg': 'Ed25519'}
    }

    # Sign envelope
    signature = sign_policy_envelope(envelope_data, signing_key)
    envelope_data['signing']['sig'] = signature

    # Create envelope object
    return PolicyEnvelope(**envelope_data)


def load_and_verify_policy(
    envelope_json: str,
    verify_key: bytes
) -> tuple[PolicyEnvelope, bool]:
    """Load policy envelope and verify signature"""
    envelope_dict = json.loads(envelope_json)
    envelope = PolicyEnvelope(**envelope_dict)

    is_valid = verify_policy_signature(envelope, verify_key)

    return envelope, is_valid

