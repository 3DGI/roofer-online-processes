# Implementation

Status reviewed on 2026-10-06. This describes the current reference implementation.
The OGC linter and compliance suite are fully green, as confirmed by the project
owner; neither was rerun during this review. Python tests and the end-to-end script
were read as source, not executed.

## Components and publication

`packages/ogc-processes` supplies protocol models, injected interfaces, and a
mountable FastAPI application. `apps/api` supplies concrete contracts and a
fixture catalog/backend/store/authenticator, mounted at `/ogcapi`.

The catalog publishes `echo` and three Roofer processes. **3DCityDB export is
intentionally deferred and unpublished.** Its Pydantic models, registry entry,
example, and fake backend branch remain in source. Description and execution
requests for that process return 404 before validation or submission.

## HTTP API

Paths below are relative to `/ogcapi`.

| Method and path | Behavior |
| --- | --- |
| `GET /` | Landing links to OpenAPI, conformance, processes, jobs |
| `GET /conformance` | Core, JSON, OGC process description and Job list classes for v2 and v1 |
| `GET /openapi.json` | OpenAPI 3.0.3 with relative OGC paths |
| `GET /processes` | Catalog, default limit 10; allowed limit 1–1000 |
| `GET /processes/{process_id}` | Named schemas, full Roofer `inputsSchema`, outputs, modes and links |
| `POST /processes/{process_id}/execution` | Validate request and submit; sync 200 or async 201 |
| `GET /jobs` | Caller-scoped refreshed jobs with filters and limit |
| `GET /jobs/{job_id}` | Caller-scoped refreshed status |
| `GET /jobs/{job_id}/results` | Successful output document; optional comma-separated `outputs` selection |
| `GET /jobs/{job_id}/results/{output_id}` | Individual validated output value |
| `GET /jobs/{job_id}/results/{output_id}/0` | Alias for individual output retrieval |

The parent app also exposes `/`, `/health`, `/docs`, `/openapi.json`, and
`/api/v1/reconstruction/{model_3d_id}/export/{format}`. Parent Swagger projects
OGC paths with the `/ogcapi` prefix; it does not describe every host route.
The host artifact route serves registered model/format fixture bytes without
authentication. Missing registration, format or file returns 404.

### Execution and result representations

All published reference processes advertise sync and async execution and only
`value` transmission. `Prefer: respond-async` selects async; otherwise execution
is sync. Async responses include `Location`, `Preference-Applied: respond-async`,
and an accepted job. Fixture work is done during submission and ordinary jobs
become successful on polling; there is no background worker.

`response` defaults to `raw`. A single raw output is text or JSON; multiple raw
outputs use `multipart/related` (exercised by `echo`). `response: document` returns
output IDs at the document root, wrapping object values in `{"value": ...}`.
Job results use the same document representation and supply per-output HTTP
`Link` headers. The internal `Results.outputs` wrapper is not the wire document.

Unknown/empty requested outputs and unsupported transmission modes return 400
before submission. Contract validation normalizes Roofer inputs before submission
and validates backend results before projection. Invalid domain inputs produce a
generic 400; invalid backend outputs produce a generic 500. Unavailable results
return 404 with `result-not-ready`; failed-job results return 500. Job statuses
include v2 `id`/`processingEntityType` and compatibility `jobID`/`type` fields.

`subscriber` is accepted but ignored. Prefer conflicts/wait negotiation are not
implemented. No cancellation/dismissal or Part 2 lifecycle routes are present.

### Job listing

Filters are `type`, `processID`, `status`, `datetime`, `minDuration`, `maxDuration`,
and `limit`. Type accepts `process` or `ogc-api-processes`; durations are nonnegative
and an inverted duration range is rejected. Datetime matches job creation time;
duration filters require started and finished timestamps. Collections truncate
without pagination links. Invalid, naive, and reversed datetime filters need
hardening. Reference status polling recreates lifecycle timestamps and is not a
model for persistent production status. The special paused `echo` fixture remains
running with unavailable results and currently reports a finished timestamp.

## Roofer contracts

`apps/api/src/api/process_contracts.py` defines input/output Pydantic models and
`CONTRACTS`. Discovery derives named schemas and full `inputsSchema` from them;
runtime validation uses the same models. `inputsSchema` is an extension describing
constraints across named inputs. Each named input has maxOccurs 1, with required
fields marked minOccurs 1. `echo` has separate conformance fixture handling.

Roofer contract models forbid undeclared fields. IDs are strict positive integers;
required text is nonblank; selected lists reject duplicates. URLs must be HTTP(S)
with a hostname, without embedded credentials or fragments. `config` is free-form
JSON checked for non-finite numbers; these checks do not establish remote retrieval
safety or host authorization.

| Published process | Inputs | Single output |
| --- | --- | --- |
| `roofer:validate_point_cloud:v1` | Nonempty unique `point_clouds` list of `{kind: "url", url: ...}` only | `validation_report` |
| `roofer:reconstruct_buildings:v1` | Unique `point_cloud_ids`, required `bag`, optional `name`/`config` | `building_model` |
| `roofer:convert_format:v1` | `model_3d_id`, nonempty unique `formats` containing `cityjson`/`gpkg` | `converted_model` |

Preparation rejects `upload` and `asset` source forms. The backend waits five
seconds even for async submission, then creates a fresh owned fixture cloud for
each source and reports all ready. It never downloads URLs or inspects LAS/LAZ.
The report contract supports ordered ready/invalid/failed outcomes and a consistent
`all_ready`; a ready outcome must have a point-cloud ID. URLs are not echoed.

BAG selectors are `{kind: "asset", asset_id: ...}`, `{kind: "buildings",
building_ids: [...]}`, or `{kind: "area", wkt: ..., crs: "EPSG:28992"}`. WKT must
be a valid nonempty Polygon/MultiPolygon. Reference area resolution buffers one
metre before full containment against three fixture footprints. Empty/missing
selections and feature-limit overflow fail rather than truncate. Building results
include sorted unique building IDs, resolved BAG ID, model ID, fixture dataset
date, optional name, and typed artifact links. Reconstruction and conversion
serve the same static files from `data/`, included in the Docker image.

Deferred export scaffolding requires a model and a shared profile or complete
connection, removes explicit connection fields when a profile takes precedence,
and defines an `export_receipt` with `completed: true`. It is not a public API
contract in the current catalog and executes no actual database export.

## Production and verification boundary

Demo bearer tokens are unverified subjects; missing/unusable authorization uses
`demo`. Jobs and generated fixture records are subject-scoped in memory. Built-in
cloud/BAG/model IDs are available per subject. Public downloads check registrations
across subjects. Restart loses all jobs, results and generated registrations.

Production must provide Roofer authentication, ownership/readiness checks, safe
ingestion, authoritative BAG resolution, workflow execution, persistent
job/run/asset/result mapping, stable lifecycle timestamps and authorized artifacts.
Area-selector WKT must use EPSG:28992. Point-cloud CRS metadata is not inspected;
clients are responsible for coordinate alignment. The protocol/backend/store calls
do not make workflow submission and mapping persistence atomic.

CI contains Python checks, Geonovum v2 linter and TEAM Engine v1 compliance workflows.
The green standards checks establish the current advertised surface; they do not
establish real ingestion, Dagster execution, restart recovery, or production access
control. Existing source tests cover contract schemas, invalid-input side effects,
output representations/selection, subject isolation, fixture downloads, and the
unpublished export boundary. See [gap-analysis.md](gap-analysis.md) and
[next-implementation-steps.md](next-implementation-steps.md) for follow-ups.
