"""
Guards subcommands: list, info, search
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from heimdall.registry import (
    get_guard_metadata,
    get_guards_by_tier,
    get_onnx_guards,
    get_registry,
)

console = Console()
app = typer.Typer(help="Guard discovery and information")


@app.command()
def list(
    tier: str = typer.Option(None, "--tier", "-t", help="Filter by tier (T0, T1, T2)"),
    onnx: bool = typer.Option(False, "--onnx", help="Show only ONNX guards"),
    category: str = typer.Option(None, "--category", "-c", help="Filter by category"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    List all available guards

    Examples:
        # List all guards
        heimdall guards list

        # List only T0 (fast) guards
        heimdall guards list --tier T0

        # List ONNX guards
        heimdall guards list --onnx

        # JSON output
        heimdall guards list --json
    """
    # Import guards to populate registry
    import heimdall  # noqa
    import guards  # noqa

    # Filter guards
    if tier:
        guard_dict = get_guards_by_tier(tier)
    elif onnx:
        guard_dict = get_onnx_guards(category=category)
    else:
        guard_dict = get_registry()

    if not guard_dict:
        console.print("[yellow]No guards found matching criteria[/yellow]")
        raise typer.Exit(0)

    if json_output:
        import json
        output = {
            guard_id: {
                "tier": metadata.tier,
                "description": metadata.description,
                "performance_budget_ms": metadata.performance_budget_ms,
                "requires_onnx": metadata.requires_onnx,
                "onnx_category": metadata.onnx_category
            }
            for guard_id, metadata in guard_dict.items()
        }
        print(json.dumps(output, indent=2))
        raise typer.Exit(0)

    # Display as table
    table = Table(title=f"Available Guards ({len(guard_dict)})")
    table.add_column("Guard ID", style="cyan", no_wrap=True)
    table.add_column("Tier", style="green")
    table.add_column("Budget (ms)", justify="right")
    table.add_column("Type", style="magenta")
    table.add_column("Description", style="white")

    for guard_id, metadata in sorted(guard_dict.items()):
        tier_str = metadata.tier or "?"
        budget_str = f"{metadata.performance_budget_ms:.1f}" if metadata.performance_budget_ms else "-"
        type_str = "ONNX" if metadata.requires_onnx else "Rule"
        description = metadata.description or "-"

        table.add_row(
            guard_id,
            tier_str,
            budget_str,
            type_str,
            description[:60] + "..." if len(description) > 60 else description
        )

    console.print(table)
    console.print("\n[dim]Use 'heimdall guards info <guard-id>' for details[/dim]")


@app.command()
def info(
    guard_id: str = typer.Argument(..., help="Guard ID to inspect")
):
    """
    Show detailed information about a guard

    Example:
        heimdall guards info pii.email
    """
    # Import guards to populate registry
    import heimdall  # noqa
    import guards  # noqa

    try:
        metadata = get_guard_metadata(guard_id)
    except KeyError:
        console.print(f"[red]✗[/red] Guard '{guard_id}' not found", style="bold")
        console.print("\nUse 'heimdall guards list' to see available guards")
        raise typer.Exit(1)

    # Display guard info
    console.print()
    console.print(Panel(
        f"[bold]{guard_id}[/bold]",
        title="Guard Information",
        border_style="cyan"
    ))

    console.print(f"[bold]Tier:[/bold] {metadata.tier or 'Not specified'}")
    console.print(f"[bold]Performance Budget:[/bold] {metadata.performance_budget_ms or 'Not specified'} ms")
    console.print(f"[bold]Type:[/bold] {'ONNX Model' if metadata.requires_onnx else 'Rule-based'}")

    if metadata.requires_onnx:
        console.print(f"[bold]ONNX Model:[/bold] {metadata.onnx_model_id or 'Not specified'}")
        console.print(f"[bold]Category:[/bold] {metadata.onnx_category or 'Not specified'}")

    console.print("\n[bold]Description:[/bold]")
    console.print(f"  {metadata.description or 'No description available'}")

    # Usage example
    console.print("\n[bold]Usage in Policy:[/bold]")
    console.print(f"""
[dim]guards:
  - id: {guard_id}
    target: messages[*].content

compose:
  root: seq([{guard_id.split('.')[-1]}])
[/dim]""")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Search guards by name or description

    Example:
        heimdall guards search pii
        heimdall guards search "detect email"
    """
    # Import guards to populate registry
    import heimdall  # noqa
    import guards  # noqa

    query_lower = query.lower()
    matches = {}

    for guard_id, metadata in get_registry().items():
        if query_lower in guard_id.lower():
            matches[guard_id] = metadata
        elif metadata.description and query_lower in metadata.description.lower():
            matches[guard_id] = metadata

    if not matches:
        console.print(f"[yellow]No guards found matching '{query}'[/yellow]")
        raise typer.Exit(0)

    if json_output:
        import json
        output = {
            guard_id: {
                "tier": metadata.tier,
                "description": metadata.description,
                "performance_budget_ms": metadata.performance_budget_ms
            }
            for guard_id, metadata in matches.items()
        }
        print(json.dumps(output, indent=2))
        raise typer.Exit(0)

    console.print(f"\n[bold]Found {len(matches)} guards matching '{query}':[/bold]\n")

    for guard_id, metadata in sorted(matches.items()):
        console.print(f"  [cyan]{guard_id}[/cyan]")
        if metadata.description:
            console.print(f"    {metadata.description}")
        console.print()


@app.command()
def tiers():
    """
    Explain guard performance tiers
    """
    console.print()
    console.print(Panel(
        """
[bold]T0 - Ultra Fast (< 5ms)[/bold]
• Regex patterns, simple rules
• Runs on every request
• Examples: banned words, format validation

[bold]T1 - Fast (5-20ms)[/bold]
• Heuristics, pattern matching
• Gated by T0 results
• Examples: PII detection, complexity checks

[bold]T2 - ML Models (20ms+)[/bold]
• ONNX models, external APIs
• Gated by T1 results
• Examples: toxicity detection, fact-checking
        """,
        title="Heimdall Performance Tiers",
        border_style="green"
    ))
    console.print("[dim]Tiers enable fast guards to gate slow guards[/dim]\n")

