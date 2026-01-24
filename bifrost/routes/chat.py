"""
Chat completions API route - Thin HTTP wrapper around SDK

Gateway is just an HTTP proxy to the SDK with streaming support.
"""

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from heimdall import get_violations, is_left
from heimdall_sdk import GuardViolation, HeimdallSDK

from ..config import Settings
from ..guard_metadata import (
    build_guards_metadata,
    mark_guard_as_blocked,
)
from ..logging import GuardLogger, RequestLogger

router = APIRouter()
request_logger = RequestLogger()
guard_logger = GuardLogger()


def get_upstream_config(settings: Settings) -> tuple[str, str | None]:
    """
    Determine upstream base_url and API key for proxy mode.

    Returns:
        (base_url, api_key) tuple

    Priority:
        1. UPSTREAM_BASE_URL + UPSTREAM_API_KEY (explicit proxy config)
        2. OPENAI_API_KEY + default OpenAI URL (no fallback)
    """
    if settings.upstream_base_url:
        api_key = settings.upstream_api_key or settings.openai_api_key
        if not api_key:
            raise ValueError("API key required when UPSTREAM_BASE_URL is set")
        return settings.upstream_base_url, api_key

    # Default to OpenAI (fail fast if API key missing)
    api_key = settings.openai_api_key
    if not api_key:
        raise ValueError("OPENAI_API_KEY required")

    return "https://api.openai.com/v1", api_key


@router.post("/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions with guardrails and streaming"""
    request_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        # Parse request
        body = await request.json()
        tenant_id = request.headers.get("x-tenant-id", "default")
        policy_id = request.headers.get("x-policy-id")
        trace_id = request.headers.get("x-trace-id", request_id)
        is_streaming = body.get("stream", False)

        if not policy_id:
            raise HTTPException(status_code=400, detail="x-policy-id header required")

        # Get policy from cache
        policy_cache = request.app.state.policy_cache
        compiled_guards, policy_metadata = await policy_cache.get_policy(
            tenant_id=tenant_id,
            policy_id=policy_id
        )

        # Create SDK instance with compiled guards
        sdk = HeimdallSDK()
        sdk.loaded_policies[policy_id] = {
            "compiled": compiled_guards,
            "metadata": policy_metadata
        }

        # Handle streaming vs non-streaming
        if is_streaming:
            return await handle_streaming(
                sdk, request, body, policy_id, policy_metadata,
                compiled_guards, tenant_id, trace_id, request_id, start_time
            )
        else:
            return await handle_non_streaming(
                sdk, request, body, policy_id, policy_metadata,
                tenant_id, trace_id, request_id, start_time
            )

    except Exception as e:
        response_time = time.time() - start_time
        await request_logger.log_request(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            headers=dict(request.headers),
            status_code=500,
            response_time=response_time
        )
        raise HTTPException(status_code=500, detail=str(e))


async def handle_streaming(
    sdk: HeimdallSDK,
    request: Request,
    body: dict[str, Any],
    policy_id: str,
    policy_metadata: dict[str, Any],
    compiled_guards: dict[str, Any],
    tenant_id: str,
    trace_id: str,
    request_id: str,
    start_time: float
):
    """Handle streaming responses with real-time guard checking"""

    async def stream_generator():
        """Generate streaming response with guard enforcement"""
        from openai import AsyncOpenAI

        # Get upstream configuration (Bedrock, Azure, Ollama, etc.)
        base_url, api_key = get_upstream_config(request.app.state.settings)
        client = AsyncOpenAI(base_url=base_url, api_key=api_key)

        try:
            # Send initial metadata
            input_guards = build_guards_metadata(policy_metadata, "input")
            output_guards = build_guards_metadata(policy_metadata, "output")

            metadata_chunk = {
                "guardrails": {
                    "input_guards": input_guards,
                    "output_guards": output_guards,
                    "policy_id": policy_id
                }
            }
            yield f"data: {json.dumps(metadata_chunk)}\n\n"

            # Stream LLM response
            stream = await client.chat.completions.create(**body)

            accumulated_text = ""
            window_size = request.app.state.settings.streaming_window_size

            async for chunk in stream:
                # Extract content
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    accumulated_text += token

                    # Check guards on sliding window (fast guards only)
                    if len(accumulated_text) > window_size:
                        window = accumulated_text[-window_size:]

                        # Quick check using SDK
                        output_guard = compiled_guards.get("output")
                        if output_guard:
                            result = await output_guard({"phase": "output", "output": window})
                            if is_left(result):
                                violations = get_violations(result)
                                # Send block notification
                                block_chunk = {
                                    "error": {
                                        "type": "policy_violation",
                                        "message": "Content blocked during streaming",
                                        "violations": violations
                                    }
                                }
                                yield f"data: {json.dumps(block_chunk)}\n\n"
                                yield "data: [DONE]\n\n"
                                return

                # Forward chunk
                chunk_dict = chunk.model_dump() if hasattr(chunk, 'model_dump') else chunk
                yield f"data: {json.dumps(chunk_dict)}\n\n"

            yield "data: [DONE]\n\n"

        except GuardViolation as e:
            error_chunk = {
                "error": {
                    "type": "policy_violation",
                    "message": str(e),
                    "trace_id": trace_id
                }
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "x-policy-id": policy_id,
            "x-tenant-id": tenant_id,
            "x-trace-id": trace_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


async def handle_non_streaming(
    sdk: HeimdallSDK,
    request: Request,
    body: dict[str, Any],
    policy_id: str,
    policy_metadata: dict[str, Any],
    tenant_id: str,
    trace_id: str,
    request_id: str,
    start_time: float
):
    """Handle non-streaming responses"""

    # Define LLM call function
    async def call_upstream_llm(**kwargs):
        """Call upstream LLM (OpenAI, Bedrock, Azure, Ollama, etc.)"""
        from openai import AsyncOpenAI

        # Get upstream configuration
        base_url, api_key = get_upstream_config(request.app.state.settings)
        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        return await client.chat.completions.create(**kwargs)

    try:
        input_guard_start = time.time()
        response = await sdk.wrap_llm(call_upstream_llm, policy_id, **body)
        input_guard_time = (time.time() - input_guard_start) * 1000

        # Build guard metadata for response
        input_guards = build_guards_metadata(policy_metadata, "input")
        output_guards = build_guards_metadata(policy_metadata, "output")

        # Add guardrails info to response
        response_dict = response.model_dump() if hasattr(response, 'model_dump') else response
        response_dict["guardrails"] = {
            "input_guards": input_guards,
            "output_guards": output_guards,
            "execution_time_ms": {
                "input": input_guard_time,
                "output": (time.time() - start_time - input_guard_time/1000) * 1000
            },
            "policy_id": policy_id,
            "total_guards_executed": len(input_guards) + len(output_guards)
        }

        # Log success
        response_time = time.time() - start_time
        await request_logger.log_request(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            headers=dict(request.headers),
            body=body,
            status_code=200,
            response_time=response_time,
            tenant_id=tenant_id,
            policy_id=policy_id,
            policy_hash=policy_metadata.get("hash", "unknown")
        )

        return JSONResponse(
            content=response_dict,
            headers={
                "x-policy-id": policy_id,
                "x-policy-hash": f"sha256:{policy_metadata.get('hash', 'unknown')}",
                "x-tenant-id": tenant_id,
                "x-trace-id": trace_id
            }
        )

    except GuardViolation as e:
        # Guard blocked the request
        violations = e.violations if hasattr(e, 'violations') else []

        # Build guard metadata and mark violation
        input_guards = build_guards_metadata(policy_metadata, "input")
        if violations:
            input_guards = mark_guard_as_blocked(
                input_guards,
                violations[0].get("rule_id", ""),
                violations[0].get("message", "")
            )

        await guard_logger.log_guard_execution(
            request_id=request_id,
            guard_id="input_guards",
            phase="input",
            execution_time_ms=(time.time() - start_time) * 1000,
            violations=violations
        )

        response_time = time.time() - start_time
        await request_logger.log_request(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            headers=dict(request.headers),
            body=body,
            status_code=400,
            response_time=response_time,
            tenant_id=tenant_id,
            policy_id=policy_id,
            policy_hash=policy_metadata.get("hash", "unknown")
        )

        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "type": "policy_violation",
                    "message": f"Policy violation: {violations[0].get('message', 'Unknown')}",
                    "policy_id": policy_id,
                    "rule_id": violations[0].get("rule_id", "unknown"),
                    "action": "refuse",
                    "trace_id": trace_id
                },
                "guardrails": {
                    "input_guards": input_guards,
                    "output_guards": [],
                    "execution_time_ms": {
                        "input": (time.time() - start_time) * 1000,
                        "output": 0
                    }
                }
            },
            headers={
                "x-policy-id": policy_id,
                "x-tenant-id": tenant_id,
                "x-trace-id": trace_id
            }
        )
