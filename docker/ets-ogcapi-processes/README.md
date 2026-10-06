# OGC API - Processes TEAM Engine check

This folder runs the OGC CITE Executable Test Suite (ETS) for OGC API - Processes
Part 1 (1.0) in the official `ogccite/ets-ogcapi-processes10:1.3-teamengine-6.0.0-RC2` container. The
GitHub Actions job starts this API checkout on the runner, starts TEAM Engine
on a bridge network, then submits an ETS run through TEAM Engine's REST API.
The IUT URL is therefore the just-started API, not the staging deployment.

The runner expects Docker, Python, `just`, and a locally running API. Start the
API on port 8000 so it listens on the host network interface:

```sh
just api-run
```

In another terminal, start TEAM Engine and run the headless ETS through its REST
API:

```sh
just ogc-teamengine-up
just ogc-compliance
just ogc-teamengine-down
```

The default IUT URL is `http://host.docker.internal:8000/ogcapi/`, which lets
the Team Engine container reach the host API. Pass another URL to test a
different reachable API, for example `just ogc-compliance
http://host.docker.internal:18082/ogcapi/`. CI uses the same `just` recipes.
The runner writes an EARL XML report to `artifacts/ogc-processes-ets.xml`.
Override `TEAM_ENGINE_URL` when using a different Team Engine instance. Do not
point this runner at a production service unless that is specifically intended.

The suite requires an echo process ID. This API already advertises `echo`, but
it previously could not execute it through the Roofer-only contract adapter;
the echo process returns the input string and its character count. With the default
`response: raw`, both outputs are returned as `multipart/related`, with a `text/plain`
part for the string and an `application/json` part for the count. Selecting only
`value` returns `text/plain`. This exercises raw output transmission without the
ETS 1.3 synchronous JSON schema's overlapping `oneOf` branches. The validator is
unchanged, and both synchronous and asynchronous echo execution remain available.

Request `response: document` for a JSON result document. Output IDs are its top-level
keys; object output values are qualified as `{"value": <object>}`. Job result
documents use the same encoding, with per-output links in the HTTP `Link` header.

This is a compliance check for the published Processes 1.0 Part 1 suite. The
existing `just ogc-lint` command remains complementary: it checks the generated
OpenAPI document against the 2.0.0 draft using `@geonovum/ogc-checker`.
