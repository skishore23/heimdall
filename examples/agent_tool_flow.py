"""
Agentic example: guard tool calls before they reach external systems.

Run this script after launching Bifröst (or the SDK) and load
`policies/agent_tool_guard.yaml` before calling `guard_tool`.

This example keeps every call pinned to `https://trusted.example.com`
while showcasing a tool that fetches URLs on behalf of an agent.
"""

import asyncio

from heimdall_sdk import GuardViolation, HeimdallSDK


async def open_internal_url(url: str) -> str:
    """Simulated tool that would call an internal endpoint."""
    await asyncio.sleep(0.01)  # pretend there is a network hop
    return f"Fetched {len(url)} bytes from {url}"


async def main():
    sdk = HeimdallSDK()
    await sdk.load_policy("policies/agent_tool_guard.yaml")

    # Allowed call
    try:
        result = await sdk.guard_tool(
            open_internal_url,
            "agent_tool_guard",
            url="https://trusted.example.com/api/v1/heartbeat"
        )
        print("Allowed tool call:", result)
    except GuardViolation as violation:
        print("Allowed call blocked unexpectedly:", violation)

    # Blocked call (violates forbidden pattern)
    try:
        await sdk.guard_tool(
            open_internal_url,
            "agent_tool_guard",
            url="https://untrusted.example.com/exfiltrate"
        )
    except GuardViolation as violation:
        print("Blocked the rogue tool call:", violation.violations)

    await sdk.close()


if __name__ == "__main__":
    asyncio.run(main())
