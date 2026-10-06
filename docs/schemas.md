# OGC API - Processes schema catalog

The schema files live in the [`openapi/schemas`](https://github.com/opengeospatial/ogcapi-processes/tree/master/openapi/schemas) directory of the OGC API - Processes repository.

## Remote file URL pattern

Open an individual schema as raw text using:

```text
https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/refs/heads/master/openapi/schemas/{directory}/{filename}
```

For example, [`process.yaml`](https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/refs/heads/master/openapi/schemas/processes-core/process.yaml) defines a process description. To find a filename, open the directory link in the catalog below.

## Catalog

| Schema group | Browse files | What it contains |
| --- | --- | --- |
| Processes Core | [Directory](https://github.com/opengeospatial/ogcapi-processes/tree/master/openapi/schemas/processes-core) | Process descriptions and summaries (`process.yaml`, `processSummary.yaml`), input/output definitions (`inputDescription.yaml`, `outputDescription.yaml`), and execution, value, job, and result schemas. |
| Common Core | [Directory](https://github.com/opengeospatial/ogcapi-processes/tree/master/openapi/schemas/common-core) | Shared API schemas, including landing pages, conformance declarations, links, and exceptions. |
| Job Management | [Directory](https://github.com/opengeospatial/ogcapi-processes/tree/master/openapi/schemas/processes-job-management) | Job definitions, status and list schemas, headers, and process graph support. |
| Workflows | [Directory](https://github.com/opengeospatial/ogcapi-processes/tree/master/openapi/schemas/processes-workflows) | Workflow execution and schemas for process inputs, outputs, and values used in workflows. |
| Common Geodata | [Directory](https://github.com/opengeospatial/ogcapi-processes/tree/master/openapi/schemas/common-geodata) | Geodata collection descriptions, extents, grids, dimensions, and collection properties. |

To form a direct URL, replace `{directory}` and `{filename}` in the pattern with the directory name and file name. For example:

```text
https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/refs/heads/master/openapi/schemas/processes-core/inputDescription.yaml
```

## Local implementation status (2026-10-06)

The upstream links above are reference material, not the authoritative contract
for this service. Current protocol models are in
`packages/ogc-processes/src/ogc_processes/models.py`; Roofer runtime contracts and
JSON Schema generation are in `apps/api/src/api/process_contracts.py`.

Read `/ogcapi/openapi.json` for the advertised OpenAPI 3.0.3 surface and
`/ogcapi/processes/{process_id}` for named input/output schemas and the complete
Roofer `inputsSchema` extension. Named input schemas include only their referenced
`$defs` dependencies; the full input schema captures constraints across inputs.
Runtime validation also enforces rules such as geometric validity and output
consistency that clients should not infer from schema validation alone.

Preparation accepts URL sources only. Conversion and artifact keys support only
`cityjson` and `gpkg`. Export models remain in source, but 3DCityDB export is
intentionally deferred and unpublished. Catalog availability, rather than the
presence of a Python model or registry entry, determines executable processes.

The OGC linter and compliance checks are fully green, as confirmed by the project
owner; they were not rerun during this review. See [implementation.md](implementation.md)
for the API behavior and [examples.md](examples.md) for current requests.
