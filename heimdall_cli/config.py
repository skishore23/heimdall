"""
Configuration management for Heimdall CLI

Loads configuration from (in order of precedence):
1. CLI flags
2. Environment variables
3. heimdall.yaml in current/parent dirs
4. Built-in defaults
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class HeimdallConfig(BaseSettings):
    """Heimdall CLI configuration"""

    model_config = SettingsConfigDict(env_prefix="HEIMDALL_")

    # Directories - using str to avoid Path/generator issues with Pydantic
    policies_dir: str = "./policies"
    build_dir: str = "./build"
    models_dir: str = "./models"

    # Bifröst gateway
    bifrost_url: str = "http://localhost:8080"

    # Defaults
    default_policy: str | None = "enterprise_default_v1"
    default_model: str = "openai:gpt-4o"

    # Mímir signing keys
    mimir_signing_key: str | None = None
    mimir_verify_key: str | None = None

    # Timeouts
    timeout: float = 30.0
    guard_timeout: float = 0.2

    # Environment
    env: str = "development"
    tenant: str = "default"

    # Output
    json: bool = False
    quiet: bool = False
    no_color: bool = False


def discover_config_file() -> Path | None:
    """
    Discover heimdall.yaml in current or parent directories

    Returns:
        Path to config file if found, None otherwise
    """
    current = Path.cwd()

    for parent in [current] + list(current.parents):
        config_path = parent / "heimdall.yaml"
        if config_path.exists():
            return config_path

    return None


def load_config(
    config_file: Path | None = None,
    **overrides: Any
) -> HeimdallConfig:
    """
    Load configuration with layered overrides

    Args:
        config_file: Optional explicit config file path
        **overrides: CLI flag overrides

    Returns:
        Merged configuration
    """
    # Start with defaults
    config_data: dict[str, Any] = {}

    # Discover or use explicit config file
    if config_file is None:
        config_file = discover_config_file()

    # Load from YAML if found
    if config_file and config_file.exists():
        with open(config_file) as f:
            yaml_data = yaml.safe_load(f) or {}

            # Extract top-level config
            if 'policies_dir' in yaml_data:
                config_data['policies_dir'] = yaml_data['policies_dir']
            if 'build_dir' in yaml_data:
                config_data['build_dir'] = yaml_data['build_dir']
            if 'models_dir' in yaml_data:
                config_data['models_dir'] = yaml_data['models_dir']
            if 'bifrost_url' in yaml_data:
                config_data['bifrost_url'] = yaml_data['bifrost_url']

            # Extract defaults section
            if 'defaults' in yaml_data:
                defaults = yaml_data['defaults']
                if 'policy' in defaults:
                    config_data['default_policy'] = defaults['policy']
                if 'model' in defaults:
                    config_data['default_model'] = defaults['model']

    # Apply CLI overrides (highest precedence)
    for k, v in overrides.items():
        if v is not None:
            config_data[k] = v

    return HeimdallConfig(**config_data)

