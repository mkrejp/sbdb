"""Health check routes."""

from fastapi import APIRouter

from sample_db_backend.db import probe_database
from sample_db_backend.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return process liveness and optional database probe status."""
    database = probe_database()
    status_value = "ok" if database in {"connected", "skipped"} else "degraded"
    return HealthResponse(status=status_value, database=database)
