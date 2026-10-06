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

The reusable protocol package is in `packages/ogc-processes`. Roofer Online integration is defined
by the host adapter contract in [docs/integration-contract.md](docs/integration-contract.md).

Production v2 contracts live in `packages/roofer-processes-contracts`. The real
Roofer integration, remote ingestion, authentication, and release workflow are
documented in [docs/roofer-integration.md](docs/roofer-integration.md).

## Staging deployment

The reference API can be deployed on `webserver-fsn1` at
<https://processes.staging.roofer-online.nl>. It uses demo authentication and keeps jobs in
memory, so restarting its single worker clears active jobs. Ensure the hostname has an A record
for `46.224.130.97` before enabling the Caddy site.

From the repository root, deploy the current commit with:

```bash
just deploy
```

This copies the committed source over SSH using the `3dgi-webserver` alias from your local
`~/.ssh/config`, rebuilds and starts the Compose service, then runs the Caddy Ansible recipe
from the sibling `../3dgi-sysadmin` checkout. Ansible targets the inventory name
`webserver-fsn1`. Commit any changes you want deployed first; `git archive HEAD` excludes
uncommitted and untracked files.

Inspect service health and logs with:

```bash
ssh webserver-fsn1 'docker compose -f /home/deploy/roofer-online-processes/compose.yaml ps'
ssh webserver-fsn1 'docker compose -f /home/deploy/roofer-online-processes/compose.yaml logs -f api'
```

For later updates, repeat the source transfer and `docker compose up -d --build` command. The
Compose binding is loopback-only; public traffic reaches the API through Caddy.

## Scope and provenance

See [docs/project-plan.md](docs/project-plan.md) and [docs/architecture.md](docs/architecture.md)
for the implementation plan and deployment boundary.
The [public URL fixes plan](docs/public-url-fixes-plan.md) covers proxy and artifact links.

## API workflow

Prepare uploaded, remote, or existing point clouds with `roofer:validate_point_cloud:v1`,
inspect each outcome for ready IDs, then reconstruct with an explicit BAG selector. Convert
or export owned ready models and retrieve authenticated artifacts. See the
[client examples and production adapter requirements](docs/integration-contract.md).
Contracts are enforced by runtime models and advertised JSON schemas, including the complete
`inputsSchema` extension for constraints spanning multiple named inputs. The reference service
uses deterministic fixtures and demo archives; production ingestion is the next milestone.
