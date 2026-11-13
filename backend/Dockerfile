# syntax=docker/dockerfile:1
# BuildKit required for cache mounts (DOCKER_BUILDKIT=1 or Docker Desktop default).

FROM python:3.14-slim AS builder

WORKDIR /app

# Reuse official uv binary — avoids pip download on every cold build.
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv

ARG UV_EXTRA_ARGS=""

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Layer 1: deps — only rebuilds when lock/manifest change.
COPY app/pyproject.toml app/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project $UV_EXTRA_ARGS

# Layer 2: project — rebuilds on code changes; deps stay cached above.
COPY app/ ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev $UV_EXTRA_ARGS

FROM python:3.14-slim AS runtime

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /app /app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
