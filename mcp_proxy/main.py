"""
Main entry point for MCP proxy with guard enforcement
"""

import asyncio
import logging

from .config import MCPProxyConfig
from .proxy import MCPProxy


async def main():
    """Main entry point for MCP proxy"""
    import argparse

    parser = argparse.ArgumentParser(description="MCP Proxy with Guard Enforcement")
    parser.add_argument("--upstream", required=True, help="Upstream MCP server URL")
    parser.add_argument("--policy", required=True, help="Policy YAML file path")
    parser.add_argument("--port", type=int, default=9000, help="Proxy port")
    parser.add_argument("--host", default="localhost", help="Proxy host")
    parser.add_argument("--log-level", default="INFO", help="Log level")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create config
    config = MCPProxyConfig(
        upstream_url=args.upstream,
        policy_path=args.policy,
        host=args.host,
        port=args.port
    )

    # Create and run proxy
    proxy = MCPProxy(config)

    try:
        await proxy.start()
    except KeyboardInterrupt:
        logging.info("Shutting down MCP proxy...")
    finally:
        await proxy.stop()


if __name__ == "__main__":
    asyncio.run(main())
