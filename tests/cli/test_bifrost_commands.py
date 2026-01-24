"""
Tests for bifrost subcommands
"""

import json
import tempfile

from typer.testing import CliRunner

from heimdall_cli.app import app

runner = CliRunner()


def test_bifrost_status_when_not_running():
    """Test bifrost status when gateway not running"""
    result = runner.invoke(app, ["bifrost", "status"])

    # Should exit with code 5 (network error) when Bifröst not running
    assert result.exit_code == 5
    assert "Failed to connect" in result.stdout or "error" in result.stdout.lower()


def test_bifrost_status_json_output_when_not_running():
    """Test bifrost status JSON output when gateway not running"""
    result = runner.invoke(app, ["bifrost", "status", "--json"])

    assert result.exit_code == 5
    output = json.loads(result.stdout)
    assert "status" in output
    assert output["status"] == "error"
    assert "error" in output


def test_bifrost_reload_missing_file():
    """Test bifrost reload with missing file"""
    result = runner.invoke(app, ["bifrost", "reload", "nonexistent.json"])

    assert result.exit_code == 4
    assert "not found" in result.stdout.lower()


def test_bifrost_reload_when_not_running():
    """Test bifrost reload when gateway not running"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as f:
        f.write('{"policy_id": "test", "version": "1.0"}')
        f.flush()

        result = runner.invoke(app, ["bifrost", "reload", f.name])

        # Should fail with network error
        assert result.exit_code == 5


def test_bifrost_trace_when_not_running():
    """Test bifrost trace when gateway not running"""
    result = runner.invoke(app, ["bifrost", "trace", "-n", "10"])

    # Should fail with network error
    assert result.exit_code == 5


def test_bifrost_help():
    """Test bifrost help command"""
    result = runner.invoke(app, ["bifrost", "--help"])

    assert result.exit_code == 0
    assert "status" in result.stdout
    assert "reload" in result.stdout
    assert "trace" in result.stdout

