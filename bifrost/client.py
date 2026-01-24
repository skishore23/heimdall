"""
Bifröst HTTP client for CLI operations

Provides functions for:
- Status check
- Policy hot-reload
- Trace streaming
- Logs retrieval
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class BifrostClient:
    """HTTP client for Bifröst gateway"""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    async def get_status(self) -> dict[str, Any]:
        """
        Get gateway status

        Returns:
            Status information including health, version, config
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Get health
            health_resp = await client.get(f"{self.base_url}/health")
            health_resp.raise_for_status()
            health = health_resp.json()

            # Get info
            info_resp = await client.get(f"{self.base_url}/info")
            info_resp.raise_for_status()
            info = info_resp.json()

            # Get metrics
            metrics_resp = await client.get(f"{self.base_url}/metrics")
            metrics_resp.raise_for_status()
            metrics = metrics_resp.json()

            return {
                "health": health,
                "info": info,
                "metrics": metrics
            }

    async def reload_policy(self, envelope_path: str) -> dict[str, Any]:
        """
        Hot-reload a policy envelope

        Args:
            envelope_path: Path to policy envelope JSON

        Returns:
            Reload result
        """
        # Load envelope
        with open(envelope_path) as f:
            envelope_data = json.load(f)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/admin/reload",
                json=envelope_data
            )
            resp.raise_for_status()
            return resp.json()

    async def stream_traces(
        self,
        guard_id: str | None = None,
        decision: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream decision traces via SSE

        Args:
            guard_id: Optional guard ID filter
            decision: Optional decision filter (pass/block)

        Yields:
            Trace events
        """
        params = {}
        if guard_id:
            params['guard_id'] = guard_id
        if decision:
            params['decision'] = decision

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                'GET',
                f"{self.base_url}/trace/stream",
                params=params
            ) as resp:
                resp.raise_for_status()

                async for line in resp.aiter_lines():
                    if line.startswith('data: '):
                        data = line[6:]  # Remove 'data: ' prefix
                        try:
                            trace = json.loads(data)
                            yield trace
                        except json.JSONDecodeError:
                            continue

    async def get_trace_list(
        self,
        guard_id: str | None = None,
        decision: str | None = None,
        limit: int = 100
    ) -> dict[str, Any]:
        """
        Get recent traces

        Args:
            guard_id: Optional guard ID filter
            decision: Optional decision filter
            limit: Maximum number of traces

        Returns:
            List of traces
        """
        params = {'limit': limit}
        if guard_id:
            params['guard_id'] = guard_id
        if decision:
            params['decision'] = decision

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}/trace/list",
                params=params
            )
            resp.raise_for_status()
            return resp.json()

    async def clear_traces(self) -> dict[str, Any]:
        """Clear all collected traces"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/trace/clear")
            resp.raise_for_status()
            return resp.json()

