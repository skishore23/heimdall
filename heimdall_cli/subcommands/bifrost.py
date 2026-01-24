"""
Bifröst subcommands: status, reload, trace, logs
"""

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from bifrost.client import BifrostClient
from heimdall_cli.config import HeimdallConfig

console = Console()
app = typer.Typer(help="Bifröst gateway control")


@app.command()
def status(
    url: str | None = typer.Option(None, "--url", help="Bifröst URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Check Bifröst gateway status

    Shows:
    - Health status
    - Version
    - Active policy
    - Request metrics
    """
    # Load config
    config = HeimdallConfig()
    bifrost_url = url or config.bifrost_url

    # Run async
    result = asyncio.run(get_status_async(bifrost_url, json_output))
    raise typer.Exit(result)


async def get_status_async(url: str, json_output: bool) -> int:
    """Get status asynchronously"""
    try:
        client = BifrostClient(url)
        status_data = await client.get_status()

        if json_output:
            print(json.dumps(status_data, indent=2))
            return 0

        # Display health
        health = status_data['health']
        status_str = health['status']
        status_color = "green" if status_str == "healthy" else "red"

        console.print(f"[{status_color}]●[/{status_color}] Bifröst Gateway", style="bold")
        console.print(f"  Status: [{status_color}]{status_str}[/{status_color}]")
        console.print(f"  Version: {health['version']}")
        console.print(f"  Redis: {health.get('redis', 'unknown')}")

        # Display info
        info = status_data['info']
        console.print("\n[bold]Configuration:[/bold]")
        console.print(f"  Default Policy: {info['config'].get('default_policy_id', 'none')}")
        console.print(f"  OpenAI Key: {'✓' if info['config'].get('openai_api_key_configured') else '✗'}")
        console.print(f"  Anthropic Key: {'✓' if info['config'].get('anthropic_api_key_configured') else '✗'}")

        # Display metrics
        metrics = status_data['metrics']
        console.print("\n[bold]Metrics:[/bold]")
        console.print(f"  Total Requests: {metrics.get('gateway_requests_total', 0)}")
        console.print(f"  Avg Duration: {metrics.get('gateway_request_duration_seconds', 0):.3f}s")

        guard_metrics = metrics.get('guard_performance_metrics', {})
        if guard_metrics:
            console.print(f"  Guard Executions: {guard_metrics.get('total_executions', 0)}")
            console.print(f"  Avg Guard Time: {guard_metrics.get('average_execution_time_ms', 0):.2f}ms")

        return 0

    except Exception as e:
        if json_output:
            result = {
                "status": "error",
                "error": str(e)
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[red]✗[/red] Failed to connect to Bifröst:", style="bold")
            console.print(f"  {str(e)}", style="red")
            console.print(f"\n  URL: {url}")
            console.print("  Hint: Is Bifröst running?")

        return 5


@app.command()
def reload(
    envelope: Path = typer.Argument(..., help="Path to policy envelope JSON"),
    url: str | None = typer.Option(None, "--url", help="Bifröst URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Hot-reload a policy envelope

    Atomically updates the active policy without restarting the gateway.
    Requires a signed envelope (from 'heimdall policy compile --signing-key').
    """
    # Load config
    config = HeimdallConfig()
    bifrost_url = url or config.bifrost_url

    if not envelope.exists():
        console.print(f"[red]✗[/red] Envelope not found: {envelope}", style="bold")
        raise typer.Exit(4)

    # Run async
    result = asyncio.run(reload_async(bifrost_url, envelope, json_output))
    raise typer.Exit(result)


async def reload_async(url: str, envelope: Path, json_output: bool) -> int:
    """Reload policy asynchronously"""
    try:
        client = BifrostClient(url)
        result = await client.reload_policy(str(envelope))

        if json_output:
            print(json.dumps(result, indent=2))
        else:
            console.print("[green]✓[/green] Policy reloaded successfully", style="bold")
            console.print(f"  Envelope: {envelope}")

        return 0

    except Exception as e:
        if json_output:
            result = {
                "status": "error",
                "error": str(e)
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[red]✗[/red] Hot-reload failed:", style="bold")
            console.print(f"  {str(e)}", style="red")

        return 5


@app.command()
def trace(
    follow: bool = typer.Option(False, "-f", "--follow", help="Stream traces continuously"),
    guard_id: str | None = typer.Option(None, "--guard", help="Filter by guard ID"),
    decision: str | None = typer.Option(None, "--decision", help="Filter by decision (pass/block)"),
    limit: int = typer.Option(100, "-n", "--limit", help="Number of traces to show (non-streaming)"),
    url: str | None = typer.Option(None, "--url", help="Bifröst URL"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    View decision traces

    Examples:
        # Show recent traces
        heimdall bifrost trace -n 50

        # Stream live traces
        heimdall bifrost trace --follow

        # Filter by guard
        heimdall bifrost trace --guard pii.email --follow

        # Filter by decision
        heimdall bifrost trace --decision block --follow
    """
    # Load config
    config = HeimdallConfig()
    bifrost_url = url or config.bifrost_url

    # Run async
    result = asyncio.run(
        trace_async(bifrost_url, follow, guard_id, decision, limit, json_output)
    )
    raise typer.Exit(result)


async def trace_async(
    url: str,
    follow: bool,
    guard_id: str | None,
    decision: str | None,
    limit: int,
    json_output: bool
) -> int:
    """View traces asynchronously"""
    try:
        client = BifrostClient(url)

        if follow:
            # Stream traces
            if not json_output:
                console.print("[blue]→[/blue] Streaming traces... (Ctrl+C to stop)", style="dim")

            async for trace in client.stream_traces(guard_id=guard_id, decision=decision):
                if json_output:
                    print(json.dumps(trace))
                else:
                    # Format trace nicely
                    trace_guard = trace.get('guard_id', 'unknown')
                    trace_decision = trace.get('decision', 'unknown')
                    trace_time = trace.get('duration_ms', 0)

                    decision_color = "green" if trace_decision == "pass" else "red"
                    console.print(
                        f"[{decision_color}]{trace_decision.upper():>5}[/{decision_color}] "
                        f"[cyan]{trace_guard:30}[/cyan] "
                        f"[dim]{trace_time:.2f}ms[/dim]"
                    )
        else:
            # Get recent traces
            result = await client.get_trace_list(
                guard_id=guard_id,
                decision=decision,
                limit=limit
            )

            if json_output:
                print(json.dumps(result, indent=2))
            else:
                traces = result.get('traces', [])
                console.print(f"[bold]Recent Traces ({len(traces)}):[/bold]")

                for trace in traces:
                    trace_guard = trace.get('guard_id', 'unknown')
                    trace_decision = trace.get('decision', 'unknown')
                    trace_time = trace.get('duration_ms', 0)

                    decision_color = "green" if trace_decision == "pass" else "red"
                    console.print(
                        f"[{decision_color}]{trace_decision.upper():>5}[/{decision_color}] "
                        f"[cyan]{trace_guard:30}[/cyan] "
                        f"[dim]{trace_time:.2f}ms[/dim]"
                    )

        return 0

    except KeyboardInterrupt:
        if not json_output:
            console.print("\n[yellow]Stopped[/yellow]")
        return 0

    except Exception as e:
        if json_output:
            result = {
                "status": "error",
                "error": str(e)
            }
            print(json.dumps(result, indent=2))
        else:
            console.print("[red]✗[/red] Trace failed:", style="bold")
            console.print(f"  {str(e)}", style="red")

        return 5


@app.command()
def logs():
    """
    View Bifröst logs

    Note: Log retrieval depends on your deployment.
    This is a placeholder for future implementation.
    """
    console.print("[yellow]Log retrieval not yet implemented[/yellow]")
    console.print("Hint: Use your deployment's logging system (CloudWatch, Stackdriver, etc.)")
    raise typer.Exit(0)

