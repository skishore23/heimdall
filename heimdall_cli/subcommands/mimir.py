"""
Mímir subcommands: push, pull, rollout (control-plane lite)

Note: Core Mímir functionality (compile/sign/verify) is in the 'policy' subcommand.
These commands are for future control-plane operations (storage, canary deployments, etc.)
"""

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Mímir control plane operations")


@app.command()
def push():
    """
    Push a policy envelope to storage

    Note: This is a placeholder for future control-plane integration.
    For now, distribute policy envelopes manually (S3, GCS, etc.)
    """
    console.print("[yellow]Mímir push not yet implemented[/yellow]")
    console.print("\nFor now:")
    console.print("  1. Compile policy: heimdall policy compile -p policy.yaml -o build/policy.json")
    console.print("  2. Upload to S3/GCS: aws s3 cp build/policy.json s3://bucket/policies/")
    console.print("  3. Reload gateway: heimdall bifrost reload build/policy.json")
    raise typer.Exit(0)


@app.command()
def pull():
    """
    Pull a policy envelope from storage

    Note: This is a placeholder for future control-plane integration.
    """
    console.print("[yellow]Mímir pull not yet implemented[/yellow]")
    console.print("\nFor now, download policies manually from your storage.")
    raise typer.Exit(0)


@app.command()
def rollout():
    """
    Manage canary rollouts and traffic splitting

    Note: This is a placeholder for future control-plane integration.
    """
    console.print("[yellow]Mímir rollout not yet implemented[/yellow]")
    console.print("\nFor canary deployments:")
    console.print("  1. Deploy new policy to subset of gateways")
    console.print("  2. Monitor metrics")
    console.print("  3. Gradually roll out to all gateways")
    raise typer.Exit(0)

