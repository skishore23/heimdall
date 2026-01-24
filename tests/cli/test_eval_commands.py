"""
Tests for eval subcommands
"""

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
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(policy_yaml)
        yield Path(f.name)

    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def sample_suite():
    """Create a sample eval suite file"""
    suite_yaml = """
suite: test_suite
description: Test suite

tests:
  - name: test_case_1
    input: "Test input"
    expect: pass
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(suite_yaml)
        yield Path(f.name)

    Path(f.name).unlink(missing_ok=True)


def test_eval_suite_missing_policy():
    """Test eval suite with missing policy"""
    result = runner.invoke(app, [
        "eval", "suite",
        "-p", "nonexistent.yaml",
        "-s", "suite.yaml"
    ])

    assert result.exit_code == 4
    assert "not found" in result.stdout.lower()


def test_eval_suite_missing_suite(sample_policy):
    """Test eval suite with missing suite file"""
    result = runner.invoke(app, [
        "eval", "suite",
        "-p", str(sample_policy),
        "-s", "nonexistent.yaml"
    ])

    assert result.exit_code == 4
    assert "not found" in result.stdout.lower()


def test_eval_suite_with_files(sample_policy, sample_suite):
    """Test eval suite with valid files"""
    result = runner.invoke(app, [
        "eval", "suite",
        "-p", str(sample_policy),
        "-s", str(sample_suite)
    ])

    # May fail if guards not registered, but should parse arguments
    assert result.exit_code in [0, 1]


def test_eval_bench_not_implemented():
    """Test eval bench (placeholder)"""
    result = runner.invoke(app, [
        "eval", "bench",
        "--guard", "test.guard",
        "-n", "10"
    ])

    assert result.exit_code == 0
    assert "not" in result.stdout.lower() and "implemented" in result.stdout.lower()


def test_eval_help():
    """Test eval help command"""
    result = runner.invoke(app, ["eval", "--help"])

    assert result.exit_code == 0
    assert "suite" in result.stdout
    assert "bench" in result.stdout

