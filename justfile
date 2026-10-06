ogc-teamengine-image := "ogccite/ets-ogcapi-processes10:1.3-teamengine-6.0.0-RC2"
ogc-teamengine-container := "ogc-processes-ets"

default:
    @just --list

sync:
    uv sync

api-run:
    uv run --package roofer-online-processes-api uvicorn api.main:app --host 0.0.0.0 --reload

api-docker:
    docker compose up -d --build api

api-docker-down:
    docker compose down

ogc-check:
    npm exec --package=@geonovum/ogc-checker@1.3.1 -- ogc-checker validate --standard ogc-api-processes --version 2.0.0 --input "${OGC_API_URL:-http://localhost:8000/ogcapi/openapi.json}" --fail-on warn

# Start the pinned TEAM Engine container and wait until its REST endpoint responds.
ogc-teamengine-up:
    #!/usr/bin/env bash
    set -euo pipefail
    docker run --add-host=host.docker.internal:host-gateway --publish 127.0.0.1:8080:8080 --detach --name {{ogc-teamengine-container}} {{ogc-teamengine-image}}
    for attempt in $(seq 1 60); do
        if curl --fail --silent http://localhost:8080/teamengine/ >/dev/null; then
            echo "TEAM Engine is ready at http://localhost:8080/teamengine"
            exit 0
        fi
        sleep 2
    done
    docker logs {{ogc-teamengine-container}}
    exit 1

ogc-teamengine-down:
    docker rm --force {{ogc-teamengine-container}} 2>/dev/null || true

# Run the Processes 1.0 ETS headlessly through TEAM Engine's REST API.
ogc-processes-ets iut_url="http://host.docker.internal:8000/ogcapi/":
    OGC_IUT_URL="{{iut_url}}" python3 docker/ets-ogcapi-processes/run_ets.py

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
