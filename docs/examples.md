# Reference API examples

These examples match the published API as reviewed on 2026-10-06. Run the
reference service at `http://localhost:8000`; OGC routes are under `/ogcapi`.
Use the same `Authorization: Bearer example-user` header for execution, polling,
and results. Tokens are demo identities rather than verified credentials.

The service lists `echo`, preparation, reconstruction and conversion. 3DCityDB
export is intentionally deferred: discovery and execution for it return 404.

## Prepare remote point-cloud sources

POST `/ogcapi/processes/roofer:validate_point_cloud:v1/execution` with
`Prefer: respond-async`, `Content-Type: application/json`, and:

```json
{
  "inputs": {
    "point_clouds": [
      {"kind": "url", "url": "https://data.example/survey.laz"}
    ]
  }
}
```

Only URL sources are accepted. Upload/asset source forms are not implemented.
The reference waits five seconds before responding, downloads nothing, and
reports all syntactically valid sources ready with fixture metadata.

Follow the 201 response's `Location` and GET that job with the same bearer header.
Ordinary reference jobs report successful on polling. GET `<Location>/results`:

```json
{
  "validation_report": {
    "value": {
      "all_ready": true,
      "point_clouds": [
        {
          "source_index": 0,
          "outcome": "ready",
          "ready": true,
          "point_cloud_id": 1000100,
          "crs": "EPSG:28992",
          "bounds": [0, 0, 10, 2],
          "point_count": 100,
          "point_density": 5.0
        }
      ]
    }
  }
}
```

The point-cloud ID shown is illustrative: use the actual returned ID. Production
reports may include invalid/failed sources; use only ready entries. Current
reference execution does not produce those real failure outcomes.

## Reconstruct

POST `/ogcapi/processes/roofer:reconstruct_buildings:v1/execution` with the same
headers, substituting a returned ready point-cloud ID. For a standalone fixture
example, cloud ID 123 is available:

```json
{
  "inputs": {
    "point_cloud_ids": [123],
    "bag": {"kind": "buildings", "building_ids": ["0000000000000001"]},
    "name": "Demo",
    "config": {}
  }
}
```

Alternative BAG selectors are `{"kind": "asset", "asset_id": 456}` or:

```json
{
  "kind": "area",
  "wkt": "POLYGON ((-1 -1,3 -1,3 3,-1 3,-1 -1))",
  "crs": "EPSG:28992"
}
```

Poll and fetch results as above. `building_model.value` contains the model ID,
resolved BAG ID, sorted building IDs, fixture dataset date, optional name, and
`artifacts.cityjson`/`artifacts.gpkg` with `href` and `type`. Download the returned
links without authentication in this reference service. They serve static demo
files, not newly reconstructed geometry. Production artifact access is adapter work.

## Convert formats

POST `/ogcapi/processes/roofer:convert_format:v1/execution`, using the returned
model ID or fixture ID 789:

```json
{
  "inputs": {"model_3d_id": 789, "formats": ["cityjson", "gpkg"]},
  "response": "document"
}
```

With `Prefer: respond-sync`, this returns HTTP 200 with
`converted_model.value.model_3d_id` and artifact links. Only `cityjson` and `gpkg`
are supported. For async, use `Prefer: respond-async` and follow `Location`.

## Result selection and raw output

GET `<Location>/results?outputs=converted_model` selects that output. GET
`<Location>/results/converted_model` or the `/0` alias retrieves its value directly.

Without a Prefer header, execution defaults to sync. Without `response: document`,
a single Roofer output is returned as its raw JSON object, without output-ID or
`value` wrappers. `echo` has multiple outputs and defaults to multipart raw output;
request a single output to receive plain text:

```json
{
  "inputs": {"value": "hello"},
  "outputs": {"value": {"transmissionMode": "value"}},
  "response": "raw"
}
```

POST this to `/ogcapi/processes/echo/execution`. The response is HTTP 200 with
`text/plain` body `hello`. Reference transmission requests are rejected; callbacks
are not delivered, and jobs cannot be dismissed through the current API.
