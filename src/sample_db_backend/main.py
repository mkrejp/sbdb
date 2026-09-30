"""FastAPI application entrypoint."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from sample_db_backend.config import get_settings
from sample_db_backend.routers import health, layers

logger = logging.getLogger("sample_db_backend")


class UnexpectedErrorMiddleware(BaseHTTPMiddleware):
    """Log unexpected failures with structured fields; return HTTP 500."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Pass through normal responses; catch unhandled exceptions."""
        try:
            return await call_next(request)
        except Exception:
            logger.exception(
                "unexpected_error method=%s path=%s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s %(message)s",
    )
    app = FastAPI(
        title="Sample DB backend",
        description=(
            "FastAPI + PostgreSQL (Supabase) API for GeoJSON map layers "
            "(design artifact: notes-for-data-model). Validation errors use HTTP 422."
        ),
        version="0.2.0",
    )
    app.add_middleware(UnexpectedErrorMiddleware)
    app.include_router(health.router)
    app.include_router(layers.router)
    return app


app = create_app()


def main() -> None:
    """Run uvicorn using env-configured host/port."""
    settings = get_settings()
    uvicorn.run(
        "sample_db_backend.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
