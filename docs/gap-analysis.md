# OGC API Processes and Roofer Online gap analysis

Assessment date: 2026-10-06. This review covers the implementation, API, tests,
CI configuration, and plans in this repository. Earlier observations about the
Roofer host and sibling integration workspace are historical context, not a
fresh assessment of those repositories.

## Current scope and verification

The protocol application targets OGC API - Processes Part 1 v2 and advertises
v1 compatibility. `/conformance` declares Core, JSON, OGC process description,
and Job list for both versions. The Geonovum v2 OGC linter and the TEAM Engine
v1 compliance suite are fully green, as confirmed by the project owner. Both
have CI workflows. Neither was rerun during this documentation review.

The proposal included four Roofer processes. Current delivery covers three
published Roofer contracts plus the `echo` conformance fixture. **3DCityDB export
is intentionally postponed and excluded from the current delivery milestone.**
It is not an active implementation gap. Part 2 dynamic deployment, dismissal,
and callbacks are not advertised by the current service.

## Implementation compared with the plans

| Capability | Current evidence | Remaining work |
| --- | --- | --- |
| Protocol boundary | Injected interfaces in `packages/ogc-processes/src/ogc_processes/interfaces.py`; no Roofer or Dagster imports in the protocol package | Implement production host services behind those interfaces |
| Discovery and schemas | `ReferenceCatalog` publishes `echo`, validation, reconstruction, conversion; named inputs and complete `inputsSchema` derive from Pydantic contracts | Keep descriptions and runtime behavior aligned when extending scope |
| Execute and results | Sync/raw/document, async 201 with Location, job polling, output selection and individual output routes | Real background execution, durable status and results |
| Job listing | Subject isolation, type/process/status/datetime/duration filters and bounded limit | Robust datetime validation, stable lifecycle timestamps, pagination |
| Validation/preparation | URL-only nonempty unique source list; ordered typed report; fixture always reports ready | Secure remote ingestion, actual metadata/validation and partial outcomes |
| Reconstruction | Ready fixture IDs; BAG asset/building/area selectors; buffered containment and selection limits; fixture model/artifact result | Authoritative BAG resolution, ownership/CRS checks and real reconstruction |
| Conversion | Existing fixture/generated model; only `cityjson` and `gpkg`; retrievable fixture downloads | Independent conversion workflow and durable artifact records |
| Authentication/storage | Demo bearer identities and in-memory subject-scoped jobs/results | Roofer authentication, persistent job/run/asset mapping and authorized downloads |
| 3DCityDB | Contract and backend scaffolding retained; catalog deliberately skips it; public description/execution return 404 | Deferred; reconsider only when explicitly restoring this scope |
| Standards checks | OGC linter and compliance fully green; CI configured | Maintain existing gates during changes; production integration needs separate evidence |

The former claims that inputs are generic, empty reconstruction requests succeed,
results are placeholder URNs, v2 fields are missing, and compliance automation is
unfinished no longer describe the current implementation.

## Domain gaps

### `roofer:validate_point_cloud:v1`

The current input is `point_clouds: [{kind: "url", url: "https://..."}]`.
Upload sources and existing-asset sources are rejected. Syntax validation accepts
HTTP(S) URLs with a hostname and rejects embedded credentials/fragments; it does
not check reachability or LAS/LAZ content. The backend sleeps five seconds during
submission, creates fresh owned fixture IDs for every URL, and reports every
source as ready without downloading it, including URLs named `invalid.laz` or
`failed.laz`. Async submission still performs this work before returning 201.

The output contract supports ready/invalid/failed source outcomes and consistent
`all_ready`, but the reference backend does not exercise real failures. Production
must ingest safely, inspect point-cloud data, preserve successful sources through
partial failures, and distinguish a completed report from reporting-workflow failure.
Tus integration and asset-based preparation require a future public-contract change.

### `roofer:reconstruct_buildings:v1`

The implemented inputs are `point_cloud_ids`, required `bag`, optional `name`, and
free-form finite JSON `config`. `bag` selects an asset, explicit building IDs,
or valid Polygon/MultiPolygon WKT in EPSG:28992. Fixture geometry is buffered by
one metre before full footprint containment; missing IDs, empty selections and
feature-limit overflow are rejected. Results contain a model ID, BAG ID, sorted
building IDs, fixture dataset date, and CityJSON/GeoPackage links.

This demonstrates the contract rather than invoking Roofer or Dagster. The
production adapter must resolve authoritative data, check all ownership/readiness
and CRS requirements, submit the actual workflow, and require its expected
materializations/artifacts before reporting success. Resolved identifiers and a
dataset date do not promise an immutable geometry snapshot.

### `roofer:convert_format:v1`

The current format enum is exactly `cityjson` and `gpkg`. OBJ, terrain CityJSON,
and 3D Tiles are outside the current public contract. Reference execution registers
requested formats for a fixture model and returns links to static files. A production
adapter still needs independent conversion of an existing owned ready model,
without rerunning reconstruction, and persistent records for requested outputs.

### Deferred `roofer:export_to_3dcitydb:v1`

`ExportInputs`, `ExportReceipt`, a registry example, and a fake backend branch remain
in source. Their presence does not make this an available API process. Future work
would need host target authorization, transient credential handling, actual export,
and durable receipts. No export deliverable or export acceptance check is required
for the current milestone.

## Protocol limitations and production boundaries

- `subscriber` is accepted but ignored; there is no callback delivery.
- Catalog entries advertise only `outputTransmission: ["value"]`. Reference requests
  are rejected before submission. Artifact `href` fields are nested domain values,
  not negotiated OGC reference transmission.
- No DELETE job route, dismissed status, cancellation interface, or Part 2 routes exist.
- Prefer handling selects async when `respond-async` appears, otherwise sync;
  conflicting preferences and wait negotiation are not handled explicitly.
- Job/process collections truncate to `limit` without next links or offset/cursor support.
- Datetime parsing can turn invalid values into an unbounded/no-match filter;
  comparing timezone-naive input to aware timestamps can raise an error. Reversed
  intervals are not explicitly rejected.
- The fake status method recreates started/finished times on each poll. The paused
  `echo` fixture remains running with unavailable results until state is cleared and
  reports a finished timestamp while running. These are fixture lifecycle limitations.
- Subject isolation applies to jobs and generated fixture records. Downloads are public
  and check model/format registration across subjects; production artifact authorization
  is still required.
- Workflow submission and job-store creation are separate calls. A persistent adapter
  must prevent or recover from untracked runs if saving the public mapping fails.

These findings do not change the reported green OGC checks; they define the
remaining runtime and production integration work. See
[next-implementation-steps.md](next-implementation-steps.md) for priorities.
