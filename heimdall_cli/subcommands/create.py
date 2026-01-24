"""
Create subcommands: guard, policy, pack

Scaffold new guards and policies with templates.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

CREATE_HELP = """
[bold cyan]🛠️  CREATE[/bold cyan] — Scaffold guards and policies

[dim]Generate new guards, policies, and packs from templates[/dim]

[bold yellow]Commands:[/bold yellow]
  [cyan]guard[/cyan]      Create a new guard from template
  [cyan]policy[/cyan]     Create a new policy YAML
  [cyan]pack[/cyan]       Create a guard pack structure

[bold]Examples:[/bold]
  [dim]# Create a PII guard (T0 tier)[/dim]
  $ heimdall create guard email_detector --type pii --tier T0

  [dim]# Create a toxicity guard (T2 tier)[/dim]
  $ heimdall create guard hate_speech --type toxicity --tier T2

  [dim]# Create a policy with guards[/dim]
  $ heimdall create policy enterprise -g pii.email,toxicity.hate

  [dim]# Create a guard pack[/dim]
  $ heimdall create pack compliance

[bold]Guard Types:[/bold]
  [cyan]pii[/cyan]         PII detection (email, SSN, phone, etc.)
  [cyan]toxicity[/cyan]    Toxicity and hate speech detection
  [cyan]schema[/cyan]      JSON schema validation
  [cyan]tools[/cyan]       Tool call validation
  [cyan]custom[/cyan]      Custom guard logic

[bold]Tiers:[/bold]
  [green]T0[/green]  Ultra-fast (<5ms)    - Regex, simple checks
  [yellow]T1[/yellow]  Fast (5-20ms)       - Heuristics, semantic
  [red]T2[/red]  Heavy (20ms+)      - ML models, ONNX
"""

app = typer.Typer(
    help=CREATE_HELP,
    no_args_is_help=True,
    rich_markup_mode="rich"
)


GUARD_TEMPLATE = '''"""
{description}
"""

from heimdall import guard, Guard, Ctx, Either, Left_, Right_, Violation
from typing import Dict, Any, List


@guard("{guard_id}", tier="{tier}", performance_budget_ms={budget_ms})
def {function_name}({params}) -> Guard:
    """
    {description}

    Args:
{param_docs}

    Returns:
        Guard function that checks context
    """
    async def check(ctx: Ctx) -> Either:
        violations: List[Violation] = []

        # TODO: Implement your guard logic here
        # Example: Extract data from context
        # text = ctx.get("output", "")

        # Example: Check condition
        # if should_block(text):
        #     violations.append(
        #         Violation(
        #             rule_id="{guard_id}",
        #             severity="high",
        #             message="Content blocked",
        #             score=0.8,
        #             tier="{tier}"
        #         )
        #     )

        if violations:
            return Left_(violations)

        return Right_(ctx)

    return check
'''

POLICY_TEMPLATE = '''# {policy_name}
# {description}

policy: {policy_id}
description: {description}

guards:
{guard_definitions}

compose:
  root: seq([{guard_sequence}])

thresholds:
  t0:
    gate_t1: 0.3
    gate_t2: 0.6
  t1:
    gate_t2: 0.4
'''

TIER_INFO = {
    "T0": {"budget_ms": 5.0, "description": "Ultra-fast (regex, simple checks)", "color": "green"},
    "T1": {"budget_ms": 20.0, "description": "Fast semantic (heuristics)", "color": "yellow"},
    "T2": {"budget_ms": 100.0, "description": "Heavy ML (ONNX models)", "color": "red"}
}

GUARD_TYPE_PARAMS = {
    "pii": {
        "params": "types: List[str], mode: str = 'mask'",
        "docs": "        types: List of PII types to detect (e.g., ['email', 'ssn'])\n        mode: Redaction mode ('mask' or 'hash')"
    },
    "toxicity": {
        "params": "threshold: float = 0.7, categories: Optional[List[str]] = None",
        "docs": "        threshold: Toxicity score threshold (0-1)\n        categories: Specific categories to check"
    },
    "schema": {
        "params": "schema: Dict[str, Any]",
        "docs": "        schema: JSON schema to validate against"
    },
    "tools": {
        "params": "allowed_tools: List[str], mode: str = 'whitelist'",
        "docs": "        allowed_tools: List of allowed tool names\n        mode: 'whitelist' or 'blacklist'"
    },
    "custom": {
        "params": "config: Dict[str, Any]",
        "docs": "        config: Custom configuration dictionary"
    }
}


@app.command()
def guard(
    name: str = typer.Argument(..., help="Guard name (e.g., 'email_detector')"),
    guard_type: str = typer.Option("custom", "--type", help="Guard category"),
    tier: str = typer.Option("T1", "--tier", help="Performance tier (T0/T1/T2)"),
    output: Path = typer.Option(Path("./guards"), "--output", "-o", help="Output directory"),
    description: str | None = typer.Option(None, "--description", "-d", help="Guard description"),
):
    """
    Create a new guard from template

    Examples:
        heimdall create guard email_detector --type pii --tier T0
        heimdall create guard hate_speech --type toxicity --tier T2
        heimdall create guard my_custom --type custom --tier T1 -o ./my_guards
    """
    # Validate tier
    if tier not in TIER_INFO:
        console.print(f"[red]✗[/red] Invalid tier '{tier}'. Must be T0, T1, or T2", style="bold")
        raise typer.Exit(1)

    # Validate type
    if guard_type not in GUARD_TYPE_PARAMS:
        console.print(f"[red]✗[/red] Invalid type '{guard_type}'", style="bold")
        console.print(f"Valid types: {', '.join(GUARD_TYPE_PARAMS.keys())}")
        raise typer.Exit(1)

    # Generate guard details
    guard_id = f"{guard_type}.{name}"
    function_name = f"{name}_guard"
    tier_info = TIER_INFO[tier]
    budget_ms = tier_info["budget_ms"]

    if description is None:
        description = f"{name.replace('_', ' ').title()} guard ({tier_info['description']})"

    # Get type-specific parameters
    type_params = GUARD_TYPE_PARAMS[guard_type]

    # Create output directory
    type_dir = output / guard_type
    type_dir.mkdir(parents=True, exist_ok=True)

    # Create guard file
    guard_file = type_dir / f"{name}.py"

    if guard_file.exists():
        console.print(f"[red]✗[/red] Guard file already exists: {guard_file}", style="bold")
        raise typer.Exit(1)

    # Generate guard content
    content = GUARD_TEMPLATE.format(
        guard_id=guard_id,
        function_name=function_name,
        description=description,
        tier=tier,
        budget_ms=budget_ms,
        params=type_params["params"],
        param_docs=type_params["docs"]
    )

    # Write guard file
    guard_file.write_text(content)

    # Create __init__.py if needed
    init_file = type_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Guard pack"""\n')

    # Display success
    console.print(f"[green]✓[/green] Created guard: {guard_file}", style="bold")
    console.print()
    console.print(Panel(
        f"[cyan]Guard ID:[/cyan] {guard_id}\n"
        f"[cyan]Tier:[/cyan] [{tier_info['color']}]{tier}[/{tier_info['color']}] ({tier_info['description']})\n"
        f"[cyan]Budget:[/cyan] {budget_ms}ms\n"
        f"[cyan]Type:[/cyan] {guard_type}",
        title="Guard Details",
        border_style="green"
    ))

    # Show next steps
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  1. Edit [cyan]{guard_file}[/cyan] and implement your logic")
    console.print(f"  2. Use in policy: [cyan]guards:\n    - id: {guard_id}[/cyan]")
    console.print(f"  3. Test with: [cyan]heimdall run test -g {guard_id}[/cyan]")

    # Show code preview
    console.print()
    console.print("[bold]Preview:[/bold]")
    syntax = Syntax(content[:400] + "\n    ...", "python", theme="monokai", line_numbers=False)
    console.print(syntax)


@app.command()
def policy(
    name: str = typer.Argument(..., help="Policy name (e.g., 'enterprise')"),
    guards: str = typer.Option(..., "--guards", "-g", help="Comma-separated guard IDs"),
    output: Path = typer.Option(Path("./policies"), "--output", "-o", help="Output directory"),
    description: str | None = typer.Option(None, "--description", "-d", help="Policy description"),
):
    """
    Create a new policy YAML

    Examples:
        heimdall create policy enterprise -g pii.email,toxicity.hate,schema.output
        heimdall create policy custom -g custom.my_guard -o ./my_policies
    """
    # Parse guards
    guard_list = [g.strip() for g in guards.split(",")]

    if not guard_list:
        console.print("[red]✗[/red] No guards specified", style="bold")
        raise typer.Exit(1)

    # Generate policy details
    policy_id = f"{name}_v1"

    if description is None:
        description = f"{name.title()} policy with {len(guard_list)} guards"

    # Generate guard definitions
    guard_defs = []
    for guard_id in guard_list:
        guard_defs.append(f"  - id: {guard_id}")

    guard_sequence = ", ".join([f'"{g}"' for g in guard_list])

    # Create output directory
    output.mkdir(parents=True, exist_ok=True)

    # Create policy file
    policy_file = output / f"{name}_v1.yaml"

    if policy_file.exists():
        console.print(f"[red]✗[/red] Policy file already exists: {policy_file}", style="bold")
        raise typer.Exit(1)

    # Generate policy content
    content = POLICY_TEMPLATE.format(
        policy_name=name.upper(),
        policy_id=policy_id,
        description=description,
        guard_definitions="\n".join(guard_defs),
        guard_sequence=guard_sequence
    )

    # Write policy file
    policy_file.write_text(content)

    # Display success
    console.print(f"[green]✓[/green] Created policy: {policy_file}", style="bold")
    console.print()
    console.print(Panel(
        f"[cyan]Policy ID:[/cyan] {policy_id}\n"
        f"[cyan]Guards:[/cyan] {len(guard_list)}\n"
        f"[cyan]Composition:[/cyan] sequential",
        title="Policy Details",
        border_style="green"
    ))

    # Show next steps
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  1. Edit [cyan]{policy_file}[/cyan] and customize composition")
    console.print(f"  2. Validate: [cyan]heimdall policy lint {policy_file}[/cyan]")
    console.print(f"  3. Compile: [cyan]heimdall policy compile -p {policy_file} -o build/{name}.json[/cyan]")


@app.command()
def pack(
    name: str = typer.Argument(..., help="Pack name (e.g., 'compliance')"),
    output: Path = typer.Option(Path("./guards"), "--output", "-o", help="Output directory"),
):
    """
    Create a new guard pack structure

    Example:
        heimdall create pack compliance
    """
    # Create pack directory
    pack_dir = output / name
    pack_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py
    init_file = pack_dir / "__init__.py"
    init_content = f'"""\n{name.title()} Guard Pack\n\nCollection of guards for {name} use cases.\n"""\n'
    init_file.write_text(init_content)

    # Create guards.py template
    guards_file = pack_dir / "guards.py"
    guards_content = f'''"""
{name.title()} Guards
"""

from heimdall import guard, Guard, Ctx, Either, Left_, Right_, Violation
from typing import Dict, Any, List


@guard("{name}.example", tier="T1", performance_budget_ms=20.0)
def example_guard(threshold: float = 0.7) -> Guard:
    """
    Example guard for {name} pack

    Args:
        threshold: Detection threshold

    Returns:
        Guard function
    """
    async def check(ctx: Ctx) -> Either:
        # TODO: Implement guard logic
        return Right_(ctx)

    return check
'''
    guards_file.write_text(guards_content)

    # Create README
    readme_file = pack_dir / "README.md"
    readme_content = f'''# {name.title()} Guard Pack

## Overview

Collection of guards for {name} use cases.

## Guards

- `{name}.example`: Example guard (T1)

## Usage

```yaml
guards:
  - id: {name}.example
    params:
      threshold: 0.7
```
'''
    readme_file.write_text(readme_content)

    # Display success
    console.print(f"[green]✓[/green] Created guard pack: {pack_dir}", style="bold")
    console.print()
    console.print(Panel(
        f"[cyan]Pack:[/cyan] {name}\n"
        f"[cyan]Location:[/cyan] {pack_dir}\n"
        f"[cyan]Files:[/cyan] __init__.py, guards.py, README.md",
        title="Pack Details",
        border_style="green"
    ))

    # Show next steps
    console.print("[bold]Next steps:[/bold]")
    console.print(f"  1. Edit [cyan]{guards_file}[/cyan] and add your guards")
    console.print(f"  2. Import guards: [cyan]import {name}.guards[/cyan]")
    console.print(f"  3. Document in [cyan]{readme_file}[/cyan]")

