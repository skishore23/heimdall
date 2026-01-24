"""
Run command: Local SDK mode (no gateway required)
"""

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from heimdall import get_violations, is_left
from heimdall_cli.config import HeimdallConfig
from heimdall_sdk import HeimdallSDK

console = Console()
app = typer.Typer(help="Run guards locally")


@app.command()
def run(
    policy: Path | None = typer.Option(None, "-p", "--policy", help="Path to policy YAML file"),
    model: str | None = typer.Option(None, "-m", "--model", help="Model to use (e.g., openai:gpt-4o)"),
    input_text: str | None = typer.Option(None, "-i", "--input", help="Input text or path to file"),
    prompt: str | None = typer.Option(None, "--prompt", help="Prompt text (or read from stdin)"),
    vars: list[str] = typer.Option([], "--vars", help="Context variables (key=value)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Run guards only, skip LLM call")
):
    """
    Run policy locally (SDK mode)

    Examples:
        # Run from stdin
        echo "Hello" | heimdall run -p policy.yaml -m openai:gpt-4o

        # Run from file
        heimdall run -p policy.yaml --input prompt.txt

        # Guards only (no LLM)
        heimdall run -p policy.yaml --input test.txt --no-llm

        # With context variables
        heimdall run -p policy.yaml --vars user_id=42 --vars tenant=acme
    """
    # Load config
    config = HeimdallConfig()

    # Resolve policy path
    if policy is None:
        if config.default_policy:
            policy = config.policies_dir / f"{config.default_policy}.yaml"
        else:
            console.print("[red]✗[/red] No policy specified and no default configured", style="bold")
            raise typer.Exit(4)

    if not policy.exists():
        console.print(f"[red]✗[/red] Policy not found: {policy}", style="bold")
        raise typer.Exit(4)

    # Resolve model
    if model is None:
        model = config.default_model

    # Read input
    if input_text:
        # Check if it's a file path
        input_path = Path(input_text)
        if input_path.exists():
            prompt = input_path.read_text()
        else:
            prompt = input_text
    elif prompt is None:
        # Read from stdin
        if not sys.stdin.isatty():
            prompt = sys.stdin.read()
        else:
            console.print("[red]✗[/red] No input provided (use --input, --prompt, or pipe to stdin)", style="bold")
            raise typer.Exit(1)

    # Parse context variables
    context_vars: dict[str, str] = {}
    for var in vars:
        if '=' not in var:
            console.print(f"[red]✗[/red] Invalid variable format: {var} (expected key=value)", style="bold")
            raise typer.Exit(1)
        key, value = var.split('=', 1)
        context_vars[key] = value

    # Run async execution
    result = asyncio.run(
        execute_run(
            policy=policy,
            model=model,
            prompt=prompt,
            context_vars=context_vars,
            json_output=json_output,
            no_llm=no_llm
        )
    )

    raise typer.Exit(result)


async def execute_run(
    policy: Path,
    model: str,
    prompt: str,
    context_vars: dict[str, str],
    json_output: bool,
    no_llm: bool
) -> int:
    """Execute the run command asynchronously"""

    try:
        # Import guard packs
        import guards  # noqa: F401

        # Create SDK instance
        sdk = HeimdallSDK()

        # Load policy
        sdk.load_policy_from_file(str(policy))
        policy_data = sdk.loaded_policies.get(policy.stem, {})
        policy_metadata = policy_data.get('metadata', {})
        policy_id = policy_metadata.get('policy', policy.stem)

        if not json_output:
            console.print(f"[blue]→[/blue] Running with policy: {policy_id}")
            console.print(f"[blue]→[/blue] Model: {model}")

        # Build request
        request = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            **context_vars
        }

        if no_llm:
            # Run guards only
            compiled_guards = policy_data.get('compiled', {})

            # Run input guards
            input_guard = compiled_guards.get('input')
            if input_guard:
                context = {
                    "messages": request["messages"],
                    **context_vars
                }
                result = await input_guard(context)

                if is_left(result):
                    violations = get_violations(result)

                    if json_output:
                        output = {
                            "status": "blocked",
                            "phase": "input",
                            "violations": violations
                        }
                        print(json.dumps(output, indent=2))
                    else:
                        console.print("[red]✗[/red] Input guards blocked request:", style="bold")
                        for i, violation in enumerate(violations, 1):
                            console.print(f"  {i}. [{violation['severity']}] {violation['rule_id']}: {violation['message']}")

                    return 3

            if json_output:
                output = {
                    "status": "passed",
                    "phase": "input"
                }
                print(json.dumps(output, indent=2))
            else:
                console.print("[green]✓[/green] All guards passed", style="bold")

            return 0

        else:
            # Full run with LLM
            response = await sdk.chat_completion(
                model=model,
                messages=request["messages"],
                policy=policy_id,
                **context_vars
            )

            # Check for violations
            if 'error' in response:
                if json_output:
                    print(json.dumps(response, indent=2))
                else:
                    console.print(f"[red]✗[/red] Error: {response['error']}", style="bold")

                return 3

            # Success
            if json_output:
                print(json.dumps(response, indent=2))
            else:
                console.print(Panel(
                    response.get('content', response.get('choices', [{}])[0].get('message', {}).get('content', '')),
                    title="[green]Response[/green]",
                    border_style="green"
                ))

            return 0

    except ValueError as e:
        # Environment error (e.g., missing API key)
        if json_output:
            output = {
                "status": "error",
                "error": str(e),
                "error_type": "environment"
            }
            print(json.dumps(output, indent=2))
        else:
            console.print("[red]✗[/red] Environment error:", style="bold")
            console.print(f"  {str(e)}", style="red")

        return 4

    except Exception as e:
        if json_output:
            output = {
                "status": "error",
                "error": str(e)
            }
            print(json.dumps(output, indent=2))
        else:
            console.print("[red]✗[/red] Execution failed:", style="bold")
            console.print(f"  {str(e)}", style="red")

        return 1

