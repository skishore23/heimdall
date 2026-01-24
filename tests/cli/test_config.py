"""
Tests for CLI configuration management
"""

import os
import tempfile
from pathlib import Path

import yaml

from heimdall_cli.config import (
    HeimdallConfig,
    discover_config_file,
    load_config,
)


def test_config_defaults():
    """Test default configuration values"""
    config = HeimdallConfig()

    assert str(config.policies_dir) == "./policies"
    assert str(config.build_dir) == "./build"
    assert str(config.models_dir) == "./models"
    assert config.bifrost_url == "http://localhost:8080"
    assert config.default_model == "openai:gpt-4o"
    assert config.timeout == 30.0


def test_config_from_env_vars():
    """Test configuration from environment variables"""
    os.environ["HEIMDALL_POLICIES_DIR"] = "/custom/policies"
    os.environ["HEIMDALL_BIFROST_URL"] = "http://custom:9090"
    os.environ["HEIMDALL_DEFAULT_MODEL"] = "anthropic:claude-3"

    try:
        config = HeimdallConfig()

        assert config.policies_dir == "/custom/policies"
        assert config.bifrost_url == "http://custom:9090"
        assert config.default_model == "anthropic:claude-3"
    finally:
        # Cleanup
        del os.environ["HEIMDALL_POLICIES_DIR"]
        del os.environ["HEIMDALL_BIFROST_URL"]
        del os.environ["HEIMDALL_DEFAULT_MODEL"]


def test_discover_config_file():
    """Test config file discovery"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        config_path = tmpdir_path / "heimdall.yaml"

        # Create config file
        config_path.write_text("policies_dir: ./test-policies\n")

        # Change to temp directory
        original_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)

            discovered = discover_config_file()
            assert discovered is not None
            assert discovered.name == "heimdall.yaml"
        finally:
            os.chdir(original_cwd)


def test_discover_config_file_in_parent():
    """Test config file discovery in parent directories"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir).resolve()  # Resolve to handle /private/var symlink
        config_path = tmpdir_path / "heimdall.yaml"
        subdir = tmpdir_path / "subdir" / "nested"
        subdir.mkdir(parents=True)

        # Create config file in root
        config_path.write_text("policies_dir: ./test-policies\n")

        # Change to nested directory
        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)

            discovered = discover_config_file()
            assert discovered is not None
            assert discovered.name == "heimdall.yaml"
            # Resolve both paths to handle macOS /private/var symlink
            assert discovered.parent.resolve() == tmpdir_path
        finally:
            os.chdir(original_cwd)


def test_load_config_from_yaml():
    """Test loading configuration from YAML file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        config_path = tmpdir_path / "heimdall.yaml"

        # Create config file
        config_data = {
            "policies_dir": "./custom-policies",
            "build_dir": "./custom-build",
            "models_dir": "./custom-models",
            "bifrost_url": "http://custom:8080",
            "defaults": {
                "policy": "custom_policy",
                "model": "custom:model"
            }
        }

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Load config
        config = load_config(config_file=config_path)

        assert config.policies_dir == "./custom-policies"
        assert config.build_dir == "./custom-build"
        assert config.models_dir == "./custom-models"
        assert config.bifrost_url == "http://custom:8080"
        assert config.default_policy == "custom_policy"
        assert config.default_model == "custom:model"


def test_load_config_with_overrides():
    """Test configuration overrides"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        config_path = tmpdir_path / "heimdall.yaml"

        # Create config file
        config_data = {
            "policies_dir": "./custom-policies",
            "bifrost_url": "http://custom:8080",
        }

        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)

        # Load config with overrides
        config = load_config(
            config_file=config_path,
            bifrost_url="http://override:9090",
            timeout=60.0
        )

        assert config.policies_dir == "./custom-policies"  # From YAML
        assert config.bifrost_url == "http://override:9090"  # Override
        assert config.timeout == 60.0  # Override


def test_config_json_output_flag():
    """Test JSON output flag"""
    os.environ["HEIMDALL_JSON"] = "true"

    try:
        config = HeimdallConfig()
        assert config.json
    finally:
        del os.environ["HEIMDALL_JSON"]


def test_config_no_color_flag():
    """Test no-color flag"""
    os.environ["HEIMDALL_NO_COLOR"] = "true"

    try:
        config = HeimdallConfig()
        assert config.no_color
    finally:
        del os.environ["HEIMDALL_NO_COLOR"]

