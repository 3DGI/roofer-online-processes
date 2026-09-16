# Roofer Online Processes

Reusable OGC API - Processes implementation for Roofer Online. The repository covers Geonovum
DTaaS Testbed 2026 Topic 1.

## Development

Requirements: Python 3.12+, Node.js 20.17+, npm, [uv](https://docs.astral.sh/uv/), and `just`.

```bash
just sync
npm install
just api-run
just check
```

The reference service runs at <http://localhost:8000>. Its OGC API is under `/ogcapi`.
With the API running, validate it against the OGC API - Processes 2.0.0 draft using:

```bash
just ogc-check
```

Set `OGC_API_URL` to check another running instance. The checker returns a non-zero status when
the API violates the selected standard.

The reusable protocol package is in `packages/ogc-processes`. Roofer Online integration is defined
by the host adapter contract in [docs/integration-contract.md](docs/integration-contract.md).

## Scope and provenance

See [docs/project-plan.md](docs/project-plan.md) and [docs/architecture.md](docs/architecture.md)
for the implementation plan and deployment boundary.

## API workflow

Prepare uploaded, remote, or existing point clouds with `roofer:validate_point_cloud:v1`,
inspect each outcome for ready IDs, then reconstruct with an explicit BAG selector. Convert
or export owned ready models and retrieve authenticated artifacts. See the
[client examples and production adapter requirements](docs/integration-contract.md).
Contracts are enforced by runtime models and advertised JSON schemas, including the complete
`inputsSchema` extension for constraints spanning multiple named inputs. The reference service
uses deterministic fixtures and demo archives; production ingestion is the next milestone.
