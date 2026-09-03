# Roofer Online Processes

Reusable OGC API - Processes implementation for Roofer Online. The repository covers Geonovum
DTaaS Testbed 2026 Topic 1.

## Development

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), and `just`.

```bash
just sync
just api-run
just check
```

The reference service runs at <http://localhost:8000>. Its OGC API is under `/ogcapi`.

The reusable protocol package is in `packages/ogc-processes`. Roofer Online integration is defined
by the host adapter contract in [docs/integration-contract.md](docs/integration-contract.md).

## Scope and provenance

See [docs/project-plan.md](docs/project-plan.md) and [docs/architecture.md](docs/architecture.md)
for the implementation plan and deployment boundary.

