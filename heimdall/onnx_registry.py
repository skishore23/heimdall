"""
ONNX Model Registry

Core system for managing ONNX MODEL FILES and their configurations.
This is separate from the Guard Registry which manages guard factories.

Responsibilities:
- Discovering and loading ONNX model files
- Managing model metadata (accuracy, size, performance budgets)
- Providing model sessions for inference
- Model file validation and error handling

Note: This works with the Guard Registry:
- ONNXRegistry: Provides available models and loads them
- Registry: Tracks which guard factories can use those models
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import onnxruntime as ort

logger = logging.getLogger(__name__)

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    ort = None


@dataclass
class ONNXModelInfo:
    """Information about an available ONNX model"""
    id: str
    name: str
    description: str
    category: str  # financial, legal, toxicity, sentiment, etc.
    model_path: str
    tokenizer_config: dict[str, Any]
    labels: list[str]
    default_threshold: float
    performance_budget_ms: float
    accuracy: float | None = None
    model_size_mb: float | None = None
    supported_languages: list[str] = None
    source_url: str | None = None
    license: str | None = None

    def __post_init__(self):
        if self.supported_languages is None:
            self.supported_languages = ["en"]


class ONNXModelRegistry:
    """
    Central registry for ONNX models

    Manages model discovery, loading, and configuration across all guard packs.
    """

    def __init__(self, models_dir: str = "models"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(exist_ok=True)
        self._models: dict[str, ONNXModelInfo] = {}
        self._loaded_sessions: dict[str, ort.InferenceSession] = {}
        self._load_builtin_models()
        self._discover_user_models()

    def _load_builtin_models(self):
        """Load built-in model configurations"""

        # Financial Domain Models
        self.register_model(ONNXModelInfo(
            id="financial_advice_distilbert",
            name="DistilBERT Financial Advice Classifier",
            description="Fast and accurate financial advice detection using DistilBERT",
            category="financial",
            model_path="models/financial_advice_distilbert.onnx",
            tokenizer_config={
                "model_type": "distilbert",
                "vocab_size": 30522,
                "max_length": 512,
                "pad_token_id": 0,
                "cls_token_id": 101,
                "sep_token_id": 102
            },
            labels=["safe", "financial_advice"],
            default_threshold=0.7,
            performance_budget_ms=50.0,
            accuracy=0.92,
            model_size_mb=250,
            source_url="https://huggingface.co/ProsusAI/finbert",
            license="Apache-2.0"
        ))

        self.register_model(ONNXModelInfo(
            id="financial_compliance_roberta",
            name="RoBERTa Financial Compliance",
            description="Advanced financial compliance detection with regulatory context",
            category="financial",
            model_path="models/financial_compliance_roberta.onnx",
            tokenizer_config={
                "model_type": "roberta",
                "vocab_size": 50265,
                "max_length": 512,
                "pad_token_id": 1,
                "cls_token_id": 0,
                "sep_token_id": 2
            },
            labels=["compliant", "non_compliant", "requires_disclaimer"],
            default_threshold=0.8,
            performance_budget_ms=80.0,
            accuracy=0.94,
            model_size_mb=500
        ))

        # Legal Domain Models
        self.register_model(ONNXModelInfo(
            id="legal_advice_bert",
            name="Legal-BERT Advice Classifier",
            description="Specialized legal advice detection using Legal-BERT",
            category="legal",
            model_path="models/legal_advice_bert.onnx",
            tokenizer_config={
                "model_type": "bert",
                "vocab_size": 30522,
                "max_length": 512,
                "pad_token_id": 0,
                "cls_token_id": 101,
                "sep_token_id": 102
            },
            labels=["safe", "legal_advice", "professional_liability"],
            default_threshold=0.8,
            performance_budget_ms=70.0,
            accuracy=0.89,
            model_size_mb=400,
            source_url="https://huggingface.co/nlpaueb/legal-bert-base-uncased"
        ))

        # Toxicity Models
        self.register_model(ONNXModelInfo(
            id="toxicity_detoxify",
            name="Detoxify Toxicity Classifier",
            description="Multi-label toxicity detection (toxic, severe_toxic, obscene, threat, insult)",
            category="toxicity",
            model_path="models/toxicity_detoxify.onnx",
            tokenizer_config={
                "model_type": "bert",
                "vocab_size": 30522,
                "max_length": 512
            },
            labels=["toxic", "severe_toxic", "obscene", "threat", "insult", "identity_hate"],
            default_threshold=0.5,
            performance_budget_ms=60.0,
            accuracy=0.95,
            model_size_mb=400,
            source_url="https://huggingface.co/unitary/toxic-bert"
        ))

        # Sentiment Analysis
        self.register_model(ONNXModelInfo(
            id="sentiment_roberta",
            name="RoBERTa Sentiment Analysis",
            description="Fine-grained sentiment analysis for business communications",
            category="sentiment",
            model_path="models/sentiment_roberta.onnx",
            tokenizer_config={
                "model_type": "roberta",
                "vocab_size": 50265,
                "max_length": 512
            },
            labels=["negative", "neutral", "positive"],
            default_threshold=0.6,
            performance_budget_ms=45.0,
            accuracy=0.91,
            model_size_mb=300
        ))

        # PII Detection
        self.register_model(ONNXModelInfo(
            id="pii_detection_bert",
            name="BERT PII Detection",
            description="Named Entity Recognition for PII detection",
            category="pii",
            model_path="models/pii_detection_bert.onnx",
            tokenizer_config={
                "model_type": "bert",
                "vocab_size": 30522,
                "max_length": 512
            },
            labels=["O", "B-PERSON", "I-PERSON", "B-EMAIL", "I-EMAIL", "B-PHONE", "I-PHONE"],
            default_threshold=0.9,
            performance_budget_ms=55.0,
            accuracy=0.96,
            model_size_mb=350
        ))

        # Content Classification
        self.register_model(ONNXModelInfo(
            id="content_classifier_distilbert",
            name="DistilBERT Content Classifier",
            description="General content classification for business use cases",
            category="content",
            model_path="models/content_classifier_distilbert.onnx",
            tokenizer_config={
                "model_type": "distilbert",
                "vocab_size": 30522,
                "max_length": 512
            },
            labels=["business", "personal", "technical", "legal", "financial", "medical"],
            default_threshold=0.7,
            performance_budget_ms=40.0,
            accuracy=0.88,
            model_size_mb=200
        ))

        # Multilingual Models
        self.register_model(ONNXModelInfo(
            id="multilingual_toxicity_bert",
            name="Multilingual BERT Toxicity",
            description="Toxicity detection across multiple languages",
            category="toxicity",
            model_path="models/multilingual_toxicity_bert.onnx",
            tokenizer_config={
                "model_type": "bert",
                "vocab_size": 119547,  # multilingual vocab
                "max_length": 512
            },
            labels=["safe", "toxic"],
            default_threshold=0.6,
            performance_budget_ms=90.0,
            accuracy=0.87,
            model_size_mb=700,
            supported_languages=["en", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "ja", "ko", "zh"]
        ))

    def _discover_user_models(self):
        """Discover user-provided models in the models directory"""
        config_files = list(self.models_dir.glob("*.json"))

        for config_file in config_files:
            try:
                with open(config_file) as f:
                    config = json.load(f)

                model_info = ONNXModelInfo(**config)
                self.register_model(model_info)
                logger.info("Loaded user model: %s", model_info.id)

            except Exception as e:
                logger.warning("Failed to load model config %s: %s", config_file, e)

    def register_model(self, model_info: ONNXModelInfo):
        """Register a new ONNX model"""
        self._models[model_info.id] = model_info

    def get_model(self, model_id: str) -> ONNXModelInfo | None:
        """Get model information by ID"""
        return self._models.get(model_id)

    def list_models(self, category: str | None = None) -> list[ONNXModelInfo]:
        """List available models, optionally filtered by category"""
        models = list(self._models.values())

        if category:
            models = [m for m in models if m.category == category]

        return sorted(models, key=lambda m: (m.category, m.name))

    def get_categories(self) -> list[str]:
        """Get all available model categories"""
        categories = {model.category for model in self._models.values()}
        return sorted(categories)

    def load_model_session(self, model_id: str) -> Optional["ort.InferenceSession"]:
        """Load ONNX model session"""
        if not ONNX_AVAILABLE:
            logger.warning("ONNX Runtime not available")
            return None

        if model_id in self._loaded_sessions:
            return self._loaded_sessions[model_id]

        model_info = self.get_model(model_id)
        if not model_info:
            logger.error("Model not found: %s", model_id)
            return None

        model_path = Path(model_info.model_path)
        if not model_path.exists():
            logger.warning("Model file not found: %s", model_path)
            logger.warning("Download from: %s", model_info.source_url or "N/A")
            return None

        try:
            # Optimize session for performance
            session_options = ort.SessionOptions()
            session_options.intra_op_num_threads = 4
            session_options.execution_mode = ort.ExecutionMode.ORT_PARALLEL
            session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            # Use GPU if available
            providers = ['CPUExecutionProvider']
            if ort.get_device() == 'GPU':
                providers.insert(0, 'CUDAExecutionProvider')

            session = ort.InferenceSession(
                str(model_path),
                sess_options=session_options,
                providers=providers
            )

            self._loaded_sessions[model_id] = session
            logger.info("Loaded ONNX model: %s", model_id)
            return session

        except Exception as e:
            logger.error("Failed to load ONNX model %s: %s", model_id, e)
            return None

    def create_model_config_template(self, output_path: str):
        """Create a template for user model configuration"""
        template = {
            "id": "my_custom_model",
            "name": "My Custom Model",
            "description": "Description of what this model does",
            "category": "custom",  # financial, legal, toxicity, sentiment, pii, content, custom
            "model_path": "models/my_custom_model.onnx",
            "tokenizer_config": {
                "model_type": "bert",  # bert, roberta, distilbert, gpt2, etc.
                "vocab_size": 30522,
                "max_length": 512,
                "pad_token_id": 0,
                "cls_token_id": 101,
                "sep_token_id": 102
            },
            "labels": ["label1", "label2"],
            "default_threshold": 0.7,
            "performance_budget_ms": 100.0,
            "accuracy": 0.85,
            "model_size_mb": 400,
            "supported_languages": ["en"],
            "source_url": "https://huggingface.co/your-model",
            "license": "Apache-2.0"
        }

        with open(output_path, 'w') as f:
            json.dump(template, f, indent=2)

        logger.info("Created model config template: %s", output_path)

    def get_model_stats(self) -> dict[str, Any]:
        """Get statistics about available models"""
        models = list(self._models.values())
        categories = {}

        for model in models:
            if model.category not in categories:
                categories[model.category] = []
            categories[model.category].append(model.id)

        return {
            "total_models": len(models),
            "categories": categories,
            "loaded_sessions": len(self._loaded_sessions),
            "average_accuracy": sum(m.accuracy for m in models if m.accuracy) / len([m for m in models if m.accuracy]),
            "total_size_mb": sum(m.model_size_mb for m in models if m.model_size_mb)
        }


# Global registry instance
onnx_registry = ONNXModelRegistry()


def get_onnx_registry() -> ONNXModelRegistry:
    """Get the global ONNX model registry"""
    return onnx_registry


def list_available_models(category: str | None = None) -> list[dict[str, Any]]:
    """List available ONNX models as dictionaries"""
    models = onnx_registry.list_models(category)
    return [asdict(model) for model in models]


def get_model_info(model_id: str) -> dict[str, Any] | None:
    """Get model information as dictionary"""
    model = onnx_registry.get_model(model_id)
    return asdict(model) if model else None


def load_onnx_model(model_id: str) -> Optional["ort.InferenceSession"]:
    """Load ONNX model session"""
    return onnx_registry.load_model_session(model_id)


# CLI functions for model management
def cli_list_models():
    """CLI command to list available models"""
    registry = get_onnx_registry()
    models = registry.list_models()

    logger.info("\nAvailable models:\n%s", "=" * 80)

    current_category = None
    for model in models:
        if model.category != current_category:
            current_category = model.category
            logger.info("\n%s MODELS:", current_category.upper())
            logger.info("%s", "-" * 40)

        status = "✅" if Path(model.model_path).exists() else "⚠️ "
        accuracy = f"{model.accuracy:.1%}" if model.accuracy else "N/A"
        size = f"{model.model_size_mb}MB" if model.model_size_mb else "N/A"

        logger.info("%s %s", status, model.id)
        logger.info("   Name: %s", model.name)
        logger.info("   Description: %s", model.description)
        logger.info("   Accuracy: %s | Size: %s | Budget: %sms", accuracy, size, model.performance_budget_ms)
        logger.info("   Labels: %s", ", ".join(model.labels))
        if model.source_url:
            logger.info("   Source: %s", model.source_url)
        logger.info("")


def cli_model_stats():
    """CLI command to show model statistics"""
    registry = get_onnx_registry()
    stats = registry.get_model_stats()

    logger.info("\nModel statistics:\n%s", "=" * 40)
    logger.info("Total models: %s", stats["total_models"])
    logger.info("Loaded sessions: %s", stats["loaded_sessions"])
    logger.info("Average accuracy: %.1f%%", stats["average_accuracy"] * 100)
    logger.info("Total size: %.1fMB", stats["total_size_mb"])
    logger.info("")
    logger.info("Models by category:")
    for category, model_ids in stats["categories"].items():
        logger.info("  %s: %s models", category, len(model_ids))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "list":
            cli_list_models()
        elif command == "stats":
            cli_model_stats()
        elif command == "template":
            output_path = sys.argv[2] if len(sys.argv) > 2 else "model_config_template.json"
            onnx_registry.create_model_config_template(output_path)
        else:
            logger.info("Usage: python onnx_registry.py [list|stats|template]")
    else:
        cli_list_models()
