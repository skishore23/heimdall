"""
Models subcommands: list, info, verify, warmup
"""

import hashlib
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from heimdall_cli.config import load_config

console = Console()
app = typer.Typer(help="ONNX model management")


def find_onnx_models(models_dir: Path) -> list[Path]:
    """Find all ONNX models in directory"""
    # Convert to Path if it's a string
    if isinstance(models_dir, str):
        models_dir = Path(models_dir)

    if not models_dir.exists():
        return []

    return list(models_dir.glob("*.onnx"))


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of file"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


@app.command(name="list")
def list_models(
    models_dir: Path | None = typer.Option(None, "--models-dir", help="Models directory"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    List ONNX models in models directory
    """
    import json
    import sys

    try:
        # Load config
        config = load_config()

        if models_dir is None:
            models_dir = Path(config.models_dir)
        elif not isinstance(models_dir, Path):
            models_dir = Path(models_dir)

        # Find models
        models = find_onnx_models(models_dir)
    except Exception as e:
        if json_output:
            result = {"status": "error", "error": str(e)}
            print(json.dumps(result, indent=2))
        else:
            console.print(f"[red]✗[/red] Unexpected error: {e}", style="bold")
            import traceback
            traceback.print_exc()
        sys.exit(1)

    if not models:
        console.print(f"[yellow]No ONNX models found in {models_dir}[/yellow]")
        raise typer.Exit(0)

    if json_output:
        result = {
            "models_dir": str(models_dir),
            "models": [
                {
                    "name": model.name,
                    "path": str(model),
                    "size_mb": round(model.stat().st_size / 1024 / 1024, 2)
                }
                for model in models
            ],
            "count": len(models)
        }
        print(json.dumps(result, indent=2))
    else:
        table = Table(title=f"ONNX Models ({len(models)})")
        table.add_column("Model", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Path", style="dim")

        for model in sorted(models, key=lambda m: m.name):
            size_mb = model.stat().st_size / 1024 / 1024
            table.add_row(
                model.name,
                f"{size_mb:.2f} MB",
                str(model)
            )

        console.print(table)

    raise typer.Exit(0)


@app.command()
def info(
    model: Path = typer.Argument(..., help="Path to ONNX model"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Show detailed information about an ONNX model
    """
    import json

    if not model.exists():
        console.print(f"[red]✗[/red] Model not found: {model}", style="bold")
        raise typer.Exit(6)

    # Compute hash
    sha256 = compute_sha256(model)
    size_mb = model.stat().st_size / 1024 / 1024

    # Try to load model metadata
    try:
        import onnxruntime as ort

        session = ort.InferenceSession(str(model), providers=['CPUExecutionProvider'])

        inputs = [
            {
                "name": inp.name,
                "type": str(inp.type),
                "shape": str(inp.shape)
            }
            for inp in session.get_inputs()
        ]

        outputs = [
            {
                "name": out.name,
                "type": str(out.type),
                "shape": str(out.shape)
            }
            for out in session.get_outputs()
        ]

        metadata = {
            "inputs": inputs,
            "outputs": outputs,
            "providers": ort.get_available_providers()
        }

    except ImportError:
        metadata = {"error": "onnxruntime not installed"}
    except Exception as e:
        metadata = {"error": str(e)}

    if json_output:
        result = {
            "name": model.name,
            "path": str(model),
            "size_mb": round(size_mb, 2),
            "sha256": sha256,
            "metadata": metadata
        }
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[cyan]{model.name}[/cyan]", style="bold")
        console.print(f"  Path: {model}")
        console.print(f"  Size: {size_mb:.2f} MB")
        console.print(f"  SHA256: {sha256}")

        if "error" not in metadata:
            console.print(f"  Inputs: {len(metadata['inputs'])}")
            console.print(f"  Outputs: {len(metadata['outputs'])}")
            console.print(f"  Providers: {', '.join(metadata['providers'])}")

    raise typer.Exit(0)


@app.command()
def verify(
    model: Path = typer.Argument(..., help="Path to ONNX model"),
    expected_sha256: str | None = typer.Option(None, "--sha256", help="Expected SHA256 hash"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Verify ONNX model checksum and validity
    """
    import json

    if not model.exists():
        console.print(f"[red]✗[/red] Model not found: {model}", style="bold")
        raise typer.Exit(6)

    # Compute hash
    actual_sha256 = compute_sha256(model)

    # Verify hash if provided
    hash_match = None
    if expected_sha256:
        hash_match = actual_sha256 == expected_sha256

        if not hash_match:
            if json_output:
                result = {
                    "status": "invalid",
                    "reason": "checksum_mismatch",
                    "expected": expected_sha256,
                    "actual": actual_sha256
                }
                print(json.dumps(result, indent=2))
            else:
                console.print("[red]✗[/red] Checksum mismatch", style="bold")
                console.print(f"  Expected: {expected_sha256}")
                console.print(f"  Actual: {actual_sha256}")

            raise typer.Exit(6)

    # Try to load model
    try:
        import onnxruntime as ort

        ort.InferenceSession(str(model), providers=['CPUExecutionProvider'])

    except ImportError:
        if json_output:
            result = {
                "status": "unknown",
                "reason": "onnxruntime_not_installed"
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[yellow]⚠[/yellow] Cannot verify: onnxruntime not installed")

        raise typer.Exit(0)

    except Exception as e:
        if json_output:
            result = {
                "status": "invalid",
                "reason": "load_failed",
                "error": str(e)
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[red]✗[/red] Model load failed:", style="bold")
            console.print(f"  {str(e)}", style="red")

        raise typer.Exit(6)

    # Success
    if json_output:
        result = {
            "status": "valid",
            "sha256": actual_sha256,
            "checksum_verified": hash_match
        }
        print(json.dumps(result, indent=2))
    else:
        console.print("[green]✓[/green] Model is valid", style="bold")
        console.print(f"  SHA256: {actual_sha256}")
        if hash_match is not None:
            console.print(f"  Checksum: {'✓ Verified' if hash_match else '✗ Mismatch'}")

    raise typer.Exit(0)


@app.command()
def warmup(
    model: Path = typer.Argument(..., help="Path to ONNX model"),
    provider: str = typer.Option("CPU", "--provider", help="Execution provider (CPU, CUDA)"),
    quant: str = typer.Option("fp32", "--quant", help="Quantization (fp32, fp16, int8)"),
    iterations: int = typer.Option(10, "--iterations", "-n", help="Number of warmup iterations"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Warm up ONNX model and measure performance

    Runs N iterations to:
    - Load model
    - Execute inference
    - Measure latency (P50, P95, P99)
    """
    import json

    import numpy as np

    if not model.exists():
        console.print(f"[red]✗[/red] Model not found: {model}", style="bold")
        raise typer.Exit(6)

    try:
        import onnxruntime as ort
    except ImportError:
        console.print("[red]✗[/red] onnxruntime not installed", style="bold")
        console.print("  Install with: pip install onnxruntime")
        raise typer.Exit(6)

    # Map provider name
    provider_map = {
        "CPU": "CPUExecutionProvider",
        "CUDA": "CUDAExecutionProvider"
    }

    provider_name = provider_map.get(provider.upper())
    if not provider_name:
        console.print(f"[red]✗[/red] Unknown provider: {provider}", style="bold")
        raise typer.Exit(6)

    # Check provider availability
    available_providers = ort.get_available_providers()
    if provider_name not in available_providers:
        console.print(f"[red]✗[/red] Provider not available: {provider_name}", style="bold")
        console.print(f"  Available: {', '.join(available_providers)}")
        raise typer.Exit(6)

    if not json_output:
        console.print(f"[blue]→[/blue] Loading model: {model.name}")
        console.print(f"[blue]→[/blue] Provider: {provider_name}")
        console.print(f"[blue]→[/blue] Quantization: {quant}")

    # Load model
    load_start = time.time()
    session = ort.InferenceSession(str(model), providers=[provider_name])
    load_time_ms = (time.time() - load_start) * 1000

    # Get input shape
    input_info = session.get_inputs()[0]

    # Generate dummy input
    # Simplified: assume text model with shape [batch, seq_len]
    dummy_input = np.random.randint(0, 1000, size=(1, 128)).astype(np.int64)

    # Warmup runs
    latencies = []

    for _i in range(iterations):
        start = time.time()
        try:
            session.run(None, {input_info.name: dummy_input})
            latency_ms = (time.time() - start) * 1000
            latencies.append(latency_ms)
        except Exception as e:
            console.print(f"[red]✗[/red] Inference failed: {e}", style="bold")
            raise typer.Exit(6)

    # Compute percentiles
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2]
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
    p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
    mean = sum(latencies) / len(latencies)

    if json_output:
        result = {
            "model": model.name,
            "provider": provider_name,
            "quantization": quant,
            "load_time_ms": round(load_time_ms, 2),
            "iterations": iterations,
            "latency_ms": {
                "mean": round(mean, 2),
                "p50": round(p50, 2),
                "p95": round(p95, 2),
                "p99": round(p99, 2)
            }
        }
        print(json.dumps(result, indent=2))
    else:
        console.print("[green]✓[/green] Warmup complete", style="bold")
        console.print(f"  Load time: {load_time_ms:.2f} ms")
        console.print(f"  Iterations: {iterations}")
        console.print("  Latency (ms):")
        console.print(f"    Mean: {mean:.2f}")
        console.print(f"    P50:  {p50:.2f}")
        console.print(f"    P95:  {p95:.2f}")
        console.print(f"    P99:  {p99:.2f}")

    raise typer.Exit(0)

