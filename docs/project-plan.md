# Topic 1 project plan

This repository implements the OGC API - Processes layer for Roofer Online.
Status updated on 2026-10-06 from the current source and project-owner verification.

## Proposal schedule and current delivery status

The dates and hours below are the original proposal allocation, not revised estimates.

| Milestone | Due | Hours | Current status |
| --- | --- | ---: | --- |
| Gap Analysis and Design | 2026-09-03 | 26 | Protocol boundary, concrete contracts and current gap analysis documented; production adapter gaps remain |
| Core OGC Processes Implementation | 2026-10-01 | 64 | Reusable protocol and three Roofer reference processes implemented; production workflow/auth/storage adapter remains |
| Compliance and Interoperability Validation | 2026-10-20 | 26 | OGC linter and compliance fully green; CI configured; production and independent-client evidence remains |
| Demo, Documentation and Handoff | 2026-11-03 | 25 | Fixture service, deployment configuration and documentation available; live demo/release/videos/handoff completion not established by this review |

## Current scope

The API targets Part 1 v2 and declares v1 compatibility for Core, JSON, OGC process
description and Job list. Process identifiers ending in `:v1` version the Roofer
contract; they do not identify the OGC protocol version.

Published Roofer processes:

- `roofer:validate_point_cloud:v1`: URL-only preparation contract and fixture reports.
- `roofer:reconstruct_buildings:v1`: point-cloud IDs and BAG selector, fixture results.
- `roofer:convert_format:v1`: CityJSON and GeoPackage fixture conversion results.

`echo` is also discoverable as a conformance fixture. The fourth proposal process,
`roofer:export_to_3dcitydb:v1`, is intentionally postponed and omitted from the
public catalog. It is excluded from current milestone acceptance.

## Definition of done and remaining acceptance

| Criterion | Status |
| --- | --- |
| Three in-scope Roofer processes discoverable with concrete input/output contracts | Implemented in the reference API |
| Sync/async execution, status, result documents/raw output and output selection | Implemented for fixtures; real workflow lifecycle remains |
| Roofer authentication, asset ownership, persistent jobs and authorized artifacts | Production adapter remains |
| OGC linter and TEAM Engine compliance green for advertised capabilities | Fully green, confirmed by project owner; not rerun in this review |
| Independent-client and real workflow/failure/restart evidence | Remaining production integration work |
| Public documentation, demo evidence, release artifacts and six-month handoff | Documentation updated; full delivery not established |

Dismissal, callbacks, reference transmission, and Part 2 dynamic process management
are outside the currently advertised capabilities. Their absence is documented;
they are not required to declare the current fixture implementation complete.
Production delivery still requires the adapter and acceptance evidence above.

See [implementation.md](implementation.md), [gap-analysis.md](gap-analysis.md),
and [next-implementation-steps.md](next-implementation-steps.md).
