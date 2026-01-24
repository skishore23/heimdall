#!/usr/bin/env python3
"""
Guardrails Gateway - Drop-in OpenAI Proxy

The easiest way: Just point your OpenAI client to the gateway.
Zero code changes to your app!
"""

import asyncio

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

# Note: Client doesn't need API key - Bifröst handles upstream authentication
# Bifröst needs OPENAI_API_KEY or UPSTREAM_API_KEY in its .env


async def main():
    """Customer perspective: Change base_url, that's it"""

    print("🛡️  Guardrails Gateway - Zero Code Changes\n")

    # The ONLY change: point to gateway instead of OpenAI
    client = AsyncOpenAI(
        base_url="http://localhost:8000/v1",  # ← Gateway, not OpenAI
        api_key="any-value"  # ← Not validated by Bifröst (it's a trusted proxy)
    )

    # Note: Bifröst uses UPSTREAM_API_KEY (from .env) to connect to OpenAI
    # Client API key is not used - authentication is via x-policy-id header

    # Everything else is normal OpenAI code:

    print("✅ Example 1: Safe message")
    print("-" * 50)
    response = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello!"}],
        extra_headers={"x-policy-id": "enterprise_default_v1"}  # Which policy
    )
    print(f"Response: {response.choices[0].message.content}")

    # Check guardrails metadata (added by gateway)
    if hasattr(response, 'guardrails'):
        guards = response.guardrails
        print(f"Guards: {len(guards['input_guards'])} input, {len(guards['output_guards'])} output")
        print(f"Latency: {guards['execution_time_ms']['input']:.1f}ms\n")

    print("🚫 Example 2: Toxic content (blocked)")
    print("-" * 50)
    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "You're an idiot!"}],
            extra_headers={"x-policy-id": "enterprise_default_v1"}
        )
        print("❌ Should have been blocked!")
    except Exception:
        print("✅ Correctly blocked\n")

    print("🔒 Example 3: PII redaction")
    print("-" * 50)
    response = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Contact me at john@example.com"}],
        extra_headers={"x-policy-id": "enterprise_default_v1"}
    )
    print(f"Response: {response.choices[0].message.content}")
    print("Note: PII automatically redacted!\n")

    print("=" * 50)
    print("Benefits of Gateway:")
    print("  • Zero code changes - just change base_url")
    print("  • Works with any OpenAI SDK (Python, JS, etc.)")
    print("  • Change policies without deploying")
    print("  • Get metrics and logs for free")
    print("=" * 50)


if __name__ == "__main__":
    print("\n📋 Setup Requirements:")
    print("   1. Bifröst must be running: python -m bifrost.main")
    print("   2. Bifröst .env must have: OPENAI_API_KEY=sk-...")
    print("   3. This client needs no API key!\n")

    asyncio.run(main())

