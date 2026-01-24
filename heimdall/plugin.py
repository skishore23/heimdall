"""
Guard Pack Plugin ABI

Provides a stable interface for third-party guard pack plugins.
"""

from abc import abstractmethod
from collections.abc import Callable
from typing import Any, Protocol

from .types import Guard


class GuardPlugin(Protocol):
    """
    Plugin ABI for guard packs

    Third-party guard packs must implement this protocol to be compatible.
    """

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique plugin identifier (e.g., 'custom_corp.security')"""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version (SemVer format)"""
        ...

    @property
    @abstractmethod
    def abi_version(self) -> str:
        """ABI version this plugin targets (e.g., '0.9')"""
        ...

    @abstractmethod
    def get_guards(self) -> dict[str, Callable[..., Guard]]:
        """
        Return dictionary of guard_id -> factory

        Returns:
            Dict mapping guard IDs to factory functions
        """
        ...

    @abstractmethod
    def get_guard_metadata(self, guard_id: str) -> dict[str, Any]:
        """
        Get metadata for a specific guard

        Args:
            guard_id: Guard identifier

        Returns:
            Metadata dict with keys: tier, description, performance_budget_ms, etc.
        """
        ...


def validate_plugin_compatibility(plugin: GuardPlugin, current_abi: str = "0.9") -> bool:
    """
    Validate plugin ABI compatibility

    Args:
        plugin: Plugin to validate
        current_abi: Current ABI version

    Returns:
        True if compatible, False otherwise
    """
    # Simple major.minor compatibility check
    plugin_major, plugin_minor = map(int, plugin.abi_version.split('.')[:2])
    current_major, current_minor = map(int, current_abi.split('.')[:2])

    # Compatible if major versions match and plugin minor <= current minor
    return plugin_major == current_major and plugin_minor <= current_minor


class PluginRegistry:
    """Registry for loaded plugins"""

    def __init__(self):
        self.plugins: dict[str, GuardPlugin] = {}

    def register_plugin(self, plugin: GuardPlugin) -> None:
        """
        Register a guard pack plugin

        Args:
            plugin: Plugin to register

        Raises:
            ValueError: If plugin is incompatible or already registered
        """
        if not validate_plugin_compatibility(plugin):
            raise ValueError(
                f"Plugin '{plugin.plugin_id}' ABI version {plugin.abi_version} "
                f"is incompatible with current ABI"
            )

        if plugin.plugin_id in self.plugins:
            raise ValueError(f"Plugin '{plugin.plugin_id}' is already registered")

        self.plugins[plugin.plugin_id] = plugin

        # Register guards from plugin
        from .registry import register_guard

        for guard_id, factory in plugin.get_guards().items():
            metadata = plugin.get_guard_metadata(guard_id)
            register_guard(
                guard_id=guard_id,
                factory=factory,
                tier=metadata.get('tier'),
                description=metadata.get('description'),
                performance_budget_ms=metadata.get('performance_budget_ms')
            )

    def unregister_plugin(self, plugin_id: str) -> None:
        """
        Unregister a plugin

        Args:
            plugin_id: Plugin identifier
        """
        if plugin_id not in self.plugins:
            raise ValueError(f"Plugin '{plugin_id}' is not registered")

        del self.plugins[plugin_id]

    def list_plugins(self) -> list[str]:
        """List all registered plugin IDs"""
        return list(self.plugins.keys())

    def get_plugin(self, plugin_id: str) -> GuardPlugin:
        """
        Get a registered plugin

        Args:
            plugin_id: Plugin identifier

        Returns:
            Plugin instance

        Raises:
            KeyError: If plugin not found
        """
        if plugin_id not in self.plugins:
            raise KeyError(f"Plugin '{plugin_id}' not found")
        return self.plugins[plugin_id]


# Global plugin registry
PLUGIN_REGISTRY = PluginRegistry()


def register_plugin(plugin: GuardPlugin) -> None:
    """Register a guard pack plugin"""
    PLUGIN_REGISTRY.register_plugin(plugin)


def list_plugins() -> list[str]:
    """List all registered plugins"""
    return PLUGIN_REGISTRY.list_plugins()

