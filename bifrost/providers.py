"""
Provider client helpers for bifrost routes
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


async def get_provider_client(body: dict[str, Any], tenant_id: str, settings: Any):
    """
    Get OpenAI-compatible provider client based on configuration

    Args:
        body: Request body (may contain model or other hints)
        tenant_id: Tenant identifier
        settings: Application settings with provider configuration

    Returns:
        Configured AsyncOpenAI client
    """
    from openai import AsyncOpenAI

    # Determine base URL and API key
    if settings.upstream_base_url:
        base_url = settings.upstream_base_url
        api_key = settings.upstream_api_key or settings.openai_api_key
    else:
        base_url = "https://api.openai.com/v1"
        api_key = settings.openai_api_key

    if not api_key:
        raise ValueError("API key required (UPSTREAM_API_KEY or OPENAI_API_KEY)")

    return AsyncOpenAI(base_url=base_url, api_key=api_key)

