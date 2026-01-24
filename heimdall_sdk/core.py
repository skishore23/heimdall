"""
Guardrails SDK Core

Lightweight, embeddable SDK for guard execution and policy enforcement.
For ONNX models and streaming proxy, use Bifrost gateway.
"""

import json
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from guards import *  # Import all guard packs

# Import core guardrails functionality
from heimdall import TieredGuardRunner, compile_policy, run_tiered_guards


@dataclass
class SDKConfig:
    """Configuration for the Guardrails SDK"""
    gateway_url: str = "http://localhost:8000"
    api_key: str | None = None
    timeout: float = 30.0
    streaming_enabled: bool = True
    tiered_execution: bool = False  # Disable by default - expects individual guards not composed
    performance_budget_ms: float = 1000.0


class PolicyError(Exception):
    """Policy-related errors"""
    pass


class GuardViolation(Exception):
    """Guard violation errors"""
    def __init__(self, violations: list[dict[str, Any]]):
        self.violations = violations
        super().__init__(f"Guard violations: {len(violations)} found")


class HeimdallSDK:
    """
    Lightweight Guardrails SDK for embeddable guard execution

    Features:
    - In-process guard execution
    - Policy compilation and caching
    - LLM call wrapping
    - Gateway integration
    - Tool enforcement

    Note: For ONNX models and streaming proxy, use Bifrost gateway.
    """

    def __init__(self, config: SDKConfig | None = None):
        self.config = config or SDKConfig()
        self.client = httpx.AsyncClient(timeout=self.config.timeout)
        self.tiered_runner = TieredGuardRunner() if self.config.tiered_execution else None
        self.loaded_policies = {}


    async def load_policy(self, policy_path: str) -> dict[str, Any]:
        """
        Load and compile a policy

        Args:
            policy_path: Path to YAML policy file

        Returns:
            Compiled policy with metadata
        """
        try:
            # Load policy file
            policy_file = Path(policy_path)
            if not policy_file.exists():
                raise PolicyError(f"Policy file not found: {policy_path}")

            with open(policy_file, 'rb') as f:
                policy_bytes = f.read()

            # Compile policy (guards, metadata)
            compiled_guards, metadata = compile_policy(policy_bytes)

            # Resolve policy_id from metadata or filename stem
            policy_id = metadata.get("policy_id", policy_file.stem)

            # Store compiled policy
            self.loaded_policies[policy_id] = {
                "compiled": compiled_guards,
                "metadata": metadata,
                "path": str(policy_file),
                "tiers": self._extract_tier_info(compiled_guards)
            }

            return self.loaded_policies[policy_id]

        except Exception as e:
            raise PolicyError(f"Failed to load policy {policy_path}: {e}")

    def _extract_tier_info(self, compiled_policy: dict[str, Any]) -> dict[str, list[str]]:
        """Extract tier information from compiled policy"""
        return {
            "T0": [],  # Fast guards
            "T1": [],  # Medium guards
            "T2": []   # Slow guards
        }

    async def wrap_llm(
        self,
        llm_func: Callable,
        policy_id: str,
        **llm_kwargs
    ) -> Any:
        """
        Wrap an LLM function with guardrails

        Args:
            llm_func: The LLM function to wrap
            policy_id: Policy to apply
            **llm_kwargs: Arguments for the LLM function

        Returns:
            LLM response after guard processing
        """
        if policy_id not in self.loaded_policies:
            raise PolicyError(f"Policy not loaded: {policy_id}")

        policy = self.loaded_policies[policy_id]
        compiled_guards = policy["compiled"]

        # Prepare context for input guards - ensure messages are included
        input_context = {
            "phase": "input",
            "messages": llm_kwargs.get("messages", []),
            **llm_kwargs
        }

        # Run input guards with tiered execution
        if self.config.tiered_execution and self.tiered_runner:
            exec_result = await run_tiered_guards(
                guards={"input": compiled_guards.get("input")},
                context=input_context
            )
            # ExecutionResult from tiered execution
            if exec_result.violations:
                raise GuardViolation(exec_result.violations)
            updated_context = exec_result.context
        else:
            # Use input guard, fall back to root guard
            input_guard = compiled_guards.get("input") or compiled_guards.get("root")
            if input_guard:
                input_result = await input_guard(input_context)
                # Either type from regular guard
                if input_result.get("_tag") == "Left":
                    violations = input_result.get("left", [])
                    raise GuardViolation(violations)
                updated_context = input_result.get("right", input_context)
            else:
                updated_context = input_context

        # Extract LLM arguments from updated context
        filtered_kwargs = {k: v for k, v in updated_context.items() if k != "phase"}

        # Call LLM function
        try:
            llm_response = await llm_func(**filtered_kwargs)
        except Exception as e:
            raise RuntimeError(f"LLM function failed: {e}")

        # Prepare context for output guards
        output_context = {
            "phase": "output",
            "output": llm_response,
            **filtered_kwargs
        }

        # Run output guards with tiered execution
        if self.config.tiered_execution and self.tiered_runner:
            exec_result = await run_tiered_guards(
                guards={"output": compiled_guards.get("output")},
                context=output_context
            )
            # ExecutionResult from tiered execution
            if exec_result.violations:
                raise GuardViolation(exec_result.violations)
            final_context = exec_result.context
        else:
            # Use output guard, fall back to root guard
            output_guard = compiled_guards.get("output") or compiled_guards.get("root")
            if output_guard:
                output_result = await output_guard(output_context)
                # Either type from regular guard
                if output_result.get("_tag") == "Left":
                    violations = output_result.get("left", [])
                    raise GuardViolation(violations)
                final_context = output_result.get("right", output_context)
            else:
                final_context = output_context

        # Return processed response
        return final_context.get("output", llm_response)

    async def guard_tool(
        self,
        tool_func: Callable,
        policy_id: str,
        **tool_kwargs
    ) -> Any:
        """
        Guard a tool/function call

        Args:
            tool_func: The tool function to guard
            policy_id: Policy to apply
            **tool_kwargs: Arguments for the tool function

        Returns:
            Tool response after guard processing
        """
        if policy_id not in self.loaded_policies:
            raise PolicyError(f"Policy not loaded: {policy_id}")

        policy = self.loaded_policies[policy_id]
        compiled_guards = policy["compiled"]

        # Guard tool arguments
        tool_args_context = {
            "phase": "tool_args",
            "function_name": tool_func.__name__,
            "arguments": tool_kwargs
        }

        tool_args_guard = compiled_guards.get("tool_args")
        if tool_args_guard:
            args_result = await tool_args_guard(tool_args_context)
            if args_result.get("_tag") == "Left":
                violations = args_result.get("left", [])
                raise GuardViolation(violations)

            # Get filtered arguments
            updated_context = args_result.get("right", tool_args_context)
            filtered_kwargs = updated_context.get("arguments", tool_kwargs)
        else:
            filtered_kwargs = tool_kwargs

        # Call tool function
        try:
            tool_response = await tool_func(**filtered_kwargs)
        except Exception as e:
            raise RuntimeError(f"Tool function failed: {e}")

        # Guard tool results
        tool_result_context = {
            "phase": "tool_result",
            "function_name": tool_func.__name__,
            "tool_result": {"content": str(tool_response)},
            "arguments": filtered_kwargs
        }

        tool_result_guard = compiled_guards.get("tool_result")
        if tool_result_guard:
            result_guard_result = await tool_result_guard(tool_result_context)
            if result_guard_result.get("_tag") == "Left":
                violations = result_guard_result.get("left", [])
                raise GuardViolation(violations)

            # Get filtered result
            final_context = result_guard_result.get("right", tool_result_context)
            return final_context.get("tool_result", {}).get("content", tool_response)

        return tool_response

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str = "gpt-3.5-turbo",
        policy_id: str | None = None,
        stream: bool = False,
        **kwargs
    ) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
        """
        Chat completion with guardrails via gateway or streaming proxy

    Args:
            messages: Chat messages
            model: Model to use
            policy_id: Policy to apply
            stream: Whether to stream response
            **kwargs: Additional OpenAI parameters

    Returns:
            Chat completion response or stream
        """
        # Prepare request
        request_data = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **kwargs
        }

        headers = {"Content-Type": "application/json"}
        if policy_id:
            headers["X-Policy-ID"] = policy_id
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        # Standard gateway request
        if stream:
            return await self._stream_standard(request_data, headers)
        else:
            return await self._request_standard(request_data, headers)

    async def _stream_with_proxy(
        self,
        request_data: dict[str, Any],
        headers: dict[str, str]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream using zero-copy streaming proxy"""
        try:
            async for chunk in self.streaming_proxy.stream_chat_completion(
                request_data, headers, self.config.gateway_url
            ):
                yield chunk
        except Exception as e:
            # Fallback to standard streaming
            print(f"⚠️  Streaming proxy failed, falling back: {e}")
            async for chunk in self._stream_standard(request_data, headers):
                yield chunk

    async def _stream_standard(
        self,
        request_data: dict[str, Any],
        headers: dict[str, str]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Standard streaming implementation"""
        url = f"{self.config.gateway_url}/v1/chat/completions"

        async with self.client.stream("POST", url, json=request_data, headers=headers) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                raise RuntimeError(f"Gateway error {response.status_code}: {error_text}")

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]  # Remove "data: " prefix
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        yield chunk
                    except json.JSONDecodeError:
                        continue

    async def _request_standard(
        self,
        request_data: dict[str, Any],
        headers: dict[str, str]
    ) -> dict[str, Any]:
        """Standard non-streaming request"""
        url = f"{self.config.gateway_url}/v1/chat/completions"

        response = await self.client.post(url, json=request_data, headers=headers)

        if response.status_code != 200:
            error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"error": response.text}
            raise RuntimeError(f"Gateway error {response.status_code}: {error_data}")

        return response.json()

    def get_policy_info(self, policy_id: str) -> dict[str, Any]:
        """Get information about a loaded policy"""
        if policy_id not in self.loaded_policies:
            raise PolicyError(f"Policy not loaded: {policy_id}")

        policy = self.loaded_policies[policy_id]
        return {
            "policy_id": policy_id,
            "path": policy["path"],
            "tiers": policy["tiers"],
            "compiled": bool(policy["compiled"])
        }

    def list_loaded_policies(self) -> list[str]:
        """List all loaded policy IDs"""
        return list(self.loaded_policies.keys())

    async def health_check(self) -> dict[str, Any]:
        """Check gateway health and connectivity"""
        try:
            url = f"{self.config.gateway_url}/health"
            response = await self.client.get(url)

            if response.status_code == 200:
                return                 {
                    "status": "healthy",
                    "gateway_url": self.config.gateway_url,
                    "tiered_execution": self.tiered_runner is not None
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": f"Gateway returned {response.status_code}"
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def close(self):
        """Clean up resources"""
        await self.client.aclose()


# Convenience functions for quick usage
async def quick_guard(
    text: str,
    policy_path: str,
    **kwargs
) -> dict[str, Any]:
    """
    Quick guard function for simple use cases

    Args:
        text: Text to guard
        policy_path: Path to policy file
        **kwargs: Additional configuration

    Returns:
        Guard result with violations if any
    """
    sdk = HeimdallSDK()

    try:
        # Load policy
        await sdk.load_policy(policy_path)
        policy_id = Path(policy_path).stem

        # Create a simple LLM function that returns the text
        async def simple_llm(**llm_kwargs):
            return llm_kwargs.get("messages", [{"content": text}])[-1]["content"]

        # Apply guards
        result = await sdk.wrap_llm(
            simple_llm,
            policy_id,
            messages=[{"role": "user", "content": text}]
        )

        return {"status": "passed", "result": result}

    except GuardViolation as e:
        return {"status": "blocked", "violations": e.violations}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        await sdk.close()


def load_policy(policy_path: str):
    """Load a policy file synchronously

    Returns:
        An object with compiled_guards dict and metadata dict
    """
    from pathlib import Path
    from types import SimpleNamespace

    from heimdall import compile_policy

    # Convert to Path and read the file
    path = Path(policy_path)
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")

    # Read the YAML content as bytes
    with open(path, 'rb') as f:
        yaml_bytes = f.read()

    # Compile the policy
    compiled_guards, metadata = compile_policy(yaml_bytes)

    # Return object with both guards and metadata
    result = SimpleNamespace()
    result.compiled_guards = compiled_guards
    result.metadata = metadata
    # Also expose metadata fields at top level for backward compatibility
    for key, value in metadata.items():
        setattr(result, key, value)
    return result


# Export main classes and functions
__all__ = [
    "HeimdallSDK",
    "SDKConfig",
    "PolicyError",
    "GuardViolation",
    "quick_guard",
    "load_policy"
]
