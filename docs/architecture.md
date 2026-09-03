# Architecture

The `ogc-processes` package owns the HTTP protocol layer and depends only on injected interfaces.
It does not import Roofer Online models, database code, authentication code, or Dagster.

Roofer Online will provide a host adapter implementing the execution, status, results, dismissal,
authentication, and persistent job-store interfaces. The adapter maps public OGC job IDs to the
existing Roofer process IDs and Dagster run IDs. Existing Roofer routes remain authoritative for
asset ownership and artifact access.

The reference API in `apps/api` uses deterministic fake services. It exists for local development,
contract tests, and demonstrations; it is not a copy of the POC pipeline and is not a production
workflow engine.

