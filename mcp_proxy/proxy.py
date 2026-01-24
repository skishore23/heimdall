"""
MCP Proxy Core Implementation

Handles JSON-RPC message routing, guard enforcement, and upstream communication.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

from bifrost.cache import PolicyCache
from heimdall import run_tiered_guards

logger = logging.getLogger(__name__)


class MCPTransport(Enum):
    """MCP transport protocols"""
    HTTP = "http"
    WEBSOCKET = "websocket"
    STDIO = "stdio"


@dataclass
class MCPProxyConfig:
    """Configuration for MCP proxy"""
    # Proxy settings
    listen_host: str = "0.0.0.0"  # nosec B104 - intentional for proxy server
    listen_port: int = 3001
    transport: MCPTransport = MCPTransport.WEBSOCKET

    # Upstream MCP server
    upstream_url: str = "ws://localhost:3000"
    upstream_timeout: float = 30.0

    # Guard settings
    enable_guards: bool = True
    default_policy: str = "mcp_default_v1"
    guard_timeout: float = 1.0

    # Performance settings
    max_concurrent_requests: int = 100
    request_buffer_size: int = 1024 * 1024  # 1MB

    # Logging
    log_requests: bool = True
    log_responses: bool = True


class MCPProxy:
    """
    MCP Pass-through Proxy with Guard Hooks

    Provides transparent proxying of MCP JSON-RPC requests with optional
    guardrails enforcement on method calls and responses.
    """

    def __init__(self, config: MCPProxyConfig):
        self.config = config
        self.policy_cache = PolicyCache()

        # Connection management
        self.client_connections: dict[str, WebSocketServerProtocol] = {}
        self.upstream_connection: websockets.WebSocketClientProtocol | None = None

        # Request tracking
        self.pending_requests: dict[str, dict[str, Any]] = {}
        self.request_semaphore = asyncio.Semaphore(config.max_concurrent_requests)

        # Statistics
        self.stats = {
            "requests_total": 0,
            "requests_blocked": 0,
            "responses_modified": 0,
            "guard_violations": 0,
            "upstream_errors": 0
        }

    async def start(self):
        """Start the MCP proxy server"""
        if self.config.transport == MCPTransport.WEBSOCKET:
            await self._start_websocket_server()
        elif self.config.transport == MCPTransport.HTTP:
            await self._start_http_server()
        else:
            raise ValueError(f"Unsupported transport: {self.config.transport}")

    async def _start_websocket_server(self):
        """Start WebSocket server for MCP proxy"""
        logger.info("Starting MCP WebSocket proxy on %s:%s", self.config.listen_host, self.config.listen_port)
        logger.info("Upstream: %s", self.config.upstream_url)

        async def handle_client(websocket, path):
            client_id = str(uuid.uuid4())
            self.client_connections[client_id] = websocket

            try:
                await self._handle_client_connection(client_id, websocket)
            finally:
                self.client_connections.pop(client_id, None)

        server = await websockets.serve(
            handle_client,
            self.config.listen_host,
            self.config.listen_port
        )

        # Maintain upstream connection
        asyncio.create_task(self._maintain_upstream_connection())

        await server.wait_closed()

    async def _maintain_upstream_connection(self):
        """Maintain persistent connection to upstream MCP server"""
        while True:
            try:
                if not self.upstream_connection or self.upstream_connection.closed:
                    logger.info("Connecting to upstream MCP server: %s", self.config.upstream_url)
                    self.upstream_connection = await websockets.connect(
                        self.config.upstream_url,
                        timeout=self.config.upstream_timeout
                    )
                    logger.info("Connected to upstream MCP server")

                    # Handle upstream messages
                    asyncio.create_task(self._handle_upstream_messages())

                await asyncio.sleep(5)  # Check connection every 5 seconds

            except Exception as e:
                logger.error("Upstream connection error: %s", e)
                self.upstream_connection = None
                await asyncio.sleep(10)  # Retry after 10 seconds

    async def _handle_client_connection(self, client_id: str, websocket: WebSocketServerProtocol):
        """Handle messages from a client connection"""
        try:
            async for message in websocket:
                await self._process_client_message(client_id, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client %s disconnected", client_id)
        except Exception as e:
            logger.error("Client connection error: %s", e)

    async def _process_client_message(self, client_id: str, message: str):
        """Process a message from client and forward to upstream"""
        async with self.request_semaphore:
            try:
                # Parse JSON-RPC message
                rpc_message = json.loads(message)
                request_id = rpc_message.get("id", str(uuid.uuid4()))

                self.stats["requests_total"] += 1

                # Apply request guards
                if self.config.enable_guards:
                    guard_result = await self._apply_request_guards(rpc_message, client_id)
                    if guard_result["blocked"]:
                        await self._send_error_response(
                            client_id, request_id,
                            "Request blocked by policy",
                            guard_result["violations"]
                        )
                        return

                    # Use modified message if guards changed it
                    rpc_message = guard_result["message"]

                # Track request for response correlation
                self.pending_requests[request_id] = {
                    "client_id": client_id,
                    "original_message": rpc_message,
                    "timestamp": time.time()
                }

                # Forward to upstream
                if self.upstream_connection and not self.upstream_connection.closed:
                    await self.upstream_connection.send(json.dumps(rpc_message))
                else:
                    await self._send_error_response(
                        client_id, request_id,
                        "Upstream server unavailable"
                    )

            except json.JSONDecodeError as e:
                logger.error("Invalid JSON from client %s: %s", client_id, e)
            except Exception as e:
                logger.error("Error processing client message: %s", e)

    async def _handle_upstream_messages(self):
        """Handle messages from upstream MCP server"""
        try:
            async for message in self.upstream_connection:
                await self._process_upstream_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Upstream server disconnected")
        except Exception as e:
            logger.error("Upstream message error: %s", e)

    async def _process_upstream_message(self, message: str):
        """Process response from upstream and forward to client"""
        try:
            rpc_response = json.loads(message)
            request_id = rpc_response.get("id")

            if request_id not in self.pending_requests:
                logger.warning("Received response for unknown request: %s", request_id)
                return

            request_info = self.pending_requests.pop(request_id)
            client_id = request_info["client_id"]

            # Apply response guards
            if self.config.enable_guards:
                guard_result = await self._apply_response_guards(
                    rpc_response,
                    request_info["original_message"],
                    client_id
                )

                if guard_result["blocked"]:
                    await self._send_error_response(
                        client_id, request_id,
                        "Response blocked by policy",
                        guard_result["violations"]
                    )
                    return

                # Use modified response if guards changed it
                rpc_response = guard_result["message"]
                if guard_result["modified"]:
                    self.stats["responses_modified"] += 1

            # Forward to client
            client_ws = self.client_connections.get(client_id)
            if client_ws and not client_ws.closed:
                await client_ws.send(json.dumps(rpc_response))

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON from upstream: %s", e)
        except Exception as e:
            logger.error("Error processing upstream message: %s", e)

    async def _apply_request_guards(self, message: dict[str, Any], client_id: str) -> dict[str, Any]:
        """Apply guards to incoming request"""
        try:
            # Get policy for client
            policy_id = self.config.default_policy
            compiled_guards, policy_metadata = await self.policy_cache.get_policy(
                tenant_id=client_id,
                policy_id=policy_id
            )

            # Create context for guards
            context = {
                "phase": "mcp_request",
                "method": message.get("method"),
                "params": message.get("params", {}),
                "client_id": client_id,
                "message": message
            }

            # Run guards
            exec_result = await run_tiered_guards(
                guards={"mcp_request": compiled_guards.get("mcp_request")},
                context=context,
                enabled_tiers=["T0", "T1"]  # Skip T2 for MCP (latency sensitive)
            )

            # ExecutionResult has violations attribute
            if exec_result.violations:
                self.stats["guard_violations"] += len(exec_result.violations)
                self.stats["requests_blocked"] += 1

                return {
                    "blocked": True,
                    "violations": exec_result.violations,
                    "message": message
                }

            return {
                "blocked": False,
                "violations": [],
                "message": exec_result.context.get("message", message)
            }

        except Exception as e:
            logger.error("Guard error: %s", e)
            # Fail open - allow request if guards fail
            return {
                "blocked": False,
                "violations": [],
                "message": message
            }

    async def _apply_response_guards(
        self,
        response: dict[str, Any],
        original_request: dict[str, Any],
        client_id: str
    ) -> dict[str, Any]:
        """Apply guards to outgoing response"""
        try:
            # Get policy for client
            policy_id = self.config.default_policy
            compiled_guards, policy_metadata = await self.policy_cache.get_policy(
                tenant_id=client_id,
                policy_id=policy_id
            )

            # Create context for guards
            context = {
                "phase": "mcp_response",
                "method": original_request.get("method"),
                "request_params": original_request.get("params", {}),
                "response": response,
                "client_id": client_id
            }

            # Run guards
            exec_result = await run_tiered_guards(
                guards={"mcp_response": compiled_guards.get("mcp_response")},
                context=context,
                enabled_tiers=["T0", "T1"]
            )

            # ExecutionResult has violations attribute
            if exec_result.violations:
                self.stats["guard_violations"] += len(exec_result.violations)

                return {
                    "blocked": True,
                    "modified": False,
                    "violations": exec_result.violations,
                    "message": response
                }

            # Check if response was modified
            modified_response = exec_result.context.get("response", response)
            was_modified = modified_response != response

            return {
                "blocked": False,
                "modified": was_modified,
                "violations": [],
                "message": modified_response
            }

        except Exception as e:
            logger.error("Response guard error: %s", e)
            # Fail open - allow response if guards fail
            return {
                "blocked": False,
                "modified": False,
                "violations": [],
                "message": response
            }

    async def _send_error_response(
        self,
        client_id: str,
        request_id: str,
        error_message: str,
        violations: list[dict[str, Any]] = None
    ):
        """Send JSON-RPC error response to client"""
        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32603,  # Internal error
                "message": error_message,
                "data": {
                    "violations": violations or [],
                    "timestamp": time.time()
                }
            }
        }

        client_ws = self.client_connections.get(client_id)
        if client_ws and not client_ws.closed:
            await client_ws.send(json.dumps(error_response))

    def get_stats(self) -> dict[str, Any]:
        """Get proxy statistics"""
        return {
            **self.stats,
            "active_connections": len(self.client_connections),
            "pending_requests": len(self.pending_requests),
            "upstream_connected": bool(
                self.upstream_connection and not self.upstream_connection.closed
            )
        }
