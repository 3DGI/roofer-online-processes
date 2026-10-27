# Roofer Online Processes

Reusable OGC API - Processes implementation for Roofer Online. The repository covers Geonovum
DTaaS Testbed 2026 Topic 1.

## Development

Requirements: Python 3.12+, Node.js 22.18+, npm, [uv](https://docs.astral.sh/uv/), and `just`.

```bash
just sync
npm ci
just api-run
just check
```

The reference service runs at <http://localhost:8000>. Its OGC API is under `/ogcapi`.
Swagger UI is available at <http://localhost:8000/ogcapi/docs>.
The rationale and tradeoffs for process-specific Swagger schemas are described
in [docs/swagger-process-specific-schemas.md](docs/swagger-process-specific-schemas.md).
Set `ROOFER_PROCESSES_PUBLIC_BASE_URL` to the public HTTPS origin (and any path prefix)
when deploying the reference API. Artifact links use this base URL; it defaults to
`http://localhost:8000` for local development. When running behind Caddy or another
reverse proxy, forward the public `Host` and scheme (`X-Forwarded-Host` and
`X-Forwarded-Proto`) and configure Uvicorn to trust that proxy's headers.
With the API running, validate it against the OGC API - Processes 2.0.0 draft using:

```bash
just ogc-lint
```

Set `OGC_API_URL` to check another running instance. The checker returns a non-zero status when
the API violates the selected standard.

The reusable protocol package is in `packages/ogc-processes`.

Production v2 contracts live in `packages/roofer-processes-contracts`.

## Running with Compose

Run `docker compose up -d --build api` and open <http://localhost:18082/ogcapi>.
Set `ROOFER_PROCESSES_PUBLIC_BASE_URL` to the externally visible origin when running
behind a proxy. The reference API uses demo authentication and stores jobs in memory.

See [the architecture](docs/architecture.md) for the implementation scope.

## API workflow

Prepare uploaded, remote, or existing point clouds with `roofer:validate_point_cloud:v1`,
inspect each outcome for ready IDs, then reconstruct with an explicit BAG selector. Convert
or export owned ready models and retrieve authenticated artifacts. See the
[client examples and production adapter requirements](docs/integration-contract.md).
Contracts are enforced by runtime models and advertised JSON schemas. The OpenAPI execution
request schema includes constraints spanning multiple named inputs. The reference service
uses deterministic fixtures and demo archives; production ingestion is the next milestone.
