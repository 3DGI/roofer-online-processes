# Roofer Online integration contract

Status updated on 2026-10-06. The current service is a deterministic reference
host with three published Roofer processes plus `echo`. **3DCityDB export is
intentionally deferred and unavailable through the public API.**

## Injected host interfaces

`create_app` requires `catalog`, `backend`, `store`, `authenticator`, and `validator`.
Their protocols are in `packages/ogc-processes/src/ogc_processes/interfaces.py`.

| Interface | Host responsibility |
| --- | --- |
| `ProcessCatalog` | List and describe only available processes and their capabilities |
| `ProcessContractValidator` | Validate/normalize inputs before submission and outputs before projection |
| `Authenticator` | Resolve a verified host principal from authorization |
| `ExecutionBackend` | Submit using normalized inputs, subject and mode; expose status and results |
| `JobStore` | Create/get/list/update owned public jobs and their upstream mapping |

Invoke host application services internally. Persist public jobs and results with
owner, Roofer process/model/asset IDs, workflow run ID, and stable timestamps.
Scope every read and input resolution to authorized users. Handle the gap between
submission and mapping persistence. Required artifacts/materializations must exist
before terminal success. Translate execution failures into failed jobs and reject
invalid inputs before launching work.

The protocol has no cancellation interface. Its model accepts subscribers but
provides no callback dispatch. Advertise only implemented modes/transmission and
conformance classes. For async-only production processes, clients currently need
`Prefer: respond-async` because the router otherwise selects sync.

## Current reference contracts

Execute requests wrap values in `inputs`; there is no execute-body `mode` field.
See [examples.md](examples.md) for a complete reference workflow.

- Preparation accepts only URL sources, with no extra remote credentials. Upload
  and existing-asset source forms return 400. It currently waits five seconds and
  reports every URL ready without fetching it, allocating new owned fixture IDs.
- Reconstruction requires ready point-cloud IDs and a `bag` asset/buildings/area
  selector. Area WKT is Polygon/MultiPolygon in EPSG:28992, buffered one metre for
  full footprint containment. Missing/empty/over-limit selections fail. Results
  record resolved BAG ID, sorted building IDs and available dataset date; they do
  not promise an immutable geometry snapshot.
- Conversion accepts a model ID and unique `cityjson`/`gpkg` formats. Results link
  to the public fixture files; no conversion engine runs.

The reference authenticator uses arbitrary bearer text as subject, defaulting to
`demo`. Built-in cloud IDs 1/123/124, BAG IDs 2/456 and model ID 789 are available
per subject. Generated resources remain owned by their creator. Fixture building
IDs are `0000000000000001` through `0000000000000003`, with footprints at x=0–2,
4–6, 8–10 and y=0–2, and dataset date 2026-01-01. There is no registered-upload
fixture or special invalid/failed URL behavior in the current backend.

Synchronous output defaults to raw. `response: document` returns output IDs at
the root and qualifies object values as `{"value": ...}`. Job result documents
use the same representation; HTTP Link headers identify individual output routes.
Catalog transmission is value-only: nested artifact links do not implement OGC
reference transmission. Reference downloads need no authentication; production
must enforce host access rules or use signed links.

## Required production work

- Implement remote retrieval with byte/time limits, redirect/target checks, and
  confidential presigned URL handling. Never forward host authorization. Syntax
  validation alone does not authorize a network target.
- Inspect real point clouds and preserve successful owned assets through partial
  batch failure. The report contract supports invalid/failed outcomes and
  `all_ready: false`; a completed report can still be a successful OGC job.
- Resolve authoritative BAG selections and enforce ownership, readiness, EPSG:28992
  area-selector WKT, complete identifier resolution and feature limits. Point-cloud
  CRS metadata is not inspected; coordinate alignment with the BAG data is the
  caller's responsibility.
- Submit actual reconstruction and independent conversion workflows, retain durable
  mapping/results, and produce retrievable authorized artifacts.
- Use real authentication, stable lifecycle mapping, restart recovery, and safe
  diagnostics that omit source URLs, credentials and filesystem paths.

Tus `processing=ogc` metadata and upload/asset preparation were earlier proposals.
Neither is implemented or accepted here. Adding them requires public schema and
adapter work; retain them as future options rather than client instructions.
3DCityDB credentials/receipts remain deferred scaffolding and are excluded from
current adapter acceptance. See [next-implementation-steps.md](next-implementation-steps.md).
