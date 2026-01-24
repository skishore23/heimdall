"""
Eval subcommands: suite, bench
"""

import asyncio
from pathlib import Path

import typer
from rich.console import Console

from heimdall.eval_harness import run_eval

console = Console()
app = typer.Typer(help="Evaluation and benchmarking")


@app.command()
def suite(
    policy: Path = typer.Option(..., "-p", "--policy", help="Path to policy YAML file"),
    suite: list[Path] = typer.Option(..., "-s", "--suite", help="Path to test suite YAML (can repeat)"),
    output: Path | None = typer.Option(None, "-o", "--out", help="Output JSON file for results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Run eval suites against a policy

    Examples:
        # Run single suite
        heimdall eval suite -p policy.yaml -s suites/pii.yaml

        # Run multiple suites
        heimdall eval suite -p policy.yaml -s suites/pii.yaml -s suites/jailbreak.yaml

        # Save results
        heimdall eval suite -p policy.yaml -s suites/pii.yaml -o results/pii.json
    """
    import json

    # Validate paths
    if not policy.exists():
        console.print(f"[red]✗[/red] Policy not found: {policy}", style="bold")
        raise typer.Exit(4)

    suite_paths = []
    for suite_path in suite:
        if not suite_path.exists():
            console.print(f"[red]✗[/red] Suite not found: {suite_path}", style="bold")
            raise typer.Exit(4)
        suite_paths.append(str(suite_path))

    # Run evaluation
    if not json_output:
        console.print("[blue]→[/blue] Running evaluation...", style="bold")
        console.print(f"  Policy: {policy}")
        console.print(f"  Suites: {len(suite_paths)}")

    scoreboards = asyncio.run(
        run_eval(str(policy), suite_paths, str(output) if output else None)
    )

    # Check results
    total_passed = sum(s.passed for s in scoreboards)
    total_tests = sum(s.total_tests for s in scoreboards)

    if json_output:
        result = {
            "policy": str(policy),
            "suites": suite_paths,
            "total_tests": total_tests,
            "passed": total_passed,
            "failed": total_tests - total_passed,
            "scoreboards": [
                {
                    "suite": s.suite_name,
                    "passed": s.passed,
                    "failed": s.failed,
                    "total": s.total_tests
                }
                for s in scoreboards
            ]
        }
        print(json.dumps(result, indent=2))
    else:
        console.print()
        for scoreboard in scoreboards:
            status_color = "green" if scoreboard.passed == scoreboard.total_tests else "red"
            console.print(
                f"[{status_color}]{scoreboard.suite_name}:[/{status_color}] "
                f"{scoreboard.passed}/{scoreboard.total_tests} passed"
            )

        console.print()
        if total_passed == total_tests:
            console.print("[green]✓[/green] All tests passed!", style="bold")
        else:
            console.print(
                f"[red]✗[/red] {total_tests - total_passed} test(s) failed",
                style="bold"
            )

    # Exit with error if any test failed
    exit_code = 0 if total_passed == total_tests else 1
    raise typer.Exit(exit_code)


@app.command()
def bench(
    guard: str = typer.Option(..., "-g", "--guard", help="Guard ID to benchmark"),
    iterations: int = typer.Option(200, "-n", "--iterations", help="Number of iterations"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON")
):
    """
    Micro-benchmark a guard

    Measures:
    - P50, P95, P99 latency
    - Throughput (ops/sec)
    - Memory usage (basic)

    Examples:
        heimdall eval bench --guard safety.toxicity.local_onnx -n 200
        heimdall eval bench --guard pii.email -n 1000 --json
    """
    import json

    console.print("[yellow]Guard benchmarking not yet fully implemented[/yellow]")
    console.print("Hint: Use the eval_harness module directly for now")

    # Placeholder for future implementation
    result = {
        "guard": guard,
        "iterations": iterations,
        "status": "not_implemented"
    }

    if json_output:
        print(json.dumps(result, indent=2))

    raise typer.Exit(0)

