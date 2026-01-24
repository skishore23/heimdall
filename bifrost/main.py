"""
Main FastAPI application for the Guardrails Gateway
"""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .cache import PolicyCache
from .config import Settings
from .hooks import HookRegistry, create_hook_builder
from .logging import setup_logging
from .routes import admin, chat, debug, embeddings, health, trace


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    settings = app.state.settings
    logger = logging.getLogger(__name__)

    logger.info("Starting Guardrails Gateway...")

    # Initialize policy cache
    app.state.policy_cache = PolicyCache(
        redis_url=settings.redis_url,
        default_policy_id=settings.default_policy_id
    )
    await app.state.policy_cache.initialize()

    # Initialize hook registry
    app.state.hook_registry = HookRegistry()
    app.state.hook_builder = create_hook_builder()

    logger.info("Guardrails Gateway started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Guardrails Gateway...")
    if hasattr(app.state, 'policy_cache'):
        await app.state.policy_cache.close()
    logger.info("Guardrails Gateway shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    settings = Settings()

    # Debug: Check if OpenAI API key is loaded
    logger = logging.getLogger(__name__)
    if settings.openai_api_key:
        logger.info(f"OpenAI API key loaded (length: {len(settings.openai_api_key)})")
    else:
        logger.error("OpenAI API key not found in environment!")
        logger.error(f"   Checked .env file at: {settings.Config.env_file}")
        logger.error(f"   File exists: {os.path.exists(settings.Config.env_file)}")

    # Setup logging
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Guardrails Gateway",
        description="OpenAI-compatible API gateway with guard enforcement",
        version="0.1.0",
        lifespan=lifespan
    )

    # Store settings in app state
    app.state.settings = settings

    # Add request logging middleware to track healthz requests
    @app.middleware("http")
    async def log_healthz_requests(request: Request, call_next):
        if request.url.path == "/healthz":
            logger = logging.getLogger(__name__)
            logger.warning(f"🚨 HEALTHZ REQUEST DETECTED: {request.url.path} from {request.client.host} - User-Agent: {request.headers.get('user-agent', 'Unknown')}")
            logger.warning(f"   Headers: {dict(request.headers)}")

        response = await call_next(request)
        return response

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(chat.router, prefix="/v1")
    app.include_router(embeddings.router, prefix="/v1")
    app.include_router(health.router, prefix="")
    app.include_router(debug.router, prefix="/debug")
    app.include_router(trace.router, prefix="/v1")
    app.include_router(admin.router, prefix="")

    return app


def main():
    """Main entry point for the gateway server"""
    settings = Settings()

    uvicorn.run(
        "bifrost.main:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        loop="uvloop",
        http="httptools",
        log_level=settings.log_level.lower(),
        access_log=True,
    )


# Create app instance for uvicorn
app = create_app()

if __name__ == "__main__":
    main()
