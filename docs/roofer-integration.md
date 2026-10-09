# Roofer production integration

`roofer:reconstruct_buildings:v2` runs inside Roofer Online at `/ogcapi`.
The standalone application in this repository remains the v1 reference service.
Its fixtures are not registered in the production catalog.

## Architecture

The reusable `ogc-processes` router accepts injected catalog, validator,
authenticator, backend, and job store. `roofer-processes-contracts` contains the
v2 input/output models and catalog; it has no Roofer database dependency.
Roofer consumes versioned wheels from `apps/api/vendor`, not a workspace checkout.

Roofer's backend uses shared Python application services and the host SQLAlchemy
session. It validates the complete authoritative BAG selection and persists the
execution and encrypted source URLs. Registering the public job ID enables
dispatch in a second transaction. An unregistered execution cannot launch work.

A separate worker downloads and validates each source, creates owned PointCloud
assets, and launches the existing `pointcloud` Dagster job. All sources must be
ready before the worker creates the BAG view, Model3D, and Process records and
launches `ogc_reconstruct`. Its asset selection includes reconstruction and the
requested export stages; 3D Tiles is selected only when requested.

The worker persists launch intent before contacting Dagster. Each stage has an
exact run mapping and execution/stage/owner tags. A lost acknowledgement is
reconciled by those tags, never automatically resubmitted. Multiple matching runs
or an unresolved submission after the grace period fails explicitly. Uncertain
terminal submissions remain eligible for reconciliation so late run IDs stay
tracked. PostgreSQL advisory locks prevent concurrent workers dispatching the
same execution. Started/finished timestamps and results survive restarts.

Success requires materializations from the exact owned run and valid ZIP archives
for every requested format. Results link to Roofer's existing authenticated export
endpoint. Failed preparation preserves already-ready assets and skips reconstruction.

## Authentication and remote sources

Discovery is public. Execution and job/result routes use Roofer's existing
Authgear JWT verification and USER role policy. Job access is scoped to the
authenticated subject. Artifact downloads retain Roofer's owner/admin policy;
clients must send their bearer token when following artifact links.

Inputs accept HTTP(S) URLs only. Standard ports, every resolved IP, and each
redirect are checked; connections pin a validated public IP while retaining the
original TLS hostname. Private/local/metadata destinations, URL credentials,
fragments, compressed HTTP bodies, and oversized transfers are rejected. Host
bearer tokens are never forwarded. Presigned URLs are encrypted at rest with a
shared Fernet key and removed after preparation or terminal failure; query strings
are not included in job documents, asset names, diagnostics, or Dagster config.

Host ingestion checks that LAS/LAZ headers are readable and contain a positive
point count, finite ordered bounds, and nonzero horizontal extent. It does not
require or parse point-cloud CRS metadata and passes source coordinates through
unchanged. No reprojection is performed; clients should supply point clouds whose
horizontal coordinates align with the EPSG:28992 BAG footprints used for
selection and reconstruction. Header inspection precedes real pipeline metadata
extraction.

Defaults: 32 sources; total bytes use Roofer `MAX_SIZE` (10 GiB unless changed);
5 redirects; 10-second connect, 60-second idle, and 3600-second source deadline;
5-second polling and 300-second ambiguous-submission grace period.

## Contract and releases

The only production process is `roofer:reconstruct_buildings:v2`, async-only and
value transmission. Send `Prefer: respond-async`; subscribers are rejected.
Inputs are URL sources, BAG building IDs or a 2D Polygon/MultiPolygon in
EPSG:28992, optional name, typed UI Roofer configuration, and requested formats.
The default format is CityJSON only. Supported formats are `cityjson`, `gpkg`,
`obj`, `cityjson_terrain`, and `3dtiles`. Terrain output requires terrain enabled
in the effective configuration. Independent conversion and 3DCityDB are deferred.

Build releases in this repository:

```sh
uv build --package ogc-processes
uv build --package roofer-processes-contracts
```

Copy the two versioned wheels to Roofer's `apps/api/vendor`, update its exact
dependency pins and wheel paths together, then regenerate its lock with `uv lock`.
The API Docker build copies the wheels before installing frozen dependencies.
Roofer deployment instructions are in its `docs/ogc-processes.md`.

## Verification limits

The integration checks cover PostGIS registration and migration, JWT ownership,
partial ingestion, requested outputs, restart recovery, and real Dagster launch,
failure, and exact-run materialization access using isolated fixture jobs.
They do not establish production acceptance of the actual Roofer tools, live BAG
data, public remote sources, or deployed proxy configuration. Keep v2 disabled
until the staging checks in Roofer's runbook pass.
