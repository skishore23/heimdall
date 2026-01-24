#!/usr/bin/env python3
"""
Guardrails Quickstart - The Only Example You Need

Shows the ONE way to use guardrails: wrap your LLM calls.
"""

import asyncio
import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

# Fail fast if no API key
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY required in .env file")


async def main():
    """Customer perspective: Just wrap your LLM call"""

    print("🛡️ Guardrails Quickstart\n")

    # Step 1: Import SDK
    from heimdall_sdk import HeimdallSDK

    # Step 2: Load policy
    sdk = HeimdallSDK()
    await sdk.load_policy("policies/enterprise_default_v1.yaml")

    # Step 3: Define your LLM call
    client = AsyncOpenAI()

    async def call_llm(**kwargs):
        """Your existing LLM call - unchanged"""
        return await client.chat.completions.create(**kwargs)

    # Step 4: Wrap it with guardrails
    def guarded_llm(**kwargs):
        return sdk.wrap_llm(
            call_llm,
            "enterprise_default_v1",  # Policy ID
            **kwargs
        )

    # That's it! Now use it:

    print("✅ Example 1: Safe message (passes)")
    print("-" * 50)
    try:
        response = await guarded_llm(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello! How are you?"}],
            max_tokens=50
        )
        print(f"Response: {response.choices[0].message.content}\n")
    except Exception as e:
        print(f"Error: {e}\n")

    print("🚫 Example 2: Toxic content (blocked)")
    print("-" * 50)
    try:
        response = await guarded_llm(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "You're an idiot!"}],
            max_tokens=50
        )
        print("❌ Should have been blocked!")
    except Exception as e:
        print(f"✅ Correctly blocked: {type(e).__name__}\n")

    print("🔒 Example 3: PII redaction (automatic)")
    print("-" * 50)
    try:
        response = await guarded_llm(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "My email is john@example.com"}],
            max_tokens=50
        )
        print(f"Response: {response.choices[0].message.content}")
        print("Note: Email was redacted before reaching OpenAI!\n")
    except Exception as e:
        print(f"Error: {e}\n")

    await sdk.close()

    print("\n" + "=" * 50)
    print("That's it! Three lines of code:")
    print("  1. sdk = HeimdallSDK()")
    print("  2. await sdk.load_policy('your_policy.yaml')")
    print("  3. await sdk.wrap_llm(your_llm_function, policy_id)")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())

