"""
ONNX Models for Business Content Classification

This module provides ONNX-based models that can catch what regex patterns miss,
offering more sophisticated semantic understanding for financial advice detection,
legal advice detection, and other business compliance scenarios.
"""

import os
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    ort = None

from heimdall import Ctx, Either, Guard, Left_, Right_, Violation, register_factory


@dataclass
class ModelConfig:
    """Configuration for ONNX models"""
    model_path: str
    tokenizer_config: dict[str, Any]
    labels: list[str]
    threshold: float = 0.5
    max_length: int = 512


class ONNXTextClassifier:
    """
    ONNX-based text classifier for business content moderation

    Supports various pre-trained models that can be converted to ONNX:
    - DistilBERT for financial advice detection
    - RoBERTa for legal advice detection
    - BERT for general content classification
    - Custom fine-tuned models
    """

    def __init__(self, model_config: ModelConfig):
        self.config = model_config
        self.session = None
        self.tokenizer = None
        self._load_model()

    def _load_model(self):
        """Load ONNX model and tokenizer - fail fast if unavailable"""
        if not ONNX_AVAILABLE:
            raise ImportError("onnxruntime is required for ONNX models")

        if not os.path.exists(self.config.model_path):
            raise FileNotFoundError(f"ONNX model not found: {self.config.model_path}")

        # Load ONNX model
        self.session = ort.InferenceSession(self.config.model_path)
        print(f"✅ Loaded ONNX model: {self.config.model_path}")

        # Initialize simple tokenizer (in production, use proper tokenizer)
        self.tokenizer = self._create_simple_tokenizer()

    def _create_simple_tokenizer(self):
        """Create a simple tokenizer for demo purposes"""
        # In production, use proper tokenizers like transformers.AutoTokenizer
        vocab = self.config.tokenizer_config.get("vocab", {})
        return {
            "vocab": vocab,
            "max_length": self.config.max_length,
            "pad_token_id": 0,
            "unk_token_id": 1
        }

    def _tokenize_text(self, text: str) -> dict[str, np.ndarray]:
        """
        Tokenize text for ONNX model input

        In production, this would use proper tokenizers like:
        - transformers.AutoTokenizer.from_pretrained("distilbert-base-uncased")
        - transformers.AutoTokenizer.from_pretrained("roberta-base")
        """
        if not self.tokenizer:
            # Fallback: simple word-based tokenization for demo
            words = text.lower().split()[:self.config.max_length]

            # Create dummy input tensors (in production, use proper tokenization)
            input_ids = np.array([hash(word) % 30000 for word in words][:512])
            attention_mask = np.ones(len(input_ids), dtype=np.int64)

            # Pad to max_length
            if len(input_ids) < 512:
                padding = 512 - len(input_ids)
                input_ids = np.pad(input_ids, (0, padding), constant_values=0)
                attention_mask = np.pad(attention_mask, (0, padding), constant_values=0)

            return {
                "input_ids": input_ids.reshape(1, -1).astype(np.int64),
                "attention_mask": attention_mask.reshape(1, -1).astype(np.int64)
            }

        # Use proper tokenizer if available
        # This is where you'd integrate with transformers tokenizers
        return self._simple_tokenize(text)

    def _simple_tokenize(self, text: str) -> dict[str, np.ndarray]:
        """Simple tokenization for demo purposes"""
        words = text.lower().split()[:512]
        input_ids = np.array([hash(word) % 30000 for word in words])
        attention_mask = np.ones(len(input_ids), dtype=np.int64)

        # Pad to 512
        if len(input_ids) < 512:
            padding = 512 - len(input_ids)
            input_ids = np.pad(input_ids, (0, padding), constant_values=0)
            attention_mask = np.pad(attention_mask, (0, padding), constant_values=0)

        return {
            "input_ids": input_ids.reshape(1, -1).astype(np.int64),
            "attention_mask": attention_mask.reshape(1, -1).astype(np.int64)
        }

    async def classify_text(self, text: str) -> tuple[list[float], list[str]]:
        """
        Classify text using ONNX model - fail fast if unavailable

        Returns:
            Tuple of (scores, labels)
        """
        # Session should be available due to fail-fast initialization
        assert self.session is not None, "ONNX session not initialized"

        # Tokenize input
        inputs = self._tokenize_text(text)

        # Run inference
        outputs = self.session.run(None, inputs)
        logits = outputs[0][0]  # Assuming first output is logits

        # Apply softmax to get probabilities
        exp_logits = np.exp(logits - np.max(logits))
        probabilities = exp_logits / np.sum(exp_logits)

        return probabilities.tolist(), self.config.labels



# Pre-configured model configurations
FINANCIAL_ADVICE_MODEL = ModelConfig(
    model_path="models/financial_advice_distilbert.onnx",
    tokenizer_config={
        "vocab": {},  # Would be loaded from tokenizer.json
        "model_type": "distilbert"
    },
    labels=["safe", "financial_advice"],
    threshold=0.7,
    max_length=512
)

LEGAL_ADVICE_MODEL = ModelConfig(
    model_path="models/legal_advice_roberta.onnx",
    tokenizer_config={
        "vocab": {},
        "model_type": "roberta"
    },
    labels=["safe", "legal_advice"],
    threshold=0.8,
    max_length=512
)

GENERAL_COMPLIANCE_MODEL = ModelConfig(
    model_path="models/compliance_bert.onnx",
    tokenizer_config={
        "vocab": {},
        "model_type": "bert"
    },
    labels=["compliant", "non_compliant"],
    threshold=0.6,
    max_length=512
)


@register_factory("business.financial_advice_onnx", tier="T2", description="ONNX-based financial advice detection with semantic understanding", performance_budget_ms=100.0)
def financial_advice_onnx_guard(
    model_config: dict[str, Any] | None = None,
    threshold: float = 0.7,
    severity: str = "critical",
    fallback_enabled: bool = False
) -> Guard:
    """
    Advanced financial advice detection using ONNX models

    This guard can catch subtle financial advice that regex patterns miss:
    - Implicit recommendations ("Apple looks promising")
    - Contextual advice ("In your situation, I'd consider...")
    - Semantic variations ("You might want to look into...")

    Args:
        model_config: Custom model configuration
        threshold: Classification threshold
        severity: Violation severity level
    """

    # Use default config if none provided
    config = FINANCIAL_ADVICE_MODEL
    if model_config:
        config = ModelConfig(**model_config)

    config.threshold = threshold
    # Initialize classifier; optionally allow rule-based fallback when ONNX unavailable
    try:
        classifier = ONNXTextClassifier(config)
    except Exception:
        if not fallback_enabled:
            raise
        classifier = None

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
        if not classifier:
            # Fallback: simple heuristic detection
            lower = text.lower()
            if any(kw in lower for kw in ["buy", "sell", "invest", "stock", "shares"]):
                return Left_([Violation(
                    rule_id="business.financial_advice_onnx",
                    severity=severity,
                    message="Heuristic financial advice detected (fallback)",
                    tier="T2",
                )])
            return Right_(ctx)

        scores, labels = await classifier.classify_text(text)

        # Find financial advice score
        financial_score = 0.0
        for i, label in enumerate(labels):
            if "financial_advice" in label.lower() or "advice" in label.lower():
                financial_score = scores[i]
                break

        if financial_score >= threshold:
            return Left_([Violation(
                rule_id="business.financial_advice_onnx",
                severity=severity,
                message=f"ONNX model detected financial advice (confidence: {financial_score:.2f})",
                score=financial_score,
                tier="T2",
                evidence={
                    "model_scores": dict(zip(labels, scores, strict=False)),
                    "confidence": financial_score,
                    "threshold": threshold,
                    "text_analyzed": text[:200] + "..." if len(text) > 200 else text,
                    "model_used": "ONNX" if classifier.session else "fallback"
                }
            )])

        return Right_(ctx)

    return run


@register_factory("business.legal_advice_onnx", tier="T2", description="ONNX-based legal advice detection with semantic understanding", performance_budget_ms=120.0)
def legal_advice_onnx_guard(
    model_config: dict[str, Any] | None = None,
    threshold: float = 0.8,
    severity: str = "high"
) -> Guard:
    """
    Advanced legal advice detection using ONNX models

    Can detect subtle legal advice patterns:
    - Implicit legal opinions ("That sounds illegal")
    - Contextual legal guidance ("In cases like this...")
    - Professional liability risks
    """

    config = LEGAL_ADVICE_MODEL
    if model_config:
        config = ModelConfig(**model_config)

    config.threshold = threshold
    classifier = ONNXTextClassifier(config)

    async def run(ctx: Ctx) -> Either:
        text = ctx.get("output", "")
        if not text and "messages" in ctx:
            messages = ctx.get("messages", [])
            if isinstance(messages, list) and messages:
                text = messages[-1].get("content", "") if isinstance(messages[-1], dict) else str(messages[-1])

        if not isinstance(text, str) or not text.strip():
            return Right_(ctx)

        scores, labels = await classifier.classify_text(text)

        legal_score = 0.0
        for i, label in enumerate(labels):
            if "legal" in label.lower():
                legal_score = scores[i]
                break

        if legal_score >= threshold:
            return Left_([Violation(
                rule_id="business.legal_advice_onnx",
                severity=severity,
                message=f"ONNX model detected legal advice (confidence: {legal_score:.2f})",
                score=legal_score,
                tier="T2",
                evidence={
                    "model_scores": dict(zip(labels, scores, strict=False)),
                    "confidence": legal_score,
                    "threshold": threshold,
                    "text_analyzed": text[:200] + "..." if len(text) > 200 else text,
                    "model_used": "ONNX" if classifier.session else "fallback"
                }
            )])

        return Right_(ctx)

    return run


@register_factory("business.compliance_onnx", tier="T2", description="General business compliance detection using ONNX", performance_budget_ms=80.0)
def general_compliance_onnx_guard(
    model_config: dict[str, Any] | None = None,
    threshold: float = 0.6,
    compliance_categories: list[str] = None,
    severity: str = "medium"
) -> Guard:
    """
    General business compliance detection using ONNX models

    Can detect various compliance issues:
    - Regulatory violations
    - Professional standards breaches
    - Industry-specific compliance issues
    """

    if compliance_categories is None:
        compliance_categories = ["financial", "legal", "medical", "privacy"]

    config = GENERAL_COMPLIANCE_MODEL
    if model_config:
        config = ModelConfig(**model_config)

    config.threshold = threshold
    classifier = ONNXTextClassifier(config)

    async def run(ctx: Ctx) -> Either:
        text = ctx.get("output", "")
        if not text and "messages" in ctx:
            messages = ctx.get("messages", [])
            if isinstance(messages, list) and messages:
                text = messages[-1].get("content", "") if isinstance(messages[-1], dict) else str(messages[-1])

        if not isinstance(text, str) or not text.strip():
            return Right_(ctx)

        scores, labels = await classifier.classify_text(text)

        # Check for non-compliant content
        non_compliant_score = 0.0
        for i, label in enumerate(labels):
            if "non_compliant" in label.lower() or "violation" in label.lower():
                non_compliant_score = scores[i]
                break

        if non_compliant_score >= threshold:
            return Left_([Violation(
                rule_id="business.compliance_onnx",
                severity=severity,
                message=f"ONNX model detected compliance issue (confidence: {non_compliant_score:.2f})",
                score=non_compliant_score,
                tier="T2",
                evidence={
                    "model_scores": dict(zip(labels, scores, strict=False)),
                    "confidence": non_compliant_score,
                    "threshold": threshold,
                    "categories_checked": compliance_categories,
                    "text_analyzed": text[:200] + "..." if len(text) > 200 else text,
                    "model_used": "ONNX" if classifier.session else "fallback"
                }
            )])

        return Right_(ctx)

    return run
