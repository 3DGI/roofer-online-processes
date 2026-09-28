FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY packages/ogc-processes/pyproject.toml packages/ogc-processes/pyproject.toml
COPY apps/api/src apps/api/src
COPY packages/ogc-processes/src packages/ogc-processes/src
COPY data /app/data

RUN uv sync --locked --no-dev --package roofer-online-processes-api

FROM python:3.12-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY apps/api/src apps/api/src
COPY packages/ogc-processes/src packages/ogc-processes/src
COPY --from=build /app/data /app/data

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
