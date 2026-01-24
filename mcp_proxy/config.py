"""
Configuration for MCP Proxy
"""

from pydantic_settings import BaseSettings


class MCPProxyConfig(BaseSettings):
    """MCP Proxy configuration"""

    upstream_url: str
    policy_path: str
    host: str = "localhost"
    port: int = 9000

    class Config:
        env_file = ".env"
        case_sensitive = False
