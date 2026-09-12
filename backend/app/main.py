# ruff: noqa: I001 - Imports structured for Jinja2 template conditionals
"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI
from fastapi_pagination import add_pagination
from starlette.middleware.cors import CORSMiddleware

from app.api.exception_handlers import register_exception_handlers
from app.api.router import api_router
from app.core.config import settings
from app.db.session import close_db
from app.core.logfire_setup import instrument_app, setup_logfire
from app.core.logfire_setup import instrument_asyncpg
from app.core.logfire_setup import instrument_pydantic_ai
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware
from app.clients.redis import RedisClient

logger = logging.getLogger(__name__)


class LifespanState(TypedDict, total=False):
    """Lifespan state - resources available via request.state."""

    redis: RedisClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[LifespanState, None]:
    """Application lifespan - startup and shutdown events.

    Resources yielded here are available via request.state in route handlers.
    See: https://asgi.readthedocs.io/en/latest/specs/lifespan.html#lifespan-state
    """
    state: LifespanState = {}
    setup_logfire()
    instrument_asyncpg()
    instrument_pydantic_ai()
    redis_client = RedisClient()
    await redis_client.connect()
    state["redis"] = redis_client
    yield state
    if "redis" in state:
        await state["redis"].close()

    await close_db()


SHOW_DOCS_ENVIRONMENTS = ("local", "staging", "development")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    show_docs = settings.ENVIRONMENT in SHOW_DOCS_ENVIRONMENTS
    openapi_url = f"{settings.API_V1_STR}/openapi.json" if show_docs else None
    docs_url = "/docs" if show_docs else None
    redoc_url = "/redoc" if show_docs else None

    openapi_tags = [
        {
            "name": "health",
            "description": "Health check endpoints for monitoring and Kubernetes probes",
        },
        {
            "name": "auth",
            "description": "Authentication endpoints - login, register, token refresh",
        },
        {
            "name": "users",
            "description": "User management endpoints",
        },
        {
            "name": "conversations",
            "description": "AI conversation persistence - manage chat history",
        },
        {
            "name": "agent",
            "description": "AI agent WebSocket endpoint for real-time chat",
        },
        {
            "name": "websocket",
            "description": "WebSocket endpoints for real-time communication",
        },
    ]

    setup_logging()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        summary="AI workspace with native knowledge retrieval and persistent tasks",
        description="""
AI workspace for knowledge retrieval, conversation, and persistent agent tasks.

## Features
- **Authentication**: JWT-based authentication with refresh tokens
- **API Key**: Header-based API key authentication
- **Database**: Async database operations
- **Redis**: Caching and session storage
- **AI Agent**: PydanticAI-powered conversational assistant
- **Observability**: Logfire integration for tracing and monitoring

## Documentation

- [Swagger UI](/docs) - Interactive API documentation
- [ReDoc](/redoc) - Alternative documentation view
        """.strip(),
        version="0.1.0",
        openapi_url=openapi_url,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_tags=openapi_tags,
        license_info={
            "name": "MIT",
            "identifier": "MIT",
        },
        lifespan=lifespan,
    )
    # setup_logfire() is also called from the lifespan for the runtime app, but
    # we call it here too so that import-time test clients (which never run
    # lifespan) silence the "configure first" warning. setup_logfire() is
    # idempotent via a module-level guard in logfire_setup.py.
    setup_logfire()
    instrument_app(app)

    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    app.include_router(api_router, prefix=settings.API_V1_STR)

    add_pagination(app)

    return app


app = create_app()
