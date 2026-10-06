# Architecture

Status reviewed on 2026-10-06 against this repository's source. The OGC linter and
compliance suite are fully green, as confirmed by the project owner; they were not rerun.

`packages/ogc-processes` owns the HTTP protocol layer and depends on injected
`ProcessCatalog`, `ExecutionBackend`, `JobStore`, `Authenticator`, and
`ProcessContractValidator` interfaces. It does not import Roofer domain models,
database code, authentication code, or Dagster.

`apps/api` mounts that application at `/ogcapi` and supplies deterministic reference
services. `process_contracts.py` supplies runtime input/output validation and the
schemas used by process discovery. The public catalog contains `echo` for
conformance exercises and three Roofer processes: preparation, reconstruction,
and conversion. **3DCityDB export is intentionally deferred and unpublished.**
Its contract and fixture backend branch remain in source for future work.

Jobs, backend results, and generated fixture asset registrations live in memory.
Demo bearer tokens are caller identities; requests without a usable bearer token
use `demo`. Job access is scoped by subject, but this is not production authentication.
The host download route serves public CityJSON and GeoPackage fixtures from `data/`.
No external point clouds are fetched and no reconstruction or conversion engine runs.

A production Roofer adapter must implement the injected interfaces using host
application services, authentication, ownership checks, and persistent storage.
It must map public jobs to Roofer process/model IDs and workflow run IDs, retain
results across restarts, and expose authorized downloads through host routes or
signed URLs. The reference API is a protocol demonstration, not a production
workflow engine.

The mounted `/ogcapi/openapi.json` describes relative OGC paths using OpenAPI
3.0.3. The parent `/openapi.json` and `/docs` expose those paths prefixed with
`/ogcapi`; the parent schema currently projects the OGC schema rather than listing
all host routes. OGC links use the request's public base URL and mount prefix.
Artifact links separately use `ROOFER_PROCESSES_PUBLIC_BASE_URL`, defaulting to
`http://localhost:8000`. Compose configures the staging origin and one worker;
the Docker image includes the fixture files. Deployment configuration is present,
but live deployment health was not checked in this review.

See [implementation.md](implementation.md) for API behavior and limitations,
[integration-contract.md](integration-contract.md) for adapter responsibilities,
and [next-implementation-steps.md](next-implementation-steps.md) for remaining work.
