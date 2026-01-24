"""
Configuration management for the Guardrails Gateway
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Server settings
    host: str = Field(default="0.0.0.0", env="HOST")  # nosec B104 - intentional for server
    port: int = Field(default=8000, env="PORT")
    workers: int = Field(default=1, env="WORKERS")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    # CORS
    cors_origins: list[str] = Field(default=["*"], env="CORS_ORIGINS")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")

    # Policy settings
    default_policy_id: str = Field(default="enterprise_default_v1", env="DEFAULT_POLICY_ID")
    policies_dir: str = Field(default="policies", env="POLICIES_DIR")

    # Provider settings
    openai_api_key: str | None = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, env="ANTHROPIC_API_KEY")

    # Upstream LLM provider configuration (for proxy mode)
    upstream_base_url: str | None = Field(default=None, env="UPSTREAM_BASE_URL")
    upstream_api_key: str | None = Field(default=None, env="UPSTREAM_API_KEY")

    # GCP settings (for production deployment)
    gcp_project_id: str | None = Field(default=None, env="GCP_PROJECT_ID")
    gcs_bucket: str | None = Field(default=None, env="GCS_BUCKET")
    kms_key_name: str | None = Field(default=None, env="KMS_KEY_NAME")

    # Performance settings
    max_concurrent_requests: int = Field(default=100, env="MAX_CONCURRENT_REQUESTS")
    request_timeout: float = Field(default=45.0, env="REQUEST_TIMEOUT")
    connect_timeout: float = Field(default=0.4, env="CONNECT_TIMEOUT")

    # Guard settings
    guard_timeout: float = Field(default=0.2, env="GUARD_TIMEOUT")
    streaming_window_size: int = Field(default=200, env="STREAMING_WINDOW_SIZE")

    # Per-guard budget settings
    guard_budget_ms: float | None = Field(default=None, env="GUARD_BUDGET_MS")
    guard_max_retries: int = Field(default=0, env="GUARD_MAX_RETRIES")
    guard_retry_backoff_ms: float = Field(default=100.0, env="GUARD_RETRY_BACKOFF_MS")

    # Observability settings
    otel_enabled: bool = Field(default=False, env="OTEL_ENABLED")
    otel_endpoint: str | None = Field(default=None, env="OTEL_ENDPOINT")
    otel_service_name: str = Field(default="bifrost-gateway", env="OTEL_SERVICE_NAME")
    otel_sample_rate: float = Field(default=1.0, env="OTEL_SAMPLE_RATE")
    decision_trace_enabled: bool = Field(default=False, env="DECISION_TRACE_ENABLED")

    # Policy layer settings
    policy_layers_enabled: bool = Field(default=False, env="POLICY_LAYERS_ENABLED")
    policy_org_level: str | None = Field(default=None, env="POLICY_ORG_LEVEL")
    policy_tenant_level: str | None = Field(default=None, env="POLICY_TENANT_LEVEL")
    policy_app_level: str | None = Field(default=None, env="POLICY_APP_LEVEL")
    policy_env_level: str | None = Field(default=None, env="POLICY_ENV_LEVEL")

    # Shadow mode settings
    shadow_mode_enabled: bool = Field(default=False, env="SHADOW_MODE_ENABLED")
    shadow_mode_sample_rate: float = Field(default=0.1, env="SHADOW_MODE_SAMPLE_RATE")

    # Circuit breaker settings
    circuit_breaker_enabled: bool = Field(default=False, env="CIRCUIT_BREAKER_ENABLED")
    circuit_breaker_failure_threshold: int = Field(default=5, env="CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    circuit_breaker_timeout_seconds: int = Field(default=60, env="CIRCUIT_BREAKER_TIMEOUT_SECONDS")

    class Config:
        # Look for .env file in the project root (parent of gateway directory)
        env_file = Path(__file__).parent.parent / ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env
