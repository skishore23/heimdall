#!/usr/bin/env python3
"""
Download and convert ONNX models for guardrails

Functional approach with small, composable functions.
Fails fast - no fallbacks or placeholders.
"""

import sys
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# === Pure functions for model conversion ===

def check_dependencies() -> None:
    """Check required dependencies are installed - fail fast if missing"""
    try:
        import torch
        import transformers
    except ImportError as e:
        raise ImportError(
            f"Missing dependencies: {e}\n"
            "Install with: pip install transformers torch"
        )


def download_model(model_name: str) -> Any:
    """Download model from HuggingFace - fail fast if unavailable"""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    print(f"📥 Downloading {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    print(f"✅ Downloaded {model_name}")

    return tokenizer, model


def convert_to_onnx(model: Any, tokenizer: Any, output_path: Path) -> None:
    """Convert model to ONNX format - fail fast if conversion fails"""
    import torch

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"🔄 Converting to ONNX: {output_path.name}")

    # Create dummy input for export
    dummy_text = "This is a test sentence for model conversion"
    inputs = tokenizer(dummy_text, return_tensors="pt", padding="max_length", max_length=128, truncation=True)

    # Set model to eval mode
    model.eval()

    # Export to ONNX with simplified approach
    with torch.no_grad():
        torch.onnx.export(
            model,
            (inputs["input_ids"], inputs["attention_mask"]),
            str(output_path),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch_size", 1: "sequence"},
                "attention_mask": {0: "batch_size", 1: "sequence"},
                "logits": {0: "batch_size"}
            },
            opset_version=14,
            do_constant_folding=True,
            export_params=True
        )

    print(f"✅ Converted to ONNX: {output_path}")


def verify_onnx_model(model_path: Path) -> None:
    """Verify ONNX model is valid - fail fast if invalid"""
    import onnxruntime as ort

    print(f"🔍 Verifying {model_path.name}...")

    # Test inference session can be created
    session = ort.InferenceSession(str(model_path))

    # Verify we can get model metadata
    input_names = [inp.name for inp in session.get_inputs()]
    output_names = [out.name for out in session.get_outputs()]

    print(f"   Inputs: {input_names}")
    print(f"   Outputs: {output_names}")

    # Get model size
    size_mb = model_path.stat().st_size / (1024 * 1024)
    print(f"✅ Verified {model_path.name} ({size_mb:.1f}MB)")


# === Model download configurations ===

def get_toxicity_config() -> dict[str, Any]:
    """Configuration for toxicity detection model"""
    return {
        "name": "toxicity_detoxify",
        "hf_model": "distilbert-base-uncased-finetuned-sst-2-english",
        "output_path": "models/toxicity_detoxify.onnx",
        "description": "Sentiment/toxicity detection using DistilBERT (small, fast)"
    }


def get_financial_config() -> dict[str, Any]:
    """Configuration for financial advice detection model"""
    return {
        "name": "financial_advice_distilbert",
        "hf_model": "yiyanghkust/finbert-tone",
        "output_path": "models/financial_advice_distilbert.onnx",
        "description": "Financial sentiment/tone detection (lighter than full FinBERT)"
    }


# === Orchestration ===

def download_and_convert_model(config: dict[str, Any]) -> None:
    """
    Download and convert a single model
    Pure orchestration - delegates to smaller functions
    """
    print(f"\n{'='*60}")
    print(f"Processing: {config['name']}")
    print(f"Description: {config['description']}")
    print(f"{'='*60}")

    output_path = Path(config["output_path"])

    # Download
    tokenizer, model = download_model(config["hf_model"])

    # Convert
    convert_to_onnx(model, tokenizer, output_path)

    # Verify
    verify_onnx_model(output_path)

    print(f"✅ Completed: {config['name']}\n")


def download_essential_models() -> None:
    """Download essential models for guardrails"""
    check_dependencies()

    models = [
        get_toxicity_config(),
        get_financial_config()
    ]

    print("🚀 Downloading essential ONNX models for guardrails")
    print(f"Total models: {len(models)}\n")

    for config in models:
        download_and_convert_model(config)

    print("🎉 All models downloaded successfully!")
    print("\nNext steps:")
    print("1. Run: python cli_onnx.py list")
    print("2. Test with policies using ONNX guards")


# === CLI ===

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Download and convert ONNX models for guardrails"
    )
    parser.add_argument(
        "--model",
        choices=["toxicity", "financial", "all"],
        default="all",
        help="Which model(s) to download"
    )

    args = parser.parse_args()

    try:
        if args.model == "all":
            download_essential_models()
        elif args.model == "toxicity":
            download_and_convert_model(get_toxicity_config())
        elif args.model == "financial":
            download_and_convert_model(get_financial_config())

    except Exception as e:
        print(f"\n❌ Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

