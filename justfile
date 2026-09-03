default:
    @just --list

sync:
    uv sync

api-run:
    uv run --package roofer-online-processes-api uvicorn api.main:app --reload

test:
    uv run pytest

lint:
    uv run ruff check .

format-check:
    uv run ruff format --check .

typecheck:
    uv run mypy packages/ogc-processes/src apps/api/src

check: format-check lint test

