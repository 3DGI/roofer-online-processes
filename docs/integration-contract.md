# Roofer Online integration contract

The reusable protocol app requires a catalog, execution backend, job store, authenticator and
contract validator. The Roofer models in `api.process_contracts` define the four public contracts.
Invoke host application services internally and persist owned OGC jobs/results with mappings to
Roofer processes and workflow run IDs. Authenticate all job, asset, and artifact operations using
the host user system. Never expose filesystem paths, submitted URLs, or connection credentials.

The reference service accepts demo bearer subjects (missing authorization defaults to `demo`);
this is development behavior. Its built-in IDs are per-subject fixtures; generated resources are
owned by their creator. Production must use the host authentication and real readiness checks.
Demo point-cloud IDs 1, 123, 124, BAG IDs 2/456 and model ID 789 are available. Registered complete
upload 123, incomplete upload 125, and remote URLs `https://data.example/survey.laz`,
`https://data.example/invalid.laz`, `https://data.example/failed.laz` exercise readiness/invalid/failure.
Other remote URLs safely fail without being downloaded. BAG pand fixture identifiers are
`0000000000000001` through `0000000000000003`, with footprints at x=0–2, 4–6, 8–10 and y=0–2.
The fixture BAG dataset date is 2026-01-01. Artifact base URL is configurable on ReferenceBackend.

## Local upload workflow

Use the host's authenticated [Tus service](https://tus.io/protocols/resumable-upload) to create
and complete an upload. The production adapter must add creation metadata `processing=ogc`
(encoded as `Upload-Metadata: processing b2dj` alongside existing required metadata).
OGC uploads transfer bytes without automatically starting metadata validation. Omitted flags retain
today's automatic UI processing. This flag and byte-transfer service are not implemented here.
Confirm completion through Tus offsets before submitting preparation:

```json
{"inputs":{"point_clouds":[{"kind":"upload","upload_url":"https://roofer.example/api/v1/pointcloud/upload/123"}]}}
```

POST to `/ogcapi/processes/roofer:validate_point_cloud:v1/execution` with the authenticated bearer
header and `Prefer: respond-async`. Follow the `Location` returned with HTTP 201 and poll it until
`status` is `successful` or `failed`. On success GET `<Location>/results` and inspect
`outputs.validation_report.point_clouds`. Use only entries with `ready: true` and retain their
`point_cloud_id`. A successful job can contain invalid/failed sources and `all_ready: false`.

## Remote preparation and existing assets

The same process accepts a public or presigned HTTP(S) LAS/LAZ URL, without extra credentials:

```json
{"inputs":{"point_clouds":[{"kind":"url","url":"https://data.example/survey.laz"},{"kind":"asset","asset_id":124}]}}
```

Poll preparation as above. Reports never echo URLs or credentials. Successfully prepared remote
sources create owned point-cloud assets, reusable even when another source fails.

## Reconstruction and downloads

POST `/ogcapi/processes/roofer:reconstruct_buildings:v1/execution` with ready IDs and a selector:

```json
{"inputs":{"point_cloud_ids":[123],"bag":{"kind":"buildings","building_ids":["0000000000000001"]},"name":"Demo","config":{}}}
```

Alternatively use `{"kind":"asset","asset_id":456}` or
`{"kind":"area","wkt":"POLYGON ((-1 -1,3 -1,3 3,-1 3,-1 -1))","crs":"EPSG:28992"}`.
Area lookup buffers by one metre and dissolves overlaps before full footprint containment.
Missing identifiers, empty selections and feature-limit overflow are errors, never truncated results.
Poll the reconstruction job and GET its results. `outputs.building_model` records the resolved
`bag_id`, sorted `building_ids`, model ID, available dataset date and `artifacts`.
Download each artifact's `href` with Roofer authorization; demo archives contain fixture text.
Resolved selection does not promise an immutable BAG geometry snapshot.

Conversion and export examples:

```json
{"inputs":{"model_3d_id":789,"formats":["cityjson","obj","gpkg","3dtiles"]}}
```

```json
{"inputs":{"model_3d_id":789,"sharedProfileId":"municipality-citydb","importMode":"import_all","reasonForUpdate":"DTaaS testbed","updatingPerson":"operator"}}
```

Submit to `roofer:convert_format:v1` and `roofer:export_to_3dcitydb:v1` respectively.
Outputs are `converted_model` (model ID/artifacts) and `export_receipt` (model ID/completed,
optional profile/count). Formats also include `cityjson_terrain`. Explicit CityDB connections use
`host`, strict `port` (1–65535), `database`, `user`, `password`, optional `schema` (citydb),
`useSSL` (false). A shared profile takes precedence and removes explicit connection settings.
`importMode` supports `import_all`, `skip`, `delete`, `terminate`. Credentials are transient.

## Required production adapter changes

- Implement the upload metadata flag described above; resolve uploads internally with ownership
  and completion checks before creating jobs.
- Check ownership, readiness and CRS compatibility for all point clouds, BAG assets and models.
- Implement remote ingestion with byte/time/download limits, target and redirect checks, and
  confidential presigned URL handling. Never forward Roofer authorization or accept extra remote
  credentials. Persist successful sources through partial preparation failures.
- Reuse host BAG resolution and asset-creation services. Enforce complete selections instead of
  today's capped lookup; reject missing IDs and feature-limit overflow.
- Advertise asynchronous execution for production preparation and reconstruction; implement
  actual workflows, standalone conversion, safe CityDB receipts, durable mapping and results.
- Map accepted/running/successful/failed states and reporting-workflow failure. Cancellation,
  callbacks and output transmission negotiation remain separate milestones; do not advertise
  unsupported extensions.
