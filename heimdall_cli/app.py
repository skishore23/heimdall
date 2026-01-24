"""
Heimdall CLI - Main application entry point
"""

import sys

import typer
from rich.console import Console

from heimdall_cli import __version__
from heimdall_cli.subcommands import (
    bifrost,
    create,
    dev,
    doctor,
    eval,
    guards,
    mimir,
    models,
    policy,
    run,
)

console = Console()

# Rich help text
HELP_TEXT = """
[bold cyan]⚔️  HEIMDALL[/bold cyan] — Guardian of the Nine Realms

[dim]Composable guard algebra for LLM applications with three-tier execution (T0/T1/T2)[/dim]

[bold yellow]Guard Discovery:[/bold yellow]
  [cyan]guards list[/cyan]      List all available guards
  [cyan]guards info[/cyan]      Show detailed guard information
  [cyan]guards search[/cyan]    Search guards by name/description

[bold yellow]Guard Creation & Management:[/bold yellow]
  [cyan]create guard[/cyan]     Generate a new guard from template
  [cyan]create policy[/cyan]    Generate a new policy YAML
  [cyan]create pack[/cyan]      Create a guard pack structure

[bold yellow]Policy Operations:[/bold yellow]
  [cyan]policy lint[/cyan]      Validate policy YAML schema
  [cyan]policy compile[/cyan]   Compile policy to signed envelope
  [cyan]policy verify[/cyan]    Verify policy signature
  [cyan]policy graph[/cyan]     Export policy composition graph

[bold yellow]Runtime & Testing:[/bold yellow]
  [cyan]run test[/cyan]         Run guards locally (SDK mode)
  [cyan]eval run[/cyan]         Run evaluation harness
  [cyan]dev[/cyan]              Launch interactive TUI dashboard

[bold yellow]Gateway Control:[/bold yellow]
  [cyan]bifrost status[/cyan]   Check gateway health
  [cyan]bifrost reload[/cyan]   Hot-reload policy
  [cyan]bifrost trace[/cyan]    View decision traces

[bold yellow]System:[/bold yellow]
  [cyan]models list[/cyan]      List available ONNX models
  [cyan]doctor[/cyan]           Environment diagnostics
  [cyan]version[/cyan]          Show version information

[bold]Examples:[/bold]
  [dim]# Create a new PII guard[/dim]
  $ heimdall create guard email_detector --type pii --tier T0

  [dim]# Create a policy with multiple guards[/dim]
  $ heimdall create policy enterprise -g pii.email,toxicity.hate

  [dim]# Launch development dashboard[/dim]
  $ heimdall dev

  [dim]# Compile and deploy policy[/dim]
  $ heimdall policy compile -p my_policy.yaml -o build/policy.json
  $ heimdall bifrost reload build/policy.json

[bold]Documentation:[/bold] https://docs.heimdall.ai
[bold]Repository:[/bold] https://github.com/heimdall-ai/heimdall
"""

app = typer.Typer(
    name="heimdall",
    help=HELP_TEXT,
    add_completion=True,
    rich_markup_mode="rich",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)

# Add subcommands
app.add_typer(
    create.app,
    name="create",
    help="🛠️  [cyan]Create[/cyan] guards, policies, and packs from templates"
)
app.add_typer(
    guards.app,
    name="guards",
    help="🛡️  [cyan]Guards[/cyan] discovery (list, info, search)"
)
app.add_typer(
    policy.app,
    name="policy",
    help="📜 [cyan]Policy[/cyan] management (lint, compile, verify, graph)"
)
app.add_typer(
    run.app,
    name="run",
    help="🏃 [cyan]Run[/cyan] guards locally in SDK mode"
)
app.add_typer(
    eval.app,
    name="eval",
    help="📊 [cyan]Evaluate[/cyan] guards with test harness"
)
app.add_typer(
    bifrost.app,
    name="bifrost",
    help="🌉 [cyan]Bifröst[/cyan] gateway control (status, reload, trace)"
)
app.add_typer(
    mimir.app,
    name="mimir",
    help="🔐 [cyan]Mímir[/cyan] policy signing and verification"
)
app.add_typer(
    models.app,
    name="models",
    help="🤖 [cyan]Models[/cyan] ONNX model management"
)
app.command(
    name="doctor",
    help="🏥 [cyan]Doctor[/cyan] — Environment diagnostics and health check"
)(doctor.doctor_command)
app.command(
    name="dev",
    help="⚡ [cyan]Dev[/cyan] — Launch interactive TUI dashboard"
)(dev.dev_command)


@app.command()
def version():
    """⚔️  Show version information and installed components"""
    from rich.panel import Panel
    from rich.table import Table

    # Create version table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan bold")
    table.add_column(style="white")

    table.add_row("Version", f"[bold]{__version__}[/bold]")
    table.add_row("Python", f"{sys.version.split()[0]}")

    # Check components
    components = []
    try:
        import onnxruntime
        components.append(("✓ ONNX Runtime", f"[green]{onnxruntime.__version__}[/green]"))
    except ImportError:
        components.append(("✗ ONNX Runtime", "[dim]not installed[/dim]"))

    try:
        import textual
        components.append(("✓ Textual TUI", f"[green]{textual.__version__}[/green]"))
    except ImportError:
        components.append(("✗ Textual TUI", "[dim]not installed[/dim]"))

    try:
        import httpx
        components.append(("✓ HTTP Client", f"[green]{httpx.__version__}[/green]"))
    except ImportError:
        components.append(("✗ HTTP Client", "[dim]not installed[/dim]"))

    console.print()
    console.print(Panel(
        table,
        title="[bold cyan]⚔️  HEIMDALL[/bold cyan]",
        subtitle="Guardian of the Nine Realms",
        border_style="cyan"
    ))

    # Show components
    if components:
        console.print("\n[bold]Components:[/bold]")
        for name, ver in components:
            console.print(f"  {name}: {ver}")

    console.print()
    console.print("[dim]Heimdall Engine • Bifröst Gateway • Mímir Control Plane[/dim]")
    console.print()

    raise typer.Exit(0)


@app.command()
def completion(
    shell: str = typer.Argument("bash", help="Shell type (bash, zsh, fish)")
):
    """
    Generate shell completion script

    Usage:
        # Bash
        heimdall completion bash > ~/.local/share/bash-completion/completions/heimdall

        # Zsh
        heimdall completion zsh > ~/.zfunc/_heimdall

        # Fish
        heimdall completion fish > ~/.config/fish/completions/heimdall.fish
    """
    import subprocess

    # Typer has built-in completion support
    if shell in ["bash", "zsh", "fish"]:
        # Use typer's built-in completion
        try:
            result = subprocess.run(
                [sys.executable, "-m", "typer", "heimdall_cli.app", "utils", "completion", shell],
                capture_output=True,
                text=True
            )
            print(result.stdout)
        except Exception as e:
            console.print(f"[red]✗[/red] Completion generation failed: {e}", style="bold")
            console.print("\nManual setup:")
            console.print(f"  Run: typer heimdall_cli.app utils completion {shell}")
            raise typer.Exit(1)
    else:
        console.print(f"[red]✗[/red] Unknown shell: {shell}", style="bold")
        console.print("Supported shells: bash, zsh, fish")
        raise typer.Exit(1)

    raise typer.Exit(0)


def main() -> None:
    """Main CLI entry point"""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]✗[/red] Unexpected error: {e}", style="bold")
        sys.exit(1)


if __name__ == "__main__":
    main()

