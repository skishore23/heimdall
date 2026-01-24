# ONNX Runtime Safety Guards

Local ML guards using ONNX Runtime for offline safety detection without external API dependencies.

## Overview

The safety guard pack provides T2 (ML-based) guards that are gated by T1 (rule-based) scores for optimal performance:

- **T1 Guards**: Fast rule-based detection (always run)
- **T2 Guards**: ML-based detection (gated by T1 scores)
- **Performance**: 90%+ of requests skip ML inference

## Installation

```bash
# Install ONNX Runtime
pip install onnxruntime

# For GPU acceleration (optional)
pip install onnxruntime-gpu
```

## Available Guards

### `safety.toxicity.local_onnx`
Local toxicity detection using ONNX models.

```yaml
guards:
  - id: safety.toxicity.local_onnx
    enabled: true    # set false to remove ONNX path entirely
    with: 
      model: "detoxify_tiny.onnx"
      threshold: 0.35
      gated_by: "t1_score>0.6"  # only run if T1 indicates risk
```

### `safety.jailbreak.local_onnx`
Jailbreak attempt detection for prompt injection prevention.

```yaml
guards:
  - id: safety.jailbreak.local_onnx
    enabled: true
    with:
      model: "jailbreak_detector.onnx"
      threshold: 0.7
      gated_by: "t1_score>0.8"  # higher threshold for performance
```

### `safety.ner.local_onnx`
Named Entity Recognition for PII detection and data classification.

```yaml
guards:
  - id: safety.ner.local_onnx
    enabled: false   # disabled by default
    with:
      model: "ner_tiny.onnx"
      entities: ["PERSON", "ORG", "GPE", "MONEY"]
```

## Configuration Patterns

### Production (Conservative)
```yaml
guards:
  - id: safety.toxicity.local_onnx
    enabled: true
    with: { model: "detoxify_tiny.onnx", threshold: 0.35, gated_by: "t1_score>0.6" }
  
  - id: safety.jailbreak.local_onnx
    enabled: true
    with: { model: "jailbreak_detector.onnx", threshold: 0.7, gated_by: "t1_score>0.8" }
```

### High Security (Aggressive)
```yaml
guards:
  - id: safety.toxicity.local_onnx
    enabled: true
    with: { model: "detoxify_tiny.onnx", threshold: 0.2, gated_by: "t1_score>0.3" }
  
  - id: safety.jailbreak.local_onnx
    enabled: true
    with: { model: "jailbreak_detector.onnx", threshold: 0.5, gated_by: "t1_score>0.5" }
```

### Performance Optimized
```yaml
guards:
  - id: safety.toxicity.local_onnx
    enabled: true
    with: { model: "detoxify_tiny.onnx", threshold: 0.5, gated_by: "t1_score>0.8" }
  
  - id: safety.jailbreak.local_onnx
    enabled: false  # disabled for maximum performance
```

### ONNX Disabled (Rules Only)
```yaml
guards:
  - id: safety.toxicity.local_onnx
    enabled: false  # falls back to pattern-based detection
```

## Model Management

### Model Directory Structure
```
guards/safety/models/
├── detoxify_tiny.onnx          # Toxicity detection model
├── jailbreak_detector.onnx     # Jailbreak detection model
└── ner_tiny.onnx              # Named entity recognition model
```

### Adding Custom Models

1. **Convert your model to ONNX format**:
```python
import torch
import onnx

# Convert PyTorch model
torch.onnx.export(model, dummy_input, "custom_model.onnx")
```

2. **Place in models directory**:
```bash
cp custom_model.onnx guards/safety/models/
```

3. **Configure in policy**:
```yaml
guards:
  - id: safety.toxicity.local_onnx
    with: { model: "custom_model.onnx" }
```

## Performance Characteristics

### Request Distribution (Typical)
- **Clean requests (90%)**: T1 pass, T2 skip
- **Mild risk (8%)**: T1 flag, T2 toxicity runs
- **High risk (2%)**: T1 flag, T2 all guards run

### Efficiency Gains
- **90%** of requests skip T2 Toxicity ML
- **98%** of requests skip T2 Jailbreak ML
- **Sub-millisecond** T1 processing
- **10-50ms** T2 processing (when triggered)

## Gating Logic

Guards use the `gated_by` parameter to conditionally execute based on T1 scores:

```python
# Example gating conditions
gated_by: "t1_score>0.6"     # Run if T1 score exceeds 0.6
gated_by: "t1_score>0.8"     # Run if T1 score exceeds 0.8 (more selective)
```

## Fallback Behavior

When ONNX models are unavailable, guards automatically fall back to pattern-based detection:

- **Toxicity**: Regex patterns for common toxic language
- **Jailbreak**: Pattern matching for prompt injection attempts
- **NER**: Regex-based entity detection

## Monitoring and Debugging

### Enable Debug Logging
```python
import logging
logging.getLogger("onnxruntime").setLevel(logging.DEBUG)
```

### Performance Metrics
```python
# Track T1/T2 execution rates
ctx["metadata"]["t1_executed"] = True
ctx["metadata"]["t2_executed"] = t1_score > gate_threshold
```

## Best Practices

1. **Start Conservative**: Use higher gating thresholds initially
2. **Monitor Performance**: Track T2 execution rates
3. **Tune Thresholds**: Adjust based on your content patterns
4. **Model Selection**: Use tiny/quantized models for production
5. **Fallback Testing**: Ensure pattern-based fallbacks work correctly

## Example Usage

```python
from heimdall_sdk import load_policy

# Load policy with ONNX guards
policy = load_policy("policies/enterprise_onnx_v1.yaml")

# Process request
context = {"messages": [{"role": "user", "content": "Hello world"}]}
result = await policy.compiled_guards["input"](context)
```

## Troubleshooting

### Model Loading Issues
```
❌ Failed to load ONNX model: Protobuf parsing failed
```
**Solution**: Ensure model files are valid ONNX format, not placeholder text files.

### Performance Issues
```
T2 guards running too frequently
```
**Solution**: Increase gating thresholds (`t1_score>0.8` instead of `t1_score>0.6`).

### Memory Usage
```
High memory consumption
```
**Solution**: Use quantized models or reduce model size.
