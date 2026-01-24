"""
Policy subcommands: lint, compile, verify, graph, diff, fmt
"""

import json
import sys
from pathlib import Path

import typer
import yaml
from rich.console import Console

from heimdall.compiler import compile_policy
from heimdall.mimir import (
    PolicyEnvelope,
    compile_and_sign_policy,
    generate_signing_keypair,
    verify_policy_signature,
)

console = Console()
app = typer.Typer(help="Policy management commands")


def load_yaml_file(path: Path) -> bytes:
    """Load YAML file as bytes"""
    if not path.exists():
        console.print(f"[red]✗[/red] Policy file not found: {path}", style="bold")
        sys.exit(2)

    return path.read_bytes()


@app.command()
def lint(
    policy: Path = typer.Argument(..., help="Path to policy YAML file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Validate policy YAML schema and guard composition

    Checks:
    - YAML syntax
    - Schema validity
    - Guard IDs exist in registry
    - Composition syntax
    """
    try:
        # Import guard packs to register them
        import guards  # noqa: F401

        # Load and compile policy
        yaml_bytes = load_yaml_file(policy)
        compiled_guards, policy_metadata = compile_policy(yaml_bytes)

        # Extract info
        policy_id = policy_metadata.get('policy', 'unknown')
        guards_count = len(policy_metadata.get('guards', []))

        if json_output:
            result = {
                "status": "valid",
                "policy_id": policy_id,
                "guards_count": guards_count,
                "metadata": policy_metadata
            }
            print(json.dumps(result, indent=2))
        else:
            console.print(f"[green]✓[/green] Policy '{policy_id}' is valid", style="bold")
            console.print(f"  Guards: {guards_count}")
            console.print(f"  Path: {policy}")

        sys.exit(0)

    except Exception as e:
        if json_output:
            result = {
                "status": "invalid",
                "error": str(e)
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[red]✗[/red] Policy validation failed:", style="bold")
            console.print(f"  {str(e)}", style="red")

        sys.exit(2)


@app.command()
def compile(
    policy: Path = typer.Option(..., "-p", "--policy", help="Path to policy YAML file"),
    output: Path = typer.Option(..., "-o", "--output", help="Output path for compiled envelope"),
    signing_key: str | None = typer.Option(None, "--signing-key", help="Ed25519 signing key (base64)"),
    version: str | None = typer.Option(None, "--version", help="Policy version tag"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Compile policy YAML to signed envelope

    Produces a signed JSON envelope containing:
    - Compiled guard graph
    - Policy metadata
    - Ed25519 signature (if signing key provided)
    """
    try:
        # Import guard packs
        import guards  # noqa: F401

        # Load policy YAML
        yaml_bytes = load_yaml_file(policy)

        # Parse YAML to get policy ID
        policy_data = yaml.safe_load(yaml_bytes)
        policy_id = policy_data.get('policy', policy.stem)

        # Compile and sign
        if signing_key:
            signing_key_bytes = signing_key.encode('utf-8')
            envelope = compile_and_sign_policy(
                yaml_bytes=yaml_bytes,
                policy_id=policy_id,
                signing_key=signing_key_bytes,
                version=version
            )
        else:
            # Compile without signing
            compiled_guards, policy_metadata = compile_policy(yaml_bytes)

            # Create unsigned envelope
            envelope_data = {
                'policy_id': policy_id,
                'version': version or 'unsigned',
                'compiled_graph': {phase: f"<compiled_guard_{phase}>" for phase in compiled_guards.keys()},
                'thresholds': policy_metadata.get('thresholds', {}),
                'models': [],
                'signing': {'alg': 'none'}
            }
            envelope = PolicyEnvelope(**envelope_data)

        # Ensure output directory exists
        output.parent.mkdir(parents=True, exist_ok=True)

        # Write envelope
        output.write_text(envelope.to_json())

        if json_output:
            result = {
                "status": "compiled",
                "policy_id": envelope.policy_id,
                "version": envelope.version,
                "output": str(output),
                "signed": bool(signing_key)
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[green]✓[/green] Policy compiled successfully", style="bold")
            console.print(f"  Policy ID: {envelope.policy_id}")
            console.print(f"  Version: {envelope.version}")
            console.print(f"  Output: {output}")
            console.print(f"  Signed: {'Yes' if signing_key else 'No'}")

        sys.exit(0)

    except Exception as e:
        if json_output:
            result = {
                "status": "error",
                "error": str(e)
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[red]✗[/red] Compilation failed:", style="bold")
            console.print(f"  {str(e)}", style="red")

        sys.exit(2)


@app.command()
def verify(
    envelope: Path = typer.Argument(..., help="Path to policy envelope JSON"),
    verify_key: str | None = typer.Option(None, "--verify-key", help="Ed25519 verify key (base64)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Verify policy envelope signature and schema

    Checks:
    - JSON schema validity
    - Signature verification (if verify key provided)
    - Envelope integrity
    """
    try:
        # Load envelope
        if not envelope.exists():
            raise FileNotFoundError(f"Envelope not found: {envelope}")

        envelope_json = envelope.read_text()
        envelope_data = json.loads(envelope_json)
        envelope_obj = PolicyEnvelope(**envelope_data)

        # Verify signature if key provided
        signature_valid = None
        if verify_key and envelope_obj.signing.get('alg') != 'none':
            verify_key_bytes = verify_key.encode('utf-8')
            signature_valid = verify_policy_signature(envelope_obj, verify_key_bytes)

            if not signature_valid:
                if json_output:
                    result = {
                        "status": "invalid",
                        "reason": "signature_verification_failed"
                    }
                    print(json.dumps(result, indent=2))
                else:
                    console.print("[red]✗[/red] Signature verification failed", style="bold")

                sys.exit(2)

        if json_output:
            result = {
                "status": "valid",
                "policy_id": envelope_obj.policy_id,
                "version": envelope_obj.version,
                "signature_verified": signature_valid
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[green]✓[/green] Envelope is valid", style="bold")
            console.print(f"  Policy ID: {envelope_obj.policy_id}")
            console.print(f"  Version: {envelope_obj.version}")
            if signature_valid is not None:
                console.print(f"  Signature: {'✓ Valid' if signature_valid else '✗ Invalid'}")

        sys.exit(0)

    except Exception as e:
        if json_output:
            result = {
                "status": "error",
                "error": str(e)
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[red]✗[/red] Verification failed:", style="bold")
            console.print(f"  {str(e)}", style="red")

        sys.exit(2)


@app.command()
def graph(
    policy: Path = typer.Argument(..., help="Path to policy YAML file"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Output file (default: stdout)"),
    format: str = typer.Option("json", "-f", "--format", help="Output format: json, dot, or png")
):
    """
    Export policy composition graph

    Formats:
    - json: JSON graph structure
    - dot: Graphviz DOT format
    - png: PNG image (requires graphviz)
    """
    try:
        # Import guard packs
        import guards  # noqa: F401

        # Load and compile policy
        yaml_bytes = load_yaml_file(policy)
        compiled_guards, policy_metadata = compile_policy(yaml_bytes)

        # Extract composition structure
        composition = policy_metadata.get('compose', {})
        guards_list = policy_metadata.get('guards', [])

        if format == "json":
            graph_data = {
                "policy_id": policy_metadata.get('policy', 'unknown'),
                "guards": guards_list,
                "composition": composition
            }
            output_str = json.dumps(graph_data, indent=2)

        elif format == "dot":
            # Generate DOT format
            lines = ["digraph policy {"]
            lines.append("  rankdir=LR;")

            # Add guards as nodes
            for guard in guards_list:
                guard_id = guard.get('id', 'unknown')
                lines.append(f'  "{guard_id}" [shape=box];')

            # Add composition edges (simplified)
            root = composition.get('root', '')
            lines.append(f'  "input" -> "{root}";')
            lines.append(f'  "{root}" -> "output";')

            lines.append("}")
            output_str = "\n".join(lines)

        elif format == "png":
            console.print("[yellow]PNG export requires graphviz - not yet implemented[/yellow]")
            sys.exit(1)

        else:
            console.print(f"[red]Unknown format: {format}[/red]")
            sys.exit(1)

        # Write or print
        if output:
            output.write_text(output_str)
            console.print(f"[green]✓[/green] Graph exported to {output}")
        else:
            print(output_str)

        sys.exit(0)

    except Exception as e:
        console.print("[red]✗[/red] Graph export failed:", style="bold")
        console.print(f"  {str(e)}", style="red")
        sys.exit(2)


@app.command()
def diff(
    policy1: Path = typer.Argument(..., help="First policy/envelope"),
    policy2: Path = typer.Argument(..., help="Second policy/envelope")
):
    """
    Diff two policies or envelopes

    Shows differences in:
    - Guards added/removed
    - Composition changes
    - Threshold changes
    """
    console.print("[yellow]Policy diff not yet implemented[/yellow]")
    raise typer.Exit(0)


@app.command()
def fmt(
    policy: Path = typer.Argument(..., help="Path to policy YAML file"),
    check: bool = typer.Option(False, "--check", help="Check only, don't modify")
):
    """
    Format policy YAML with stable ordering

    Ensures consistent formatting:
    - Sorted keys
    - Consistent indentation
    - Stable guard ordering
    """
    try:
        # Load YAML
        yaml_bytes = load_yaml_file(policy)
        policy_data = yaml.safe_load(yaml_bytes)

        # Re-serialize with consistent formatting
        formatted = yaml.dump(
            policy_data,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
            width=88
        )

        # Check mode
        if check:
            original = yaml_bytes.decode('utf-8')
            if original == formatted:
                console.print(f"[green]✓[/green] {policy} is correctly formatted")
                sys.exit(0)
            else:
                console.print(f"[red]✗[/red] {policy} needs formatting")
                sys.exit(1)

        # Write formatted version
        policy.write_text(formatted)
        console.print(f"[green]✓[/green] Formatted {policy}")
        sys.exit(0)

    except Exception as e:
        console.print("[red]✗[/red] Formatting failed:", style="bold")
        console.print(f"  {str(e)}", style="red")
        sys.exit(2)


@app.command()
def keygen():
    """
    Generate Ed25519 signing keypair for Mímir

    Outputs:
    - Signing key (keep secret!)
    - Verify key (distribute to gateways)
    """
    try:
        signing_key, verify_key = generate_signing_keypair()

        console.print("[green]✓[/green] Generated Ed25519 keypair", style="bold")
        console.print()
        console.print("[yellow]Signing Key (keep secret!):[/yellow]")
        console.print(f"  {signing_key.decode('utf-8')}")
        console.print()
        console.print("[green]Verify Key (distribute to gateways):[/green]")
        console.print(f"  {verify_key.decode('utf-8')}")
        console.print()
        console.print("[dim]Store signing key securely (vault, KMS, etc.)[/dim]")

        sys.exit(0)

    except Exception as e:
        console.print("[red]✗[/red] Keygen failed:", style="bold")
        console.print(f"  {str(e)}", style="red")
        sys.exit(2)

