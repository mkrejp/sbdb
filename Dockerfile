# syntax=docker/dockerfile:1
# Minimal Free-tier-friendly image for Railway (single uvicorn worker).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PORT=8010

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY migrations ./migrations

RUN uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8010

# Railway injects PORT; stay single-worker for ~0.5 GB Free RAM.
CMD ["sh", "-c", "uv run uvicorn sample_db_backend.main:app --host 0.0.0.0 --port ${PORT}"]
