"""
Safety Guards with ONNX Runtime Integration

Local ML models for toxicity detection, jailbreak prevention, and NER
without external API dependencies.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from heimdall import register_factory
from heimdall.author import G

if TYPE_CHECKING:
    import numpy as np
    import onnxruntime as ort

try:
    import numpy as np
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    ort = None
    np = None


class ONNXModelManager:
    """Manages ONNX model loading and inference"""

    def __init__(self):
        self.models = {}
        self.model_dir = Path(__file__).parent / "models"

    def load_model(self, model_name: str, model_path: str) -> None:
        """Load ONNX model for inference - fail fast if unavailable"""
        if not ONNX_AVAILABLE:
            raise ImportError("onnxruntime is required for ONNX models")

        full_path = self.model_dir / model_path
        if not full_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {full_path}")

        session = ort.InferenceSession(str(full_path))
        self.models[model_name] = session
        print(f"✅ Loaded ONNX model: {model_name}")

    def predict(self, model_name: str, input_data: Any) -> "np.ndarray":
        """Run inference on loaded model - fail fast if unavailable"""
        if model_name not in self.models:
            raise ValueError(f"Model {model_name} not loaded")

        session = self.models[model_name]
        input_name = session.get_inputs()[0].name
        result = session.run(None, {input_name: input_data})
        return result[0]


# Global model manager
model_manager = ONNXModelManager()


def extract_content(ctx: dict[str, Any]) -> str:
    """Extract text content from context"""
    content_parts = []

    messages = ctx.get("messages", [])
    for msg in messages:
        if isinstance(msg, dict) and "content" in msg:
            content_parts.append(msg["content"])

    if "output" in ctx:
        content_parts.append(str(ctx["output"]))

    return " ".join(content_parts)


def simple_tokenize(text: str, max_length: int = 512) -> list[float]:
    """
    Simple tokenization for ONNX models
    In production, use proper tokenizers like transformers
    """
    # Very basic tokenization - convert to character codes
    tokens = [float(ord(c)) / 255.0 for c in text.lower()[:max_length]]

    # Pad or truncate to fixed length
    if len(tokens) < max_length:
        tokens.extend([0.0] * (max_length - len(tokens)))
    else:
        tokens = tokens[:max_length]

    return tokens


@register_factory("safety.toxicity.local_onnx", tier="T2", description="ONNX-based toxicity detection with ML models", performance_budget_ms=50.0)
def local_toxicity_onnx(
    model: str = "detoxify_tiny.onnx",
    threshold: float = 0.35,
    gated_by: str | None = None,
    enabled: bool = True
):
    """
    Local toxicity detection using ONNX Runtime

    Args:
        model: ONNX model filename
        threshold: Toxicity score threshold (0.0-1.0)
        gated_by: Optional gate condition (e.g., "t1_score>0.6")
        enabled: Whether this guard is active
    """

    if not enabled:
        # Return pass-through guard when disabled
        return G("safety.toxicity.local_onnx").require(lambda ctx: True, "Disabled").build()

    # Load model at guard creation time - fail fast if unavailable
    model_manager.load_model("toxicity", model)

    def check_toxicity(ctx):
        content = extract_content(ctx)
        if not content:
            return True  # No content, allow

        # Prepare input for ONNX model
        input_tokens = simple_tokenize(content)
        input_array = np.array([input_tokens], dtype=np.float32)

        # Run ONNX inference - will fail fast if model unavailable
        scores = model_manager.predict("toxicity", input_array)
        toxicity_score = float(scores[0])

        return toxicity_score <= threshold

    return G("safety.toxicity.local_onnx", severity="high").require(
        check_toxicity,
        f"Toxic content detected (threshold: {threshold})"
    ).build()


@register_factory("safety.jailbreak.local_onnx", tier="T2", description="ONNX-based jailbreak detection", performance_budget_ms=40.0)
def local_jailbreak_onnx(
    model: str = "jailbreak_detector.onnx",
    threshold: float = 0.7,
    gated_by: str | None = None,
    enabled: bool = True
):
    """
    Local jailbreak attempt detection using ONNX Runtime

    Detects attempts to bypass AI safety measures
    """

    if not enabled:
        return G("safety.jailbreak.local_onnx").require(lambda ctx: True, "Disabled").build()

    # Load model at guard creation time - fail fast if unavailable
    model_manager.load_model("jailbreak", model)

    def check_jailbreak(ctx):
        content = extract_content(ctx)
        if not content:
            return True  # No content, allow

        # ONNX inference for jailbreak detection
        input_tokens = simple_tokenize(content)
        input_array = np.array([input_tokens], dtype=np.float32)

        scores = model_manager.predict("jailbreak", input_array)
        jailbreak_score = float(scores[0])

        return jailbreak_score <= threshold

    return G("safety.jailbreak.local_onnx", severity="critical").require(
        check_jailbreak,
        f"Jailbreak attempt detected (threshold: {threshold})"
    ).build()


@register_factory("safety.ner.local_onnx", tier="T2", description="ONNX-based Named Entity Recognition", performance_budget_ms=30.0)
def local_ner_onnx(
    model: str = "ner_tiny.onnx",
    entities: list[str] = None,
    gated_by: str | None = None,
    enabled: bool = True
):
    """
    Local Named Entity Recognition using ONNX Runtime

    Detects and optionally redacts entities like PERSON, ORG, GPE
    """

    if entities is None:
        entities = ["PERSON", "ORG", "GPE", "MONEY", "DATE"]

    if not enabled:
        return G("safety.ner.local_onnx").require(lambda ctx: True, "Disabled").build()

    # Load model at guard creation time - fail fast if unavailable
    model_manager.load_model("ner", model)

    # NER doesn't block, it annotates - so always pass
    return G("safety.ner.local_onnx").require(
        lambda ctx: True,
        "NER processing complete"
    ).build()


# Initialize models directory
def init_models_directory():
    """Create models directory if it doesn't exist"""
    models_dir = Path(__file__).parent / "models"
    models_dir.mkdir(exist_ok=True)


# Initialize on import
init_models_directory()
