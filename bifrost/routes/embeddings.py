"""
Embeddings API route with guard enforcement
"""

import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from heimdall import get_context, get_violations, is_left

from ..guards import run_input_guards
from ..logging import GuardLogger, RequestLogger
from ..providers import get_provider_client

router = APIRouter()
request_logger = RequestLogger()
guard_logger = GuardLogger()


@router.post("/embeddings")
async def embeddings(request: Request):
    """OpenAI-compatible embeddings endpoint with guard enforcement"""
    request_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        # Parse request body
        body = await request.json()
        tenant_id = request.headers.get("x-tenant-id", "default")
        policy_id = request.headers.get("x-policy-id")
        trace_id = request.headers.get("x-trace-id", request_id)

        # Get policy
        policy_cache = request.app.state.policy_cache
        compiled_guard, policy_metadata = await policy_cache.get_policy(
            tenant_id=tenant_id,
            policy_id=policy_id
        )

        policy_hash = policy_metadata.get("hash", "unknown")

        # Run input guards on embedding text
        input_guard_start = time.time()
        input_result = await run_input_guards(compiled_guard, body)
        input_guard_time = (time.time() - input_guard_start) * 1000

        if is_left(input_result):
            violations = get_violations(input_result)
            await guard_logger.log_guard_execution(
                request_id=request_id,
                guard_id="input_guards",
                phase="input",
                execution_time_ms=input_guard_time,
                violations=violations
            )

            response_time = (time.time() - start_time) * 1000
            await request_logger.log_request(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                headers=dict(request.headers),
                body=body,
                status_code=400,
                response_time=response_time / 1000,
                tenant_id=tenant_id,
                policy_id=policy_id,
                policy_hash=policy_hash,
            )

            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "type": "policy_violation",
                        "message": f"Input policy violation: {violations[0]['message']}",
                        "policy_id": policy_id or "default",
                        "policy_hash": f"sha256:{policy_hash}",
                        "rule_id": violations[0]["rule_id"],
                        "action": "refuse",
                        "trace_id": trace_id
                    }
                },
                headers={
                    "x-policy-id": policy_id or "default",
                    "x-policy-hash": f"sha256:{policy_hash}",
                    "x-tenant-id": tenant_id,
                    "x-trace-id": trace_id
                }
            )

        # Input guards passed, get updated context
        updated_body = get_context(input_result)

        # Get provider client
        settings = request.app.state.settings
        provider_client = await get_provider_client(updated_body, tenant_id, settings)

        # Make request to provider
        response = await provider_client.create_embeddings(updated_body)

        # Add policy headers to response
        response_headers = {
            "x-policy-id": policy_id or "default",
            "x-policy-hash": f"sha256:{policy_hash}",
            "x-tenant-id": tenant_id,
            "x-trace-id": trace_id
        }

        # Log request completion
        response_time = (time.time() - start_time) * 1000
        await request_logger.log_request(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            headers=dict(request.headers),
            body=body,
            status_code=200,
            response_time=response_time / 1000,
            tenant_id=tenant_id,
            policy_id=policy_id,
            policy_hash=policy_hash,
        )

        return JSONResponse(
            content=response,
            headers=response_headers
        )

    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        await request_logger.log_request(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            headers=dict(request.headers),
            status_code=500,
            response_time=response_time / 1000,
        )

        raise HTTPException(status_code=500, detail=str(e))
