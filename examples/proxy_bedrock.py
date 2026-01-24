#!/usr/bin/env python3
"""
Bifröst as Generic Proxy - Bedrock Example

Bifröst forwards requests to ANY OpenAI-compatible endpoint.
No provider-specific code needed - just set UPSTREAM_BASE_URL.

This example shows AWS Bedrock, but the same approach works for:
- Azure OpenAI
- Google Vertex AI
- Any vLLM server
- Any OpenAI-compatible API
"""

import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

# Fail fast if no configuration
if not os.getenv("UPSTREAM_BASE_URL"):
    raise ValueError(
        "UPSTREAM_BASE_URL required. Set to Bedrock OpenAI-compatible endpoint.\n"
        "Example: https://bedrock-runtime.us-east-1.amazonaws.com/v1"
    )

if not os.getenv("UPSTREAM_API_KEY"):
    raise ValueError("UPSTREAM_API_KEY required for Bedrock authentication")


async def main():
    """
    Use Heimdall guards with AWS Bedrock models.

    Architecture:
        Your App → Bifröst (Guards) → AWS Bedrock → Claude/Llama/Titan
    """

    print("🛡️  Heimdall + AWS Bedrock Proxy\n")
    print(f"Upstream: {os.getenv('UPSTREAM_BASE_URL')}")
    print("Policy: enterprise_default_v1\n")

    # Point to Bifröst gateway (NOT directly to Bedrock)
    client = AsyncOpenAI(
        base_url="http://localhost:8000/v1",  # ← Bifröst
        api_key="dummy"  # ← Not used, Bifröst uses UPSTREAM_API_KEY
    )

    # Example 1: Use Claude on Bedrock with guards
    print("=" * 60)
    print("Example 1: Claude 3 on Bedrock (with PII guard)")
    print("=" * 60)

    try:
        response = await client.chat.completions.create(
            model="anthropic.claude-3-sonnet-20240229-v1:0",  # Bedrock model ID
            messages=[
                {
                    "role": "user",
                    "content": "My email is john@example.com, can you help?"
                }
            ],
            extra_headers={
                "x-policy-id": "enterprise_default_v1"  # Heimdall policy
            }
        )

        print(f"✅ Response: {response.choices[0].message.content}")
        print(f"Model: {response.model}")

        # Check if guards ran
        if hasattr(response, 'guardrails'):
            guards = response.guardrails
            print("\nGuards executed:")
            print(f"  Input: {len(guards['input_guards'])} guards")
            print(f"  Output: {len(guards['output_guards'])} guards")
            print(f"  Total time: {guards['execution_time_ms']['input']:.1f}ms")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Example 2: Blocked content
    print("\n" + "=" * 60)
    print("Example 2: Toxic content (blocked by guards)")
    print("=" * 60)

    try:
        response = await client.chat.completions.create(
            model="anthropic.claude-3-sonnet-20240229-v1:0",
            messages=[
                {
                    "role": "user",
                    "content": "You're a stupid idiot!"
                }
            ],
            extra_headers={"x-policy-id": "enterprise_default_v1"}
        )
        print("❌ Should have been blocked!")

    except Exception as e:
        print("✅ Correctly blocked by guards")
        print(f"   Reason: {e}")

    # Example 3: Llama on Bedrock
    print("\n" + "=" * 60)
    print("Example 3: Llama 3 on Bedrock")
    print("=" * 60)

    try:
        response = await client.chat.completions.create(
            model="meta.llama3-70b-instruct-v1:0",  # Bedrock Llama
            messages=[
                {
                    "role": "user",
                    "content": "What's 2+2?"
                }
            ],
            extra_headers={"x-policy-id": "enterprise_default_v1"}
        )

        print(f"✅ Response: {response.choices[0].message.content}")
        print(f"Model: {response.model}")

    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 60)
    print("🎉 Benefits:")
    print("  • Guards run on ALL models (Claude, Llama, Titan)")
    print("  • Zero code changes to switch providers")
    print("  • Consistent policy enforcement")
    print("  • Works with streaming too")
    print("=" * 60)


if __name__ == "__main__":
    # Configuration check
    print("\n📋 Configuration:")
    print("  Bifröst: http://localhost:8000/v1")
    print(f"  Upstream: {os.getenv('UPSTREAM_BASE_URL', 'NOT SET')}")
    print(f"  API Key: {'✓ Set' if os.getenv('UPSTREAM_API_KEY') else '✗ Missing'}")
    print()

    # Instructions
    if not os.getenv("UPSTREAM_BASE_URL"):
        print("⚠️  Setup required:")
        print("   1. Set UPSTREAM_BASE_URL to Bedrock endpoint")
        print("   2. Set UPSTREAM_API_KEY for authentication")
        print("   3. Start Bifröst: python -m bifrost.main")
        print("   4. Run this example")
        exit(1)

    asyncio.run(main())

