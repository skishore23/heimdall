"""
Doctor command: Environment diagnostics
"""

import os
import platform
import sys
from typing import Any

import typer
from rich.console import Console

console = Console()


def check_python_version() -> dict[str, Any]:
    """Check Python version"""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    is_ok = version.major == 3 and version.minor >= 10

    return {
        "name": "Python Version",
        "status": "ok" if is_ok else "warning",
        "value": version_str,
        "message": "OK" if is_ok else "Recommend Python 3.10-3.12"
    }


def check_dependencies() -> list[dict[str, Any]]:
    """Check key dependencies"""
    results = []

    # Required dependencies
    required = [
        ("pydantic", "Pydantic"),
        ("yaml", "PyYAML"),
        ("typer", "Typer"),
        ("rich", "Rich"),
    ]

    for module_name, display_name in required:
        try:
            __import__(module_name)
            results.append({
                "name": display_name,
                "status": "ok",
                "value": "✓ Installed",
                "message": ""
            })
        except ImportError:
            results.append({
                "name": display_name,
                "status": "error",
                "value": "✗ Missing",
                "message": f"Install with: pip install {module_name}"
            })

    # Optional dependencies
    optional = [
        ("onnxruntime", "ONNX Runtime (CPU)", "pip install onnxruntime"),
        ("textual", "Textual (TUI)", "pip install textual"),
        ("httpx", "httpx (Bifröst client)", "pip install httpx"),
    ]

    for module_name, display_name, install_cmd in optional:
        try:
            __import__(module_name)
            results.append({
                "name": display_name,
                "status": "ok",
                "value": "✓ Installed",
                "message": ""
            })
        except ImportError:
            results.append({
                "name": display_name,
                "status": "info",
                "value": "○ Optional",
                "message": install_cmd
            })

    return results


def check_environment_variables() -> list[dict[str, Any]]:
    """Check environment variables"""
    results = []

    # Check API keys
    env_vars = [
        ("OPENAI_API_KEY", "OpenAI API Key", "Required for OpenAI models"),
        ("ANTHROPIC_API_KEY", "Anthropic API Key", "Required for Claude models"),
        ("HEIMDALL_BIFROST_URL", "Bifröst URL", "Optional, defaults to localhost:8080"),
    ]

    for var_name, display_name, description in env_vars:
        value = os.getenv(var_name)

        if value:
            # Mask sensitive values
            masked = value[:10] + "..." if len(value) > 10 else value
            results.append({
                "name": display_name,
                "status": "ok",
                "value": masked,
                "message": description
            })
        else:
            results.append({
                "name": display_name,
                "status": "info",
                "value": "Not set",
                "message": description
            })

    return results


def check_onnx_providers() -> dict[str, Any]:
    """Check ONNX execution providers"""
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        has_gpu = 'CUDAExecutionProvider' in providers

        return {
            "name": "ONNX Providers",
            "status": "ok",
            "value": ", ".join(providers),
            "message": f"GPU: {'✓' if has_gpu else '✗'}"
        }
    except ImportError:
        return {
            "name": "ONNX Providers",
            "status": "warning",
            "value": "N/A",
            "message": "onnxruntime not installed"
        }


def check_directories() -> list[dict[str, Any]]:
    """Check expected directories"""
    from heimdall_cli.config import HeimdallConfig

    config = HeimdallConfig()
    results = []

    dirs = [
        (config.policies_dir, "Policies"),
        (config.build_dir, "Build"),
        (config.models_dir, "Models"),
    ]

    for dir_path, name in dirs:
        exists = dir_path.exists()
        results.append({
            "name": f"{name} Directory",
            "status": "ok" if exists else "info",
            "value": str(dir_path),
            "message": "Exists" if exists else "Not found (will be created as needed)"
        })

    return results


def doctor_command(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Run environment diagnostics

    Checks:
    - Python version
    - Dependencies
    - Environment variables
    - ONNX providers
    - Directory structure
    """
    import json

    # Collect diagnostics
    diagnostics = {
        "system": {
            "platform": platform.platform(),
            "python": check_python_version(),
        },
        "dependencies": check_dependencies(),
        "environment": check_environment_variables(),
        "onnx": check_onnx_providers(),
        "directories": check_directories(),
    }

    if json_output:
        print(json.dumps(diagnostics, indent=2))
        raise typer.Exit(0)

    # Pretty print
    console.print("[bold]Heimdall Environment Diagnostics[/bold]\n")

    # System info
    console.print("[bold]System:[/bold]")
    console.print(f"  Platform: {diagnostics['system']['platform']}")
    py = diagnostics['system']['python']
    status_color = {"ok": "green", "warning": "yellow", "error": "red"}[py['status']]
    console.print(f"  Python: [{status_color}]{py['value']}[/{status_color}] {py['message']}")

    # Dependencies
    console.print("\n[bold]Dependencies:[/bold]")
    for dep in diagnostics['dependencies']:
        status_color = {"ok": "green", "warning": "yellow", "error": "red", "info": "dim"}[dep['status']]
        console.print(f"  {dep['name']:25} [{status_color}]{dep['value']:15}[/{status_color}] {dep['message']}")

    # Environment
    console.print("\n[bold]Environment Variables:[/bold]")
    for env in diagnostics['environment']:
        status_color = {"ok": "green", "info": "dim"}[env['status']]
        console.print(f"  {env['name']:25} [{status_color}]{env['value']:20}[/{status_color}]")
        if env['message']:
            console.print(f"    [dim]{env['message']}[/dim]")

    # ONNX
    onnx = diagnostics['onnx']
    status_color = {"ok": "green", "warning": "yellow"}[onnx['status']]
    console.print("\n[bold]ONNX:[/bold]")
    console.print(f"  {onnx['name']:25} [{status_color}]{onnx['value']}[/{status_color}]")
    if onnx['message']:
        console.print(f"    {onnx['message']}")

    # Directories
    console.print("\n[bold]Directories:[/bold]")
    for dir_info in diagnostics['directories']:
        status_color = {"ok": "green", "info": "dim"}[dir_info['status']]
        console.print(f"  {dir_info['name']:25} [{status_color}]{dir_info['message']}[/{status_color}]")
        console.print(f"    [dim]{dir_info['value']}[/dim]")

    # Summary
    has_errors = any(
        d['status'] == 'error'
        for d in diagnostics['dependencies']
    )

    console.print()
    if has_errors:
        console.print("[red]✗[/red] Some dependencies are missing", style="bold")
        raise typer.Exit(1)
    else:
        console.print("[green]✓[/green] Environment looks good!", style="bold")
        raise typer.Exit(0)

