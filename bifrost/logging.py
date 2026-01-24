"""
Logging configuration for the Guardrails Gateway
"""

import logging
import sys
from typing import Any

import structlog


def setup_logging(log_level: str = "INFO"):
    """Setup structured logging with structlog"""

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Set log levels for third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("redis").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger"""
    return structlog.get_logger(name)


class RequestLogger:
    """Request logging middleware"""

    def __init__(self):
        self.logger = get_logger("gateway.request")

    async def log_request(
        self,
        request_id: str,
        method: str,
        path: str,
        headers: dict[str, str],
        body: Any = None,
        status_code: int = None,
        response_time: float = None,
        tenant_id: str = None,
        policy_id: str = None,
        policy_hash: str = None,
    ):
        """Log request details"""
        log_data = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "response_time_ms": response_time * 1000 if response_time else None,
            "tenant_id": tenant_id,
            "policy_id": policy_id,
            "policy_hash": policy_hash,
        }

        # Add headers (filter sensitive ones)
        sensitive_headers = {"authorization", "x-api-key", "cookie"}
        filtered_headers = {
            k: v for k, v in headers.items()
            if k.lower() not in sensitive_headers
        }
        log_data["headers"] = filtered_headers

        # Add body size (not content for privacy)
        if body is not None:
            if isinstance(body, dict | list):
                import json
                body_str = json.dumps(body)
                log_data["body_size"] = len(body_str)
            elif isinstance(body, str):
                log_data["body_size"] = len(body)
            else:
                log_data["body_size"] = len(str(body))

        if status_code and status_code >= 400:
            self.logger.error("Request completed with error", **log_data)
        else:
            self.logger.info("Request completed", **log_data)


class GuardLogger:
    """Guard execution logging"""

    def __init__(self):
        self.logger = get_logger("gateway.guards")

    async def log_guard_execution(
        self,
        request_id: str,
        guard_id: str,
        phase: str,
        execution_time_ms: float,
        violations: list = None,
        context_size: int = None,
    ):
        """Log guard execution details"""
        log_data = {
            "request_id": request_id,
            "guard_id": guard_id,
            "phase": phase,
            "execution_time_ms": execution_time_ms,
            "context_size": context_size,
            "violation_count": len(violations) if violations else 0,
        }

        if violations:
            log_data["violations"] = [
                {
                    "rule_id": v.get("rule_id"),
                    "severity": v.get("severity"),
                    "message": v.get("message"),
                    "score": v.get("score"),
                }
                for v in violations
            ]

        if violations:
            self.logger.warning("Guard violations detected", **log_data)
        else:
            self.logger.debug("Guard executed successfully", **log_data)
