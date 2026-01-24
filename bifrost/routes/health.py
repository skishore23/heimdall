"""
Health check and monitoring endpoints
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint for Kubernetes/load balancer"""
    try:
        # Check Redis connection
        policy_cache = request.app.state.policy_cache
        if policy_cache.redis_client:
            await policy_cache.redis_client.ping()
            redis_status = "healthy"
        else:
            redis_status = "not_configured"

        return JSONResponse(
            content={
                "status": "healthy",
                "redis": redis_status,
                "version": "0.9.0"
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "version": "0.9.0"
            }
        )


@router.get("/metrics")
async def metrics(request: Request) -> JSONResponse:
    """Prometheus metrics endpoint with real performance data"""
    from heimdall.registry import get_performance_metrics

    # Get actual performance metrics from the registry
    perf_metrics = get_performance_metrics()

    # Calculate aggregate metrics
    total_requests = len(perf_metrics)
    avg_duration = sum(m.execution_time_ms for m in perf_metrics) / max(total_requests, 1) / 1000.0
    budget_violations = sum(1 for m in perf_metrics if m.exceeded_budget)

    # Get Redis status
    redis_status = "connected"
    try:
        redis_client = request.app.state.policy_cache.redis_client
        await redis_client.ping()
    except Exception:
        redis_status = "disconnected"

    return JSONResponse(
        content={
            "gateway_requests_total": total_requests,
            "gateway_request_duration_seconds": round(avg_duration, 4),
            "guard_violations_total": budget_violations,
            "guard_execution_duration_seconds": round(avg_duration, 4),
            "redis_connection_status": redis_status,
            "guard_performance_metrics": {
                "total_executions": total_requests,
                "average_execution_time_ms": round(sum(m.execution_time_ms for m in perf_metrics) / max(total_requests, 1), 2),
                "budget_exceeded_count": budget_violations,
                "unique_guards_executed": len({m.guard_id for m in perf_metrics})
            }
        }
    )


@router.get("/info")
async def info(request: Request) -> JSONResponse:
    """Service information endpoint"""
    settings = request.app.state.settings
    return JSONResponse(
        content={
            "service": "guardrails-gateway",
            "version": "0.9.0",
            "description": "OpenAI-compatible API gateway with guard enforcement",
            "features": [
                "OpenAI API compatibility",
                "Composable Guard Algebra (Heimdall)",
                "Streaming support",
                "Policy enforcement",
                "Redis caching",
                "Structured logging"
            ],
            "config": {
                "openai_api_key_configured": bool(settings.openai_api_key),
                "anthropic_api_key_configured": bool(settings.anthropic_api_key),
                "redis_url": settings.redis_url,
                "default_policy_id": settings.default_policy_id
            }
        }
    )
