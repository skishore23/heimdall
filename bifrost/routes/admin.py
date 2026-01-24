"""
Admin endpoints for Bifröst gateway
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from heimdall.mimir import PolicyEnvelope

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.post("/reload")
async def reload_policy(request: Request):
    """
    Hot-reload a policy envelope

    Request body:
        PolicyEnvelope JSON (from 'heimdall policy compile')

    Returns:
        Reload status

    Example:
        curl -X POST http://localhost:8080/admin/reload \\
          -H "Content-Type: application/json" \\
          -d @build/policy.json
    """
    try:
        # Parse envelope
        body = await request.json()
        envelope = PolicyEnvelope(**body)

        # Get policy cache
        policy_cache = request.app.state.policy_cache

        # Hot-reload policy
        await policy_cache.hot_reload_policy(envelope)

        logger.info(f"Hot-reloaded policy: {envelope.policy_id} v{envelope.version}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "reloaded",
                "policy_id": envelope.policy_id,
                "version": envelope.version,
                "message": f"Policy {envelope.policy_id} v{envelope.version} reloaded successfully"
            }
        )

    except ValueError as e:
        # Signature verification failed
        logger.error(f"Policy reload failed (invalid signature): {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid policy envelope: {str(e)}"
        )

    except Exception as e:
        logger.error(f"Policy reload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Policy reload failed: {str(e)}"
        )


@router.get("/policies")
async def list_policies(request: Request):
    """
    List all cached policies

    Returns:
        List of policies with metadata
    """
    try:
        policy_cache = request.app.state.policy_cache
        policies = await policy_cache.list_policies()

        return JSONResponse(
            status_code=200,
            content={
                "policies": policies,
                "count": len(policies)
            }
        )

    except Exception as e:
        logger.error(f"Failed to list policies: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list policies: {str(e)}"
        )


@router.post("/policies/{policy_id}/invalidate")
async def invalidate_policy(policy_id: str, request: Request):
    """
    Invalidate a specific policy from cache

    Args:
        policy_id: Policy ID to invalidate

    Returns:
        Invalidation status
    """
    try:
        policy_cache = request.app.state.policy_cache
        await policy_cache.invalidate_policy(policy_id)

        logger.info(f"Invalidated policy: {policy_id}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "invalidated",
                "policy_id": policy_id,
                "message": f"Policy {policy_id} invalidated successfully"
            }
        )

    except Exception as e:
        logger.error(f"Failed to invalidate policy: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to invalidate policy: {str(e)}"
        )

