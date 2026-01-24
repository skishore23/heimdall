"""
Production-optimized ONNX Runtime Configuration

Provides tuned SessionOptions, quantization support, micro-batching,
execution provider negotiation, and model attestation.
"""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

try:
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    ort = None
    np = None
    Tokenizer = None


@dataclass
class ONNXConfig:
    """ONNX Runtime configuration"""
    execution_provider: Literal["CPU", "CUDA", "OpenVINO", "TensorRT"] = "CPU"
    intra_op_num_threads: int = 4
    inter_op_num_threads: int = 2
    graph_optimization_level: str = "ORT_ENABLE_ALL"
    enable_cpu_mem_arena: bool = True
    enable_mem_pattern: bool = True
    enable_profiling: bool = False
    quantization: Literal["fp32", "fp16", "int8"] = "int8"
    micro_batch_size: int = 4
    max_queue_ms: float = 10.0


@dataclass
class ModelAttestation:
    """Model file attestation"""
    model_id: str
    expected_sha256: str
    allow_custom_ops: bool = False



def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def verify_model_attestation(file_path: Path, attestation: ModelAttestation) -> None:
    """
    Verify model file integrity

    Args:
        file_path: Path to ONNX model file
        attestation: Expected attestation

    Raises:
        ValueError: If attestation fails
    """
    actual_hash = compute_file_hash(file_path)

    if actual_hash != attestation.expected_sha256:
        raise ValueError(
            f"Model attestation failed for '{attestation.model_id}': "
            f"expected {attestation.expected_sha256}, got {actual_hash}"
        )


def create_optimized_session_options(config: ONNXConfig) -> Any:
    """
    Create optimized ONNX SessionOptions

    Args:
        config: ONNX configuration

    Returns:
        SessionOptions instance
    """
    if not ONNX_AVAILABLE:
        raise RuntimeError("ONNX Runtime not available. Install with: pip install onnxruntime")

    sess_options = ort.SessionOptions()

    # Thread configuration
    sess_options.intra_op_num_threads = config.intra_op_num_threads
    sess_options.inter_op_num_threads = config.inter_op_num_threads

    # Graph optimization
    if config.graph_optimization_level == "ORT_ENABLE_ALL":
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    elif config.graph_optimization_level == "ORT_ENABLE_EXTENDED":
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
    elif config.graph_optimization_level == "ORT_ENABLE_BASIC":
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    else:
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL

    # Memory optimization
    sess_options.enable_cpu_mem_arena = config.enable_cpu_mem_arena
    sess_options.enable_mem_pattern = config.enable_mem_pattern

    # Profiling (dev only)
    sess_options.enable_profiling = config.enable_profiling

    return sess_options


def negotiate_execution_provider(preferred: str) -> list[str]:
    """
    Negotiate execution provider based on availability

    Args:
        preferred: Preferred execution provider

    Returns:
        List of providers in priority order
    """
    if not ONNX_AVAILABLE:
        raise RuntimeError("ONNX Runtime not available")

    available = ort.get_available_providers()

    provider_map = {
        "CUDA": "CUDAExecutionProvider",
        "CPU": "CPUExecutionProvider",
        "OpenVINO": "OpenVINOExecutionProvider",
        "TensorRT": "TensorrtExecutionProvider",
    }

    preferred_provider = provider_map.get(preferred, "CPUExecutionProvider")

    # Build priority list
    providers = []

    if preferred_provider in available:
        providers.append(preferred_provider)

    # Always fall back to CPU
    if "CPUExecutionProvider" not in providers:
        providers.append("CPUExecutionProvider")

    return providers


class OptimizedONNXSession:
    """
    Optimized ONNX inference session with micro-batching
    """

    def __init__(
        self,
        model_path: Path,
        config: ONNXConfig,
        attestation: ModelAttestation | None = None,
        tokenizer_path: Path | None = None
    ):
        """
        Initialize optimized ONNX session

        Args:
            model_path: Path to ONNX model file
            config: ONNX configuration
            attestation: Optional model attestation
            tokenizer_path: Optional tokenizer JSON file
        """
        if not ONNX_AVAILABLE:
            raise RuntimeError("ONNX Runtime not available")

        # Verify attestation if provided
        if attestation:
            verify_model_attestation(model_path, attestation)

        # Create session options
        sess_options = create_optimized_session_options(config)

        # Negotiate execution provider
        providers = negotiate_execution_provider(config.execution_provider)

        # Create session
        self.session = ort.InferenceSession(
            str(model_path),
            sess_options=sess_options,
            providers=providers
        )

        self.config = config
        self.tokenizer = None

        # Load tokenizer if provided
        if tokenizer_path:
            if not ONNX_AVAILABLE or Tokenizer is None:
                raise RuntimeError("Tokenizers library not available")
            self.tokenizer = Tokenizer.from_file(str(tokenizer_path))

        # Micro-batching state
        self.batch_queue: list[dict[str, Any]] = []
        self.batch_deadline: float | None = None

    def _tokenize_text(self, text: str) -> dict[str, np.ndarray]:
        """Tokenize text input"""
        if self.tokenizer is None:
            raise ValueError("Tokenizer not configured")

        encoding = self.tokenizer.encode(text)

        return {
            "input_ids": np.array([encoding.ids], dtype=np.int64),
            "attention_mask": np.array([encoding.attention_mask], dtype=np.int64),
        }

    def run_inference(self, inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """
        Run inference on a single input

        Args:
            inputs: Dictionary of input tensors

        Returns:
            Dictionary of output tensors
        """
        outputs = self.session.run(None, inputs)

        # Map outputs to names
        output_names = [out.name for out in self.session.get_outputs()]
        return dict(zip(output_names, outputs, strict=False))

    def run_inference_batched(self, batch_inputs: list[dict[str, np.ndarray]]) -> list[dict[str, np.ndarray]]:
        """
        Run inference on a batch of inputs

        Args:
            batch_inputs: List of input dictionaries

        Returns:
            List of output dictionaries
        """
        if len(batch_inputs) == 0:
            return []

        # Stack inputs into batches
        batched = {}
        for key in batch_inputs[0].keys():
            batched[key] = np.vstack([inp[key] for inp in batch_inputs])

        # Run inference
        outputs = self.session.run(None, batched)

        # Unstack outputs
        output_names = [out.name for out in self.session.get_outputs()]
        results = []

        for i in range(len(batch_inputs)):
            result = {}
            for name, output in zip(output_names, outputs, strict=False):
                result[name] = output[i:i+1]
            results.append(result)

        return results

    def infer_with_micro_batching(
        self,
        inputs: dict[str, np.ndarray],
        timeout_ms: float | None = None
    ) -> dict[str, np.ndarray]:
        """
        Run inference with micro-batching optimization

        Args:
            inputs: Input tensors
            timeout_ms: Optional timeout (uses config.max_queue_ms if None)

        Returns:
            Output tensors
        """
        max_queue_ms = timeout_ms if timeout_ms is not None else self.config.max_queue_ms

        # Add to batch queue
        self.batch_queue.append(inputs)

        # Set deadline if first item
        if self.batch_deadline is None:
            self.batch_deadline = time.time() + (max_queue_ms / 1000.0)

        # Check if we should flush
        should_flush = (
            len(self.batch_queue) >= self.config.micro_batch_size or
            time.time() >= self.batch_deadline
        )

        if should_flush:
            # Run batch inference
            batch_results = self.run_inference_batched(self.batch_queue)

            # Clear queue
            self.batch_queue = []
            self.batch_deadline = None

            # Return last result (the one we just added)
            return batch_results[-1]
        else:
            # Wait for batch to fill or deadline
            # In production, this would use async/await
            # For now, just run single inference
            return self.run_inference(inputs)


def load_quantized_model(
    model_path: Path,
    quantization: Literal["fp32", "fp16", "int8"],
    fallback: bool = True
) -> Path:
    """
    Load quantized model variant or fall back to FP32

    Args:
        model_path: Base model path (e.g., model.onnx)
        quantization: Desired quantization level
        fallback: Whether to fall back to FP32 if quantized version not found

    Returns:
        Path to model file

    Raises:
        FileNotFoundError: If model not found and fallback=False
    """
    if quantization == "fp32":
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        return model_path

    # Try quantized variant
    stem = model_path.stem
    suffix = model_path.suffix
    parent = model_path.parent

    quantized_path = parent / f"{stem}_{quantization}{suffix}"

    if quantized_path.exists():
        return quantized_path

    if fallback and model_path.exists():
        return model_path

    raise FileNotFoundError(
        f"Quantized model not found: {quantized_path} "
        f"(fallback={'enabled' if fallback else 'disabled'})"
    )

