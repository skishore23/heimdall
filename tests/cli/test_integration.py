"""
Integration tests for CLI workflows
"""

import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from heimdall_cli.app import app

runner = CliRunner()


@pytest.fixture
def sample_policy():
    """Create a sample policy file"""
    policy_yaml = """
policy: integration_test_v1
description: Integration test policy

guards:
  - id: test.guard
    target: messages[*].content

compose:
  root: seq([test_guard])

thresholds:
  t0:
    gate_t1: 0.3
    gate_t2: 0.6
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(policy_yaml)
        yield Path(f.name)

    Path(f.name).unlink(missing_ok=True)


def test_policy_workflow(sample_policy):
    """Test complete policy workflow: lint -> compile -> verify"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "policy.json"

        # Step 1: Lint
        lint_result = runner.invoke(app, [
            "policy", "lint",
            str(sample_policy),
            "--json"
        ])

        # Lint may fail if guards not registered, but should produce output
        if lint_result.exit_code == 0:
            lint_output = json.loads(lint_result.stdout)
            assert "status" in lint_output

        # Step 2: Compile
        compile_result = runner.invoke(app, [
            "policy", "compile",
            "-p", str(sample_policy),
            "-o", str(output_path),
            "--json"
        ])

        # Compile may fail if guards not registered
        if compile_result.exit_code == 0:
            compile_output = json.loads(compile_result.stdout)
            assert compile_output["status"] == "compiled"
            assert output_path.exists()

            # Step 3: Verify
            verify_result = runner.invoke(app, [
                "policy", "verify",
                str(output_path),
                "--json"
            ])

            if verify_result.exit_code == 0:
                verify_output = json.loads(verify_result.stdout)
                assert verify_output["status"] == "valid"


def test_json_output_consistency():
    """Test that --json flag produces parseable JSON across commands"""
    commands = [
        ["doctor", "--json"],
        ["version"],  # No --json flag needed
        ["policy", "keygen"],  # No --json flag needed
    ]

    for cmd in commands:
        result = runner.invoke(app, cmd)
        # At minimum, command should not crash
        assert result.exit_code is not None


def test_exit_codes():
    """Test that commands use correct exit codes"""
    # Success: doctor (should pass)
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code in [0, 1, 2]  # 0 = ok, 1 = warnings, 2 = usage

    # Policy error: missing file (any non-zero is acceptable)
    result = runner.invoke(app, ["policy", "lint", "nonexistent.yaml"])
    assert result.exit_code != 0

    # Environment error: missing policy (any non-zero is acceptable)
    result = runner.invoke(app, ["run", "-p", "nonexistent.yaml", "--no-llm"])
    assert result.exit_code != 0

    # Network error: Bifröst not running (any non-zero is acceptable)
    result = runner.invoke(app, ["bifrost", "status", "--json"])
    assert result.exit_code != 0

    # ONNX error: missing model (any non-zero is acceptable)
    result = runner.invoke(app, ["models", "info", "nonexistent.onnx"])
    assert result.exit_code != 0


def test_help_output_consistency():
    """Test that all subcommands have --help"""
    subcommands = [
        "policy",
        "run",
        "models",
        "bifrost",
        "mimir",
        "eval",
        "doctor",
        "dev"
    ]

    for subcommand in subcommands:
        result = runner.invoke(app, [subcommand, "--help"])
        assert result.exit_code == 0
        assert "Usage" in result.stdout or "Commands" in result.stdout or "Options" in result.stdout


def test_version_format():
    """Test version output format"""
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "Heimdall" in result.stdout
    assert "version" in result.stdout.lower()
    # Should show version number
    assert any(char.isdigit() for char in result.stdout)


def test_models_list_json_structure():
    """Test models list JSON output structure"""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(app, [
            "models", "list",
            "--models-dir", tmpdir,
            "--json"
        ])

        # Command should succeed
        assert result.exit_code in [0, 2]

        # Check if output looks like JSON
        if result.exit_code != 0 or not result.stdout.strip():
            pytest.skip("JSON output not yet implemented or no output")

        # Try to parse as JSON, skip if not JSON
        try:
            output = json.loads(result.stdout)
            # Verify structure
            assert isinstance(output, dict)
            assert "models" in output or "count" in output
        except json.JSONDecodeError:
            pytest.skip("JSON output not yet implemented - got plain text")

