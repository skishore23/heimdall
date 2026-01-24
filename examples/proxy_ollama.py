#!/usr/bin/env python3
"""
Bifröst as Proxy to Ollama (Local LLMs)

Run Heimdall guards on local open-source models via Ollama.
Perfect for development, testing, or air-gapped environments.
"""

import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()


async def main():
    """
    Use Heimdall guards with local Ollama models.

    Architecture:
        Your App → Bifröst (Guards) → Ollama → Llama/Mistral/etc.

    Setup:
        1. Install Ollama: https://ollama.ai
        2. Pull a model: ollama pull llama2
        3. Set env: export UPSTREAM_BASE_URL=http://localhost:11434/v1
        4. Start Bifröst: python -m bifrost.main
    """

    print("🛡️  Heimdall + Ollama (Local LLMs)\n")

    # Point to Bifröst gateway
    client = AsyncOpenAI(
        base_url="http://localhost:8000/v1",  # ← Bifröst
        api_key="dummy"  # ← Ollama doesn't need auth
    )

    # Example 1: Safe query
    print("=" * 60)
    print("Example 1: Safe query with local model")
    print("=" * 60)

    response = await client.chat.completions.create(
        model="llama2",  # Any Ollama model
        messages=[
            {"role": "user", "content": "What's the capital of France?"}
        ],
        extra_headers={"x-policy-id": "enterprise_default_v1"}
    )

    print(f"✅ Response: {response.choices[0].message.content}")

    # Check guards
    if hasattr(response, 'guardrails'):
        print(f"\nGuards: {len(response.guardrails['input_guards'])} input, "
              f"{len(response.guardrails['output_guards'])} output")

    # Example 2: PII detection
    print("\n" + "=" * 60)
    print("Example 2: PII redaction")
    print("=" * 60)

    response = await client.chat.completions.create(
        model="llama2",
        messages=[
            {
                "role": "user",
                "content": "Email me at alice@example.com"
            }
        ],
        extra_headers={"x-policy-id": "enterprise_default_v1"}
    )

    print(f"✅ Response: {response.choices[0].message.content}")
    print("   (Email was redacted before reaching the model)")

    # Example 3: Streaming
    print("\n" + "=" * 60)
    print("Example 3: Streaming with guards")
    print("=" * 60)

    stream = await client.chat.completions.create(
        model="llama2",
        messages=[
            {"role": "user", "content": "Count to 5"}
        ],
        stream=True,
        extra_headers={"x-policy-id": "enterprise_default_v1"}
    )

    print("Response: ", end="", flush=True)
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n")

    print("=" * 60)
    print("🎉 Benefits of Local LLMs + Guards:")
    print("  • No API costs")
    print("  • Data stays on your machine")
    print("  • Still get full guard protection")
    print("  • Perfect for development/testing")
    print("=" * 60)


if __name__ == "__main__":
    # Check configuration
    upstream = os.getenv("UPSTREAM_BASE_URL")

    if not upstream or "ollama" not in upstream.lower():
        print("⚠️  Configuration:")
        print("   Set UPSTREAM_BASE_URL=http://localhost:11434/v1")
        print()
        print("Setup:")
        print("   1. Install Ollama: https://ollama.ai")
        print("   2. Pull model: ollama pull llama2")
        print("   3. Set env:")
        print("      export UPSTREAM_BASE_URL=http://localhost:11434/v1")
        print("      export UPSTREAM_API_KEY=dummy")
        print("   4. Start Bifröst: python -m bifrost.main")
        print("   5. Run this: python examples/proxy_ollama.py")
        exit(1)

    asyncio.run(main())

