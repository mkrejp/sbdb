"""FastAPI application entrypoint."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from sample_db_backend.config import get_settings
from sample_db_backend.routers import health, layers


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="Sample DB backend",
        description=(
            "FastAPI + PostgreSQL (Supabase) API for GeoJSON map layers "
            "(design artifact: notes-for-data-model). Validation errors use HTTP 422."
        ),
        version="0.1.0",
    )
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
