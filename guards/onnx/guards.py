"""
Universal ONNX Guard

A flexible guard that can use any ONNX model from the registry.
Users can configure which models to use in their policies.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import onnxruntime as ort

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    ort = None

from heimdall import register_factory
from heimdall.onnx_registry import ONNXModelInfo, get_onnx_registry
from heimdall.types import Ctx, Either, Guard, Left_, Right_, Violation


@dataclass
class ONNXGuardConfig:
    """Configuration for ONNX-based guards"""
    model_id: str
    threshold: float = 0.7
    target_labels: list[str] | None = None  # Which labels to consider violations
    severity: str = "medium"
    performance_budget_ms: float | None = None
    ensemble_models: list[str] | None = None  # Multiple models for ensemble
    preprocessing: dict[str, Any] | None = None


class UniversalONNXClassifier:
    """
    Universal ONNX classifier that can work with any model from the registry
    """

    def __init__(self, config: ONNXGuardConfig):
        self.config = config
        self.registry = get_onnx_registry()
        self.model_info = self.registry.get_model(config.model_id)
        self.session = None
        self.ensemble_sessions = {}

        if not self.model_info:
            raise ValueError(f"Model not found in registry: {config.model_id}")

        # Load primary model - fail fast if unavailable
        self.session = self.registry.load_model_session(config.model_id)
        if not self.session:
            raise RuntimeError(f"Failed to load ONNX model: {config.model_id}")

        # Load ensemble models if specified - fail fast if any unavailable
        if config.ensemble_models:
            for model_id in config.ensemble_models:
                session = self.registry.load_model_session(model_id)
                if not session:
                    raise RuntimeError(f"Failed to load ensemble ONNX model: {model_id}")
                self.ensemble_sessions[model_id] = session

    def _tokenize_text(self, text: str, model_info: ONNXModelInfo) -> dict[str, np.ndarray]:
        """
        Tokenize text based on model type

        In production, this would use proper tokenizers from transformers library
        """
        tokenizer_config = model_info.tokenizer_config
        model_type = tokenizer_config.get("model_type", "bert")
        max_length = tokenizer_config.get("max_length", 512)
        vocab_size = tokenizer_config.get("vocab_size", 30522)

        # Simple tokenization for demo (replace with proper tokenizers)
        words = text.lower().split()[:max_length]

        # Create input tensors based on model type
        if model_type in ["bert", "distilbert"]:
            # BERT-style tokenization
            input_ids = [tokenizer_config.get("cls_token_id", 101)]  # [CLS]
            input_ids.extend([hash(word) % vocab_size for word in words])
            input_ids.append(tokenizer_config.get("sep_token_id", 102))  # [SEP]

        elif model_type == "roberta":
            # RoBERTa-style tokenization
            input_ids = [tokenizer_config.get("cls_token_id", 0)]  # <s>
            input_ids.extend([hash(word) % vocab_size for word in words])
            input_ids.append(tokenizer_config.get("sep_token_id", 2))  # </s>

        else:
            # Generic tokenization
            input_ids = [hash(word) % vocab_size for word in words]

        # Truncate or pad to max_length
        if len(input_ids) > max_length:
            input_ids = input_ids[:max_length]
        else:
            pad_token_id = tokenizer_config.get("pad_token_id", 0)
            input_ids.extend([pad_token_id] * (max_length - len(input_ids)))

        # Create attention mask
        attention_mask = [1 if token_id != tokenizer_config.get("pad_token_id", 0) else 0
                         for token_id in input_ids]

        return {
            "input_ids": np.array(input_ids).reshape(1, -1).astype(np.int64),
            "attention_mask": np.array(attention_mask).reshape(1, -1).astype(np.int64)
        }

    async def classify_text(self, text: str) -> tuple[list[float], list[str], dict[str, Any]]:
        """
        Classify text using ONNX model(s) - fail fast if models unavailable

        Returns:
            Tuple of (scores, labels, metadata)
        """
        # Both model_info and session should be available due to fail-fast initialization
        assert self.model_info is not None, "Model info not available"
        assert self.session is not None, "ONNX session not available"

        # Primary model inference
        scores, labels = await self._run_single_model(text, self.session, self.model_info)
        metadata = {"primary_model": self.config.model_id}

        # Ensemble inference if configured
        if self.ensemble_sessions:
            ensemble_scores = []
            ensemble_models = []

            for model_id, session in self.ensemble_sessions.items():
                model_info = self.registry.get_model(model_id)
                if model_info:
                    e_scores, e_labels = await self._run_single_model(text, session, model_info)
                    ensemble_scores.append(e_scores)
                    ensemble_models.append(model_id)

            # Average ensemble scores
            if ensemble_scores:
                avg_scores = np.mean([scores] + ensemble_scores, axis=0)
                scores = avg_scores.tolist()
                metadata["ensemble_models"] = ensemble_models
                metadata["ensemble_used"] = True

        return scores, labels, metadata

    async def _run_single_model(self, text: str, session: "ort.InferenceSession",
                               model_info: ONNXModelInfo) -> tuple[list[float], list[str]]:
        """Run inference on a single ONNX model"""
        # Tokenize input
        inputs = self._tokenize_text(text, model_info)

        # Run inference
        outputs = session.run(None, inputs)
        logits = outputs[0][0]  # Assuming first output is logits

        # Apply softmax to get probabilities
        exp_logits = np.exp(logits - np.max(logits))
        probabilities = exp_logits / np.sum(exp_logits)

        return probabilities.tolist(), model_info.labels



@register_factory("onnx.configurable", tier="T2", description="Configurable ONNX guard that can use any model from the registry", performance_budget_ms=100.0, requires_onnx=True)
def configurable_onnx_guard(
    model_id: str,
    threshold: float = 0.7,
    target_labels: list[str] | None = None,
    severity: str = "medium",
    performance_budget_ms: float | None = None,
    ensemble_models: list[str] | None = None,
    preprocessing: dict[str, Any] | None = None
) -> Guard:
    """
    Configurable ONNX guard that can use any model from the registry

    Args:
        model_id: ID of the model to use from the registry
        threshold: Classification threshold for violations
        target_labels: Which labels to consider violations (if None, uses model defaults)
        severity: Violation severity level
        performance_budget_ms: Override model's default performance budget
        ensemble_models: List of additional model IDs for ensemble classification
        preprocessing: Custom preprocessing configuration

    Examples:
        # Use financial advice detection model
        - id: onnx.universal
          with:
            model_id: "financial_advice_distilbert"
            threshold: 0.8
            target_labels: ["financial_advice"]

        # Use toxicity detection with ensemble
        - id: onnx.universal
          with:
            model_id: "toxicity_detoxify"
            threshold: 0.6
            ensemble_models: ["multilingual_toxicity_bert"]
            target_labels: ["toxic", "severe_toxic"]

        # Use custom model
        - id: onnx.universal
          with:
            model_id: "my_custom_classifier"
            threshold: 0.75
    """

    config = ONNXGuardConfig(
        model_id=model_id,
        threshold=threshold,
        target_labels=target_labels,
        severity=severity,
        performance_budget_ms=performance_budget_ms,
        ensemble_models=ensemble_models,
        preprocessing=preprocessing
    )

    classifier = UniversalONNXClassifier(config)

    async def run(ctx: Ctx) -> Either:
        # Get text from context
        text = ctx.get("output", "")
        if not text and "messages" in ctx:
            messages = ctx.get("messages", [])
            if isinstance(messages, list) and messages:
                text = messages[-1].get("content", "") if isinstance(messages[-1], dict) else str(messages[-1])

        if not isinstance(text, str) or not text.strip():
            return Right_(ctx)

        # Classify using ONNX model
        scores, labels, metadata = await classifier.classify_text(text)

        # Determine which labels indicate violations
        violation_labels = target_labels or []
        if not violation_labels and classifier.model_info:
            # Use model category to determine violation labels
            category = classifier.model_info.category
            if category == "financial":
                violation_labels = ["financial_advice", "non_compliant"]
            elif category == "legal":
                violation_labels = ["legal_advice", "professional_liability"]
            elif category == "toxicity":
                violation_labels = ["toxic", "severe_toxic", "threat", "insult"]
            elif category == "pii":
                violation_labels = ["pii_detected", "B-PERSON", "B-EMAIL", "B-PHONE"]
            else:
                # For unknown categories, assume second label is violation
                violation_labels = labels[1:] if len(labels) > 1 else []

        # Check for violations
        max_violation_score = 0.0
        violated_labels = []

        for i, label in enumerate(labels):
            if any(vl.lower() in label.lower() for vl in violation_labels):
                if scores[i] >= threshold:
                    max_violation_score = max(max_violation_score, scores[i])
                    violated_labels.append(label)

        if max_violation_score > 0:
            model_name = classifier.model_info.name if classifier.model_info else model_id

            return Left_([Violation(
                rule_id="onnx.universal",
                severity=severity,
                message=f"{model_name} detected violation: {', '.join(violated_labels)} (confidence: {max_violation_score:.2f})",
                score=max_violation_score,
                tier="T2",
                evidence={
                    "model_id": model_id,
                    "model_name": model_name,
                    "all_scores": dict(zip(labels, scores, strict=False)),
                    "violated_labels": violated_labels,
                    "threshold": threshold,
                    "text_analyzed": text[:200] + "..." if len(text) > 200 else text,
                    "metadata": metadata
                }
            )])

        return Right_(ctx)

    return run


# Convenience guards for common model types
@register_factory("onnx.financial", tier="T2", description="ONNX financial advice detection", performance_budget_ms=80.0, onnx_category="financial", requires_onnx=True)
def onnx_financial_guard(
    model_id: str = "financial_advice_distilbert",
    threshold: float = 0.7,
    **kwargs
) -> Guard:
    """Convenience guard for financial advice detection"""
    return configurable_onnx_guard(
        model_id=model_id,
        threshold=threshold,
        target_labels=["financial_advice", "non_compliant"],
        severity="critical",
        **kwargs
    )


@register_factory("onnx.legal", tier="T2", description="ONNX legal advice detection", performance_budget_ms=90.0, onnx_category="legal", requires_onnx=True)
def onnx_legal_guard(
    model_id: str = "legal_advice_bert",
    threshold: float = 0.8,
    **kwargs
) -> Guard:
    """Convenience guard for legal advice detection"""
    return configurable_onnx_guard(
        model_id=model_id,
        threshold=threshold,
        target_labels=["legal_advice", "professional_liability"],
        severity="high",
        **kwargs
    )


@register_factory("onnx.toxicity", tier="T2", description="ONNX toxicity detection", performance_budget_ms=70.0, onnx_category="toxicity", requires_onnx=True)
def onnx_toxicity_guard(
    model_id: str = "toxicity_detoxify",
    threshold: float = 0.5,
    **kwargs
) -> Guard:
    """Convenience guard for toxicity detection"""
    return configurable_onnx_guard(
        model_id=model_id,
        threshold=threshold,
        target_labels=["toxic", "severe_toxic", "threat", "insult"],
        severity="critical",
        **kwargs
    )


@register_factory("onnx.pii", tier="T2", description="ONNX PII detection", performance_budget_ms=60.0, onnx_category="pii", requires_onnx=True)
def onnx_pii_guard(
    model_id: str = "pii_detection_bert",
    threshold: float = 0.9,
    **kwargs
) -> Guard:
    """Convenience guard for PII detection"""
    return configurable_onnx_guard(
        model_id=model_id,
        threshold=threshold,
        target_labels=["B-PERSON", "B-EMAIL", "B-PHONE", "B-SSN"],
        severity="high",
        **kwargs
    )


@register_factory("onnx.sentiment", tier="T2", description="ONNX sentiment analysis", performance_budget_ms=50.0, onnx_category="sentiment", requires_onnx=True)
def onnx_sentiment_guard(
    model_id: str = "sentiment_roberta",
    threshold: float = 0.8,
    target_sentiment: str = "negative",
    **kwargs
) -> Guard:
    """Convenience guard for sentiment analysis"""
    return configurable_onnx_guard(
        model_id=model_id,
        threshold=threshold,
        target_labels=[target_sentiment],
        severity="medium",
        **kwargs
    )
