# Next implementation steps

Implementation update: the production v2 reconstruction adapter, durable worker,
remote ingestion, and contracts are implemented in the Roofer consumer. See
[roofer-integration.md](roofer-integration.md) for architecture and verification
limits. Independent conversion and public deployment acceptance remain deferred.
The assessment below describes the starting milestone requirements.

Assessment date: 2026-10-06. This replaces the 2026-09-16 assessment. The current
contracts, result representations, fixture downloads, and compliance CI are
implemented. The OGC linter and compliance suite are fully green, as confirmed
by the project owner, and were not rerun for this review.

**3DCityDB export is intentionally deferred.** The next milestone covers remote
point-cloud preparation, reconstruction, and CityJSON/GeoPackage conversion.
The existing export scaffolding stays unpublished.

## 1. Deliver a persistent reconstruction workflow

Implement `ExecutionBackend`, `JobStore`, and `Authenticator` using Roofer host
application services. Keep the existing contract validator and reusable router.
The reference backend is deterministic and does not submit Dagster runs.

Persist public job ID, owner, requested process ID, Roofer process/model/BAG IDs,
workflow run ID, timestamps, and result records. Handle submission/mapping failures
so accepted work cannot become untracked. Use actual host authentication and
ownership checks rather than demo bearer identities.

Resolve BAG selectors against authoritative data, enforce complete selection and
limits, and check point-cloud readiness/CRS compatibility. Publish successful
results only when expected outputs are available through authorized downloads.
Production reconstruction should advertise async execution; the current router
requires clients to send `Prefer: respond-async` for async-only processes because
its default is sync.

Acceptance evidence:

- Invalid or unauthorized requests submit no workflow.
- A public job maps to the exact submitted run and reflects accepted/running/terminal states.
- Successful jobs expose downloadable outputs; submission/run/output failures are explicit.
- Jobs and results survive restart and remain scoped to their owner.
- Mapping persistence failures can be recovered without leaving an untracked run.

## 2. Replace remote preparation fixtures with ingestion

Keep the current URL-only source contract unless an extension is explicitly agreed.
The reference implementation currently waits five seconds and reports all sources
ready; it performs no download or point-cloud validation.

Implement bounded HTTP(S) downloads, target/redirect checks, confidential presigned
URL handling, and real LAS/LAZ metadata extraction. Do not forward host credentials.
Preserve ordered outcomes and successfully prepared owned assets through partial
failures. A completed report may be successful with `all_ready: false`; failure of
the reporting workflow must produce a failed job. Move work out of submission so
async acceptance does not wait for preparation.

Upload sources, Tus `processing=ogc` metadata, and existing-asset preparation remain
possible future extensions. They are not accepted by today's preparation schema.

## 3. Implement independent conversion

Convert an existing owned ready model into requested `cityjson`/`gpkg` outputs,
without rerunning reconstruction. Persist artifact records and return usable
host-authenticated or signed URLs. Broader formats require coordinated changes
to the enum, output models, backend, examples, and contract coverage.

## 4. Harden runtime behavior

See [gap-analysis.md](gap-analysis.md) for source findings:

- Validate datetime filters independently of job count, require or normalize timezones,
  and reject invalid/reversed intervals.
- Preserve stable started/finished timestamps; running jobs must not have finished times.
- Add collection pagination when needed and retain applied filters in navigation links.
- Define conflicting Prefer and bounded wait behavior before advertising support.
- Reject subscribers explicitly or implement callbacks before promising delivery.
- Add reference transmission or dismissal only with complete backend support and the
  appropriate advertised capabilities. Current transmission is value-only.

These are runtime follow-ups; the existing OGC linter and compliance checks are green.

## 5. Complete integration evidence and handoff

Keep the existing Python, OGC linter, and TEAM Engine CI gates. Existing source tests
cover schemas, invalid inputs, output selection, subject isolation, fixture artifacts,
and unpublished export behavior. They do not establish production readiness.

Exercise real workflow submission/failure, exact run mapping, expected materializations,
artifact retrieval, ownership isolation, partial ingestion, and restart recovery once
the adapter exists. Use any sibling workspace as a consumer of the reusable package;
its current implementation was not re-reviewed here.

Complete independent-client/demo evidence, deployment verification, release artifacts,
and the handoff report. The proposal dates remain in [project-plan.md](project-plan.md);
this assessment does not assign new dates or claim these deliverables are finished.
