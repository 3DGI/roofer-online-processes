default:
    @just --list

sync:
    uv sync

api-run:
    uv run --package roofer-online-processes-api uvicorn api.main:app --reload

api-docker:
    docker compose up -d --build api

api-docker-down:
    docker compose down

ogc-check:
    npm exec --package=@geonovum/ogc-checker@1.3.1 -- ogc-checker validate --standard ogc-api-processes --version 2.0.0 --input "${OGC_API_URL:-http://localhost:8000/ogcapi/openapi.json}" --fail-on warn

test:
    uv run pytest

lint:
    uv run ruff check .

lint-fix:
    uv run ruff check --fix .

format:
    uv run ruff format .

format-check:
    uv run ruff format --check .

typecheck:
    uv run mypy packages/ogc-processes/src apps/api/src

check: format-check lint test
