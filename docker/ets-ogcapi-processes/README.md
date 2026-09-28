# OGC API - Processes TEAM Engine check

This folder runs the OGC CITE Executable Test Suite (ETS) for OGC API - Processes
Part 1 (1.0) in the official `ogccite/ets-ogcapi-processes10` container. The
GitHub Actions job starts this API checkout on the runner, starts TEAM Engine
with host networking, then submits an ETS run through TEAM Engine's REST API.
The IUT URL is therefore the just-started API, not the staging deployment.

The runner expects Docker, Python, and the API dependencies to be available. For
a local run, start the API on port 8000 and the ETS container on the host network:

```sh
docker run --network host --detach --name ogc-processes-ets ogccite/ets-ogcapi-processes10
python docker/ets-ogcapi-processes/run_ets.py
docker rm --force ogc-processes-ets
```

The runner writes an EARL XML report to `artifacts/ogc-processes-ets.xml`. The
default TEAM Engine test account in the ETS image is `ogctest` / `ogctest`.
Override `TEAM_ENGINE_URL` or `OGC_IUT_URL` to use a different reachable
instance. Do not point this runner at a production service unless that is
specifically intended.

The suite requires an echo process ID. This API already advertises `echo`, but
it previously could not execute it through the Roofer-only contract adapter;
the echo input and output are now passed through as strings for ETS execution.

This is a compliance check for the published Processes 1.0 Part 1 suite. The
existing `just ogc-check` command remains complementary: it checks the generated
OpenAPI document against the 2.0.0 draft using `@geonovum/ogc-checker`.
