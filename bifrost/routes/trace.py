"""
Trace streaming endpoint for live debugging

Provides SSE endpoint to stream decision traces in real-time.
"""

import asyncio
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from heimdall.tracing import get_trace_collector

router = APIRouter(tags=["trace"])


@router.get("/trace/stream")
async def stream_traces(
    guard_id: str | None = Query(None, description="Filter by guard ID"),
    decision: str | None = Query(None, description="Filter by decision (pass/block)")
):
    """
    Stream decision traces via Server-Sent Events

    Args:
        guard_id: Optional guard ID filter
        decision: Optional decision filter

    Returns:
        SSE stream of traces
    """
    collector = get_trace_collector()

    async def generate():
        last_count = 0

        while True:
            # Get new traces since last check
            all_traces = collector.get_traces(
                guard_id=guard_id,
                decision=decision,
                limit=1000
            )

            # Send new traces
            if len(all_traces) > last_count:
                new_traces = all_traces[last_count:]
                for trace in new_traces:
                    data = json.dumps(trace)
                    yield f"data: {data}\n\n"

                last_count = len(all_traces)

            # Wait before next check
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/trace/stats")
async def get_trace_statistics():
    """
    Get trace statistics

    Returns:
        Statistics about collected traces
    """
    collector = get_trace_collector()
    return collector.get_statistics()


@router.get("/trace/list")
async def list_traces(
    guard_id: str | None = Query(None),
    decision: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    List recent traces

    Args:
        guard_id: Optional guard ID filter
        decision: Optional decision filter
        limit: Maximum number of traces

    Returns:
        List of traces
    """
    collector = get_trace_collector()
    traces = collector.get_traces(
        guard_id=guard_id,
        decision=decision,
        limit=limit
    )

    return {
        "traces": traces,
        "count": len(traces)
    }


@router.post("/trace/clear")
async def clear_traces():
    """Clear all collected traces"""
    collector = get_trace_collector()
    collector.clear_traces()
    return {"status": "cleared"}
