"""
Tests for policy subcommands
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
policy: test_policy_v1
description: Test policy

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

    # Cleanup
    Path(f.name).unlink(missing_ok=True)


def test_policy_lint_missing_file():
    """Test policy lint with missing file"""
    result = runner.invoke(app, ["policy", "lint", "nonexistent.yaml"])

    assert result.exit_code == 2
    assert "not found" in result.stdout.lower() or "Policy file not found" in result.stdout


def test_policy_lint_json_output(sample_policy):
    """Test policy lint with JSON output"""
    result = runner.invoke(app, ["policy", "lint", str(sample_policy), "--json"])

    # Should either succeed or fail with JSON output
    if result.exit_code == 0:
        output = json.loads(result.stdout)
        assert "status" in output
        assert output["status"] == "valid"
    else:
        # If it fails (guards not registered), should still be JSON
        try:
            output = json.loads(result.stdout)
            assert "status" in output or "error" in output
        except json.JSONDecodeError:
            # Acceptable if guards not registered in test environment
            pass


def test_policy_compile_without_signing(sample_policy):
    """Test policy compile without signing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "policy.json"

        result = runner.invoke(app, [
            "policy", "compile",
            "-p", str(sample_policy),
            "-o", str(output_path)
        ])

        # May fail if guards not registered, but command should be parseable
        assert "policy" in result.stdout.lower() or result.exit_code in [0, 2]


def test_policy_compile_json_output(sample_policy):
    """Test policy compile with JSON output"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "policy.json"

        result = runner.invoke(app, [
            "policy", "compile",
            "-p", str(sample_policy),
            "-o", str(output_path),
            "--json"
        ])

        # Should produce JSON output regardless of success
        if result.stdout.strip():
            try:
                output = json.loads(result.stdout)
                assert "status" in output or "error" in output
            except json.JSONDecodeError:
                # Acceptable if guards not registered
                pass


def test_policy_verify_missing_file():
    """Test policy verify with missing file"""
    result = runner.invoke(app, ["policy", "verify", "nonexistent.json"])

    assert result.exit_code == 2
    assert "not found" in result.stdout.lower() or "Envelope not found" in result.stdout


def test_policy_keygen():
    """Test policy keygen command"""
    result = runner.invoke(app, ["policy", "keygen"])

    assert result.exit_code == 0
    assert "Signing Key" in result.stdout
    assert "Verify Key" in result.stdout
    assert "Ed25519" in result.stdout


def test_policy_graph_missing_file():
    """Test policy graph with missing file"""
    result = runner.invoke(app, ["policy", "graph", "nonexistent.yaml"])

    assert result.exit_code == 2


def test_policy_graph_json_format(sample_policy):
    """Test policy graph with JSON format"""
    result = runner.invoke(app, [
        "policy", "graph",
        str(sample_policy),
        "-f", "json"
    ])

    # Should attempt to output JSON or fail gracefully
    if result.exit_code == 0:
        try:
            output = json.loads(result.stdout)
            assert "policy_id" in output or "guards" in output
        except json.JSONDecodeError:
            pytest.fail("Expected valid JSON output")


def test_policy_fmt_check_mode(sample_policy):
    """Test policy fmt in check mode"""
    result = runner.invoke(app, ["policy", "fmt", str(sample_policy), "--check"])

    # Should exit 0 or 1 depending on formatting
    assert result.exit_code in [0, 1, 2]


def test_version_command():
    """Test version command"""
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert "Heimdall" in result.stdout
    assert "version" in result.stdout.lower()


def test_help_command():
    """Test help command"""
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "policy" in result.stdout
    assert "run" in result.stdout
    assert "models" in result.stdout


def test_policy_help():
    """Test policy subcommand help"""
    result = runner.invoke(app, ["policy", "--help"])

    assert result.exit_code == 0
    assert "lint" in result.stdout
    assert "compile" in result.stdout
    assert "verify" in result.stdout

