"""
Adapters for popular frameworks

Provides integration with FastAPI, LangChain/LangGraph, and MCP.
Handles taint propagation via W3C Trace Context baggage.
"""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from .dataflow import TaintMetadata, attach_taint_to_context, extract_taint_from_context
from .types import Ctx, Either, Guard, get_violations, is_left

# ========== FastAPI Adapter ==========

def create_fastapi_middleware(guard: Guard, extract_ctx: Callable[[Any], Ctx]):
    """
    Create FastAPI middleware for guard enforcement

    Args:
        guard: Guard to enforce
        extract_ctx: Function to extract context from FastAPI Request

    Returns:
        FastAPI middleware

    Example:
        ```python
        from fastapi import FastAPI, Request

        app = FastAPI()

        def extract_context(request: Request) -> Ctx:
            return {
                "method": request.method,
                "path": request.url.path,
                "headers": dict(request.headers),
            }

        middleware = create_fastapi_middleware(my_guard, extract_context)

        @app.middleware("http")
        async def guard_middleware(request: Request, call_next):
            return await middleware(request, call_next)
        ```
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    async def middleware(request: Request, call_next):
        # Extract context
        ctx = extract_ctx(request)

        # Extract taint from W3C baggage if present
        baggage = request.headers.get("baggage", "")
        if baggage:
            baggage_dict = {}
            for item in baggage.split(","):
                if "=" in item:
                    key, value = item.strip().split("=", 1)
                    baggage_dict[key] = value

            taint = TaintMetadata.from_baggage(baggage_dict)
            ctx = attach_taint_to_context(ctx, taint)

        # Run guard
        result = await guard(ctx)

        if is_left(result):
            # Block request
            violations = get_violations(result)
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Policy violation",
                    "violations": violations
                }
            )

        # Propagate taint in response headers
        response = await call_next(request)

        taint = extract_taint_from_context(ctx)
        if taint:
            baggage_str = ",".join(f"{k}={v}" for k, v in taint.to_baggage().items())
            response.headers["baggage"] = baggage_str

        return response

    return middleware


# ========== LangChain/LangGraph Adapter ==========

def wrap_langchain_tool(tool: Any, guard: Guard, extract_ctx: Callable[[dict], Ctx]):
    """
    Wrap a LangChain tool with guard enforcement

    Args:
        tool: LangChain tool
        guard: Guard to enforce
        extract_ctx: Function to extract context from tool input

    Returns:
        Wrapped tool with guard enforcement

    Example:
        ```python
        from langchain.tools import Tool

        def my_tool(input: str) -> str:
            return f"Result: {input}"

        def extract_tool_context(args: dict) -> Ctx:
            return {
                "tool": "my_tool",
                "input": args.get("input"),
            }

        guarded_tool = wrap_langchain_tool(
            Tool(name="my_tool", func=my_tool, description="..."),
            my_guard,
            extract_tool_context
        )
        ```
    """
    original_func = tool.func

    @wraps(original_func)
    async def guarded_func(*args, **kwargs):
        # Extract context
        ctx = extract_ctx({"args": args, "kwargs": kwargs})

        # Run guard
        result = await guard(ctx)

        if is_left(result):
            violations = get_violations(result)
            raise ValueError(f"Guard violation: {violations}")

        # Call original tool
        if callable(original_func):
            return await original_func(*args, **kwargs) if hasattr(original_func, '__await__') \
                   else original_func(*args, **kwargs)

        return None

    tool.func = guarded_func
    return tool


def create_langgraph_guard_node(guard: Guard, node_name: str):
    """
    Create a LangGraph node for guard enforcement

    Args:
        guard: Guard to enforce
        node_name: Node identifier

    Returns:
        LangGraph node function

    Example:
        ```python
        from langgraph.graph import StateGraph

        graph = StateGraph(MyState)

        guard_node = create_langgraph_guard_node(my_guard, "input_guard")
        graph.add_node("guard", guard_node)
        ```
    """
    async def guard_node(state: dict[str, Any]) -> dict[str, Any]:
        # Extract context from state
        ctx = state.copy()
        ctx["_node"] = node_name

        # Run guard
        result = await guard(ctx)

        if is_left(result):
            # Add violations to state
            state["_guard_violations"] = get_violations(result)
            state["_guard_failed"] = True
        else:
            state["_guard_failed"] = False

        return state

    return guard_node


# ========== MCP Adapter ==========

def create_mcp_proxy_guard(guard: Guard):
    """
    Create MCP proxy guard that intercepts tool calls

    Args:
        guard: Guard to enforce

    Returns:
        MCP proxy guard function

    Example:
        ```python
        from mcp_proxy import MCPProxy

        proxy = MCPProxy()
        guard_fn = create_mcp_proxy_guard(my_guard)
        proxy.add_guard(guard_fn)
        ```
    """
    async def mcp_guard(tool_call: dict[str, Any]) -> Either:
        # Extract context from MCP tool call
        ctx = {
            "tool": tool_call.get("name"),
            "arguments": tool_call.get("arguments", {}),
            "context": tool_call.get("context", {}),
        }

        # Propagate taint from MCP context
        if "baggage" in tool_call.get("context", {}):
            baggage = tool_call["context"]["baggage"]
            taint = TaintMetadata.from_baggage(baggage)
            ctx = attach_taint_to_context(ctx, taint)

        # Run guard
        result = await guard(ctx)

        return result

    return mcp_guard


def inject_taint_into_mcp_context(
    tool_call: dict[str, Any],
    taint: TaintMetadata
) -> dict[str, Any]:
    """
    Inject taint metadata into MCP tool call context

    Args:
        tool_call: MCP tool call
        taint: Taint metadata

    Returns:
        Updated tool call with taint
    """
    if "context" not in tool_call:
        tool_call["context"] = {}

    tool_call["context"]["baggage"] = taint.to_baggage()

    return tool_call


# ========== Generic Decorator ==========

def guard_function(guard: Guard, extract_ctx: Callable):
    """
    Generic decorator to add guard to any async function

    Args:
        guard: Guard to enforce
        extract_ctx: Function to extract context from function args

    Returns:
        Decorator

    Example:
        ```python
        @guard_function(my_guard, lambda *args, **kwargs: {"args": args})
        async def sensitive_operation(user_id: str, data: dict):
            # ... operation
            pass
        ```
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract context
            ctx = extract_ctx(*args, **kwargs)

            # Run guard
            result = await guard(ctx)

            if is_left(result):
                violations = get_violations(result)
                raise PermissionError(f"Guard violation: {violations}")

            # Call original function
            return await func(*args, **kwargs)

        return wrapper
    return decorator

