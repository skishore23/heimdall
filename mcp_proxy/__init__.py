"""
MCP Pass-through Proxy

JSON-RPC relay with guard hooks for Model Context Protocol (MCP) integration.
Provides transparent proxying of MCP requests with guardrails enforcement.
"""

from .handlers import MCPRequestHandler, MCPResponseHandler
from .middleware import GuardMiddleware, LoggingMiddleware
from .proxy import MCPProxy, MCPProxyConfig
from .server import start_mcp_proxy

__all__ = [
    "MCPProxy",
    "MCPProxyConfig",
    "MCPRequestHandler",
    "MCPResponseHandler",
    "GuardMiddleware",
    "LoggingMiddleware",
    "start_mcp_proxy"
]
