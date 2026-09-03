# OGC API Processes and Roofer Online Gap Analysis

## Scope

This report maps the four processes promised in the DTaaS proposal to the current Roofer Online API and workflow implementation. It defines the adapter required to expose those capabilities through OGC API Processes.

## Standards baseline and verification result

The implementation target is **OGC API - Processes Version 2**, primarily Part 1: Core v2.0 ([18-062r3](https://docs.ogc.org/DRAFTS/18-062r3.html)) and, where dynamic process lifecycle is required, Part 2 ([20-044](https://docs.ogc.org/DRAFTS/20-044.html)). Both documents are currently drafts and are being implemented deliberately as draft specifications. The approved Part 1 1.0.0 document ([18-062r2](https://docs.ogc.org/is/18-062r2/18-062r2.html)) remains the compatibility baseline.

The host-side conclusions below are sound: validation against an existing asset and independent format conversion need host operations, while reconstruction and CityDB export already have backend workflows that can be adapted. The protocol constraints are:

- Part 1 Core requires the landing page, conformance declaration, process list and descriptions, process execution, and job status/results. The `/jobs` collection is the optional Job list conformance class, not a Core requirement.
- Version 2 does not require exposing Part 2 lifecycle operations for a fixed catalog. Part 2 applies only when the server dynamically deploys, replaces, or undeploys process definitions; a fixed Roofer catalog can implement Part 1 v2 without those mutating endpoints.
- An OGC execute request wraps process-specific values in an `inputs` object. The examples below show process values; the adapter must wrap each one as `{"inputs": <process-specific-values>}` in the OGC execute request.
- Execution mode is negotiated from `jobControlOptions` and the HTTP `Prefer` header (`respond-sync` or `respond-async`); `mode` is not a v2 Part 1 execute-body field. Existing long-running Dagster workflows should use asynchronous execution.
- OGC job status values are `accepted`, `running`, `successful`, `failed`, and `dismissed`. `dismissed` is part of the optional Dismiss conformance class, so cancellation is required only if that extension is advertised.
- Process outputs must be declared in the process description and returned by value or reference according to the advertised transmission mode. Artifact links may point to authenticated Roofer download URLs, but local filesystem URIs must not be exposed.

The reusable package is currently shaped around the approved 1.0 wire model: it uses jobID, omits the v2 processingEntityType, and declares 1.0 conformance URIs. It therefore needs a v2 alignment pass before implementation is complete. The v2 draft preserves the core resource and execution model, but its status schema uses id and requires processingEntityType; these fields must be implemented even when the v1 validator is used as a compatibility gate.

## Compatibility validation strategy

The official OGC Processes validator currently targets the approved 1.0.0 conformance suite, while the Geonovum checker lists both 1.0.0 final and 2.0.0 draft support. Run the v1 validator as a backwards-compatibility regression gate, and run the v2 draft checker/tests as the authoritative conformance check for v2-only fields and requirements. A v1 pass demonstrates compatibility with the v1 subset; it does not by itself prove full v2 conformance.

## Current Roofer Online API

Roofer Online is a FastAPI application backed by SQLAlchemy models and Dagster. Users and assets are authenticated through Authgear JWTs. `Asset` is the base entity for point clouds, BAG data, and 3D models. `Process` tracks a user-owned background operation and contains a process type, status, optional asset ID, optional Dagster run ID, error message, and timestamps. The internal process types are `point-cloud-upload`, `reconstruction`, and `3dcitydb-export`; there is no internal process type for format conversion or standalone point-cloud validation.

Relevant endpoints:

| Capability | Existing endpoint | Current behavior |
| --- | --- | --- |
| Point-cloud upload and metadata | `POST /api/v1/pointcloud/upload`, `PATCH /api/v1/pointcloud/upload/{upload_id}` | Creates a `PointCloud` and a `point-cloud-upload` `Process`. When the Tus upload completes, a background task submits the Dagster `pointcloud` job. |
| Point-cloud status | `GET /api/v1/processes/{process_id}/status` | Polls Dagster, maps the run to `ok`, `in-progress`, or `error`, and writes LAS metadata, bounds, density, and asset status on success. |
| Reconstruction submission | `POST /api/v1/reconstruction/start` | Validates owned point-cloud and BAG IDs, creates a `Model3D` and a `reconstruction` `Process`, then submits the Dagster `reconstruct` job in a background task. |
| Reconstruction status | `GET /api/v1/processes/{process_id}/status` | Polls the stored Dagster run and materializations. On completion it stores model metadata, export URIs, storage size, and model status. |
| Reconstruction assets | `GET /api/v1/reconstructions`, `GET /api/v1/pointclouds` | Lists only the authenticated user’s assets. |
| Format downloads | `GET /api/v1/reconstruction/{model_3d_id}/export/{format}` | Serves stored ZIP artifacts for `obj`, `gpkg`, `cityjson`, `cityjson_terrain`, and `3dtiles`. |
| 3D Tiles files | `GET /api/v1/reconstruction/{model_3d_id}/3dtiles/{lod}/{file}` | Serves individual tileset files for `lod12`, `lod13`, and `lod22`. |
| CityDB profiles | `GET /api/v1/3dcitydb/connection-profiles` | Lists shared profiles without passwords. |
| CityDB export | `POST /api/v1/reconstruction/{model_3d_id}/export/3dcitydb` | Validates ownership, model status, CityJSON availability, and target policy, then submits the Dagster `job_export_3dcitydb` job and creates a `3dcitydb-export` process. Credentials are passed to Dagster but are not stored in the process record. |
| Process list/status | `GET /api/v1/processes`, `GET /api/v1/processes/{process_id}/status` | Lists and polls processes for the authenticated user. Status values are `ok`, `in-progress`, and `error`. |

## Gaps by proposed process

### `roofer:validate_point_cloud:v1`

There is no validation endpoint. Validation is an implicit post-upload operation: the completed Tus upload starts Dagster `pointcloud`, whose `pointcloud_metadata` asset runs `lasinfo`; the status poll copies LAS metadata into the point-cloud asset. The existing process is named `point-cloud-upload`, so it represents ingestion and validation together and cannot be submitted against an existing asset through a process-specific API.

The adapter must expose validation over existing point-cloud IDs. It must verify ownership and asset readiness, start or reuse the metadata workflow, and persist a process record dedicated to the OGC execution. The OGC result should contain validation state and metadata such as bounds, point count, classification codes, and point density. A failed validation is an OGC `failed` job with the stored error message; it does not produce a model.

Process-specific input values (to be placed under the OGC execute request `inputs` member):

```json
{"point_cloud_ids": [123]}
```

The current Dagster asset accepts one `pointcloud_path` and one `asset_id`; multiple IDs require one run per asset or a new batch operation.

### `roofer:reconstruct_buildings:v1`

`POST /api/v1/reconstruction/start` is a direct backend for this process. It accepts `point_cloud_ids`, `bag_id`, optional `name`, and a free-form Roofer `config`. It validates asset existence and owner/admin access, creates the model and process rows, and submits Dagster `reconstruct` with the point-cloud paths, BAG view, model ID/name, and configuration.

The existing Dagster `reconstruct` job is broader than reconstruction: its selection includes `reconstructed_building_models`, `export_cesium3dtiles`, and `export_multiformat`. The OGC adapter can call this operation and return all materialized outputs, or the host must split reconstruction from export if independent execution is required.

The current response already supplies the internal identifiers needed by the adapter: `model_3d_id` and `process_id`. The adapter must associate one public OGC job ID with both, plus the Dagster run ID once the background submission completes. Polling uses the process status endpoint and materialization metadata. Results reference the authenticated download endpoints rather than exposing filesystem URIs.

Process-specific input values (to be placed under the OGC execute request `inputs` member):

```json
{
  "point_cloud_ids": [123, 124],
  "bag_id": 456,
  "name": "Nijmegen centrum",
  "config": {}
}
```

The current implementation is asynchronous. There is no bounded synchronous reconstruction endpoint.

### `roofer:convert_format:v1`

There is no standalone conversion endpoint or process record. Format generation is currently part of the reconstruction Dagster job. `export_multiformat` produces OBJ, GeoPackage, CityJSON, and optional terrain CityJSON ZIPs; `export_cesium3dtiles` produces 3D Tiles files and a ZIP. Their URIs are merged into `Model3D.asset_metadata`, and the download endpoint resolves them from the model metadata.

The OGC process requires a new host operation. It should accept an existing `model_3d_id`, validate ownership and `ok` status, accept a list of supported formats, submit a dedicated Dagster conversion job, and create a process row with a conversion type. The job should reference the existing model’s reconstruction output and publish artifact URIs into a durable result record. Reusing the reconstruction job for this operation would incorrectly rerun reconstruction and would not provide independent conversion semantics.

Process-specific input values (to be placed under the OGC execute request `inputs` member):

```json
{"model_3d_id": 789, "formats": ["cityjson", "obj", "gpkg", "3dtiles"]}
```

Supported format identifiers are `obj`, `gpkg`, `cityjson`, `cityjson_terrain`, and `3dtiles`. The OGC result should contain one reference per requested format.

### `roofer:export_to_3dcitydb:v1`

`POST /api/v1/reconstruction/{model_3d_id}/export/3dcitydb` implements the required backend operation. It accepts either a shared profile ID or complete connection parameters, validates the model owner, requires model status `ok`, requires the stored CityJSON export, validates the target host, and submits Dagster `job_export_3dcitydb`. The process row has no asset ID and stores the Dagster run ID.

The endpoint returns a Dagster run ID but does not return the newly created internal process ID. The OGC adapter must retain that process ID when invoking the operation, or the endpoint must return it. Status is available through the generic process endpoint. The current process status has no successful export result other than the Dagster materialization log, so the adapter needs a result record containing the model ID, target profile identifier, completion state, and export summary.

Process-specific input values (to be placed under the OGC execute request `inputs` member):

```json
{
  "model_3d_id": 789,
  "sharedProfileId": "municipality-citydb",
  "importMode": "import_all",
  "reasonForUpdate": "DTaaS testbed",
  "updatingPerson": "operator"
}
```

Explicit connection parameters are also accepted by the internal API. They must be handled as transient execution data and excluded from OGC job resources, results, process metadata, and logs.

## OGC-to-Roofer adapter

The wrapper should be mounted in the Roofer Online FastAPI application and use its existing authentication and database session. It should not call Roofer’s HTTP endpoints from inside the same application. The adapter should invoke the existing service/background functions or a new application service that shares their models and authorization checks.

The public resource model is separate from the internal model:

| OGC resource | Roofer mapping |
| --- | --- |
| Process ID | Static adapter catalog entry, not a Roofer `ProcessType` value |
| OGC job ID | New durable mapping row containing OGC ID, Roofer process ID, model ID, Dagster run ID, owner, and requested process ID |
| Job owner | Authenticated JWT subject, checked against all referenced assets and the mapped process |
| `accepted` | OGC submission accepted and internal process created; Dagster run may not yet exist |
| `running` | Internal process is `in-progress` and the Dagster run is active or queued |
| `successful` | Internal process is `ok` and required materializations/artifacts are available |
| `failed` | Internal process is `error`, Dagster run failed, or a required materialization is missing |
| `dismissed` | Optional Part 1 Dismiss extension. If advertised, requires a cancellation operation that terminates the Dagster run and records dismissal; no current Roofer endpoint provides this |
| OGC results | References generated through authenticated Roofer download routes or signed artifact URLs |

The OGC execution endpoint should advertise asynchronous execution for the existing reconstruction, conversion, CityDB, and validation Dagster workflows. A new bounded host operation may additionally advertise synchronous execution. The adapter should negotiate the selected mode using the HTTP `Prefer` header and return `201 Created` plus `Location` for asynchronous executions; a successful synchronous execution returns the requested output representation directly.

## Required Roofer Online changes

1. Add an application service for OGC submissions instead of coupling the wrapper to route handlers and `BackgroundTasks`.
2. Add a standalone validation submission operation for existing point-cloud assets.
3. Add a standalone conversion Dagster job and process type for existing models.
4. Return the internal process ID from CityDB export submission, or provide a service-level return object containing it.
5. Add durable OGC job mapping and result persistence.
6. If the optional Dismiss conformance class is advertised, add a cancellation operation that maps OGC dismissal to Dagster cancellation and records the terminal state.
7. Expose artifact references through stable authenticated URLs; do not expose local `uri` values directly.
8. Preserve the existing JWT and owner/admin checks for every input asset, model, process, and job.
9. Normalize internal `ok`, `in-progress`, and `error` plus Dagster run states into the OGC job lifecycle and retain detailed error messages for failed jobs. Invalid input should be rejected as an execute exception before creating a job; execution-time failures should become `failed` jobs.
10. Update the protocol layer for v2 status and conformance fields (`id`, `processingEntityType`, v2 conformance URIs), HTTP `Prefer` negotiation, and the v2 OpenAPI schemas; retain v1 validator coverage as a compatibility regression test.


## Part 1 and Part 2 endpoint crosswalk

For the fixed Roofer catalog, the public adapter needs these Part 1 resources:

| OGC operation | Adapter responsibility |
| --- | --- |
| `GET /` | Link to the API definition, `/conformance`, and `/processes`; optionally `/jobs` if Job list is implemented |
| `GET /conformance` | Declare exactly the implemented Part 1 conformance classes |
| `GET /processes` | List the four stable public process identifiers and descriptions |
| `GET /processes/{processID}` | Describe named inputs, JSON schemas, outputs, job control options, transmission modes, and links |
| `POST /processes/{processID}/execution` | Validate inputs and authorization, submit the host workflow, and return a synchronous result or asynchronous job status with `Location` |
| `GET /jobs/{jobID}` | Return current OGC status and links, scoped to the authenticated owner |
| `GET /jobs/{jobID}/results` | Return declared output values or references after successful completion |

`GET /jobs` may be added and is already part of the proposed adapter contract, but it should be advertised as the Job list conformance class only after implementing its required filtering and response behavior.

Part 2 adds `POST /processes`, `PUT /processes/{processID}`, `DELETE /processes/{processID}`, and `GET /processes/{processID}/package` for dynamic process lifecycle management. Those operations are out of scope for the four fixed Roofer workflows. If added later, the server must distinguish immutable built-in processes from mutable dynamically deployed ones and enforce the stronger deployment authorization described by [Part 2](https://docs.ogc.org/DRAFTS/20-044.html).
