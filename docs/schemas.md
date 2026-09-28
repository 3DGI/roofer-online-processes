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
