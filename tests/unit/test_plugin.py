"""
Tests for plugin system
"""

import pytest

from heimdall.plugin import (
    PluginRegistry,
    validate_plugin_compatibility,
)
from heimdall.types import Ctx, Either, Guard, Right_


class TestPlugin:
    """Test plugin implementation"""

    @property
    def plugin_id(self) -> str:
        return "test.plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def abi_version(self) -> str:
        return "0.9"

    def get_guards(self):
        return {
            "test.plugin.example": self.create_example_guard
        }

    def get_guard_metadata(self, guard_id: str):
        return {
            "tier": "T0",
            "description": "Example guard",
            "performance_budget_ms": 5.0
        }

    def create_example_guard(self) -> Guard:
        async def guard(ctx: Ctx) -> Either:
            return Right_(ctx)
        return guard


def test_plugin_protocol():
    """Test that plugin implements protocol correctly"""
    plugin = TestPlugin()

    assert plugin.plugin_id == "test.plugin"
    assert plugin.version == "1.0.0"
    assert plugin.abi_version == "0.9"

    guards = plugin.get_guards()
    assert "test.plugin.example" in guards

    metadata = plugin.get_guard_metadata("test.plugin.example")
    assert metadata["tier"] == "T0"


def test_validate_plugin_compatibility_success():
    """Test plugin compatibility validation - compatible"""
    plugin = TestPlugin()

    is_compatible = validate_plugin_compatibility(plugin, current_abi="0.9")
    assert is_compatible is True


def test_validate_plugin_compatibility_major_mismatch():
    """Test plugin compatibility validation - major version mismatch"""

    class IncompatiblePlugin(TestPlugin):
        @property
        def abi_version(self) -> str:
            return "1.0"  # Major version 1, incompatible with 0.9

    plugin = IncompatiblePlugin()

    is_compatible = validate_plugin_compatibility(plugin, current_abi="0.9")
    assert is_compatible is False


def test_validate_plugin_compatibility_newer_minor():
    """Test plugin compatibility validation - newer minor version"""

    class NewerPlugin(TestPlugin):
        @property
        def abi_version(self) -> str:
            return "0.10"  # Newer minor, should not be compatible

    plugin = NewerPlugin()

    is_compatible = validate_plugin_compatibility(plugin, current_abi="0.9")
    assert is_compatible is False


def test_plugin_registry_register():
    """Test registering a plugin"""
    registry = PluginRegistry()
    plugin = TestPlugin()

    registry.register_plugin(plugin)

    assert "test.plugin" in registry.list_plugins()


def test_plugin_registry_duplicate_error():
    """Test that registering duplicate plugin raises error"""
    registry = PluginRegistry()
    plugin = TestPlugin()

    registry.register_plugin(plugin)

    with pytest.raises(ValueError, match="already registered"):
        registry.register_plugin(plugin)


def test_plugin_registry_incompatible_error():
    """Test that incompatible plugin raises error"""
    registry = PluginRegistry()

    class IncompatiblePlugin(TestPlugin):
        @property
        def abi_version(self) -> str:
            return "1.0"

    plugin = IncompatiblePlugin()

    with pytest.raises(ValueError, match="incompatible"):
        registry.register_plugin(plugin)


def test_plugin_registry_unregister():
    """Test unregistering a plugin"""
    registry = PluginRegistry()
    plugin = TestPlugin()

    registry.register_plugin(plugin)
    assert "test.plugin" in registry.list_plugins()

    registry.unregister_plugin("test.plugin")
    assert "test.plugin" not in registry.list_plugins()


def test_plugin_registry_get():
    """Test getting a plugin"""
    registry = PluginRegistry()
    plugin = TestPlugin()

    registry.register_plugin(plugin)

    retrieved = registry.get_plugin("test.plugin")
    assert retrieved.plugin_id == "test.plugin"


def test_plugin_registry_get_not_found():
    """Test getting non-existent plugin"""
    registry = PluginRegistry()

    with pytest.raises(KeyError):
        registry.get_plugin("nonexistent.plugin")

