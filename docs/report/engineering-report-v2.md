# 3D building reconstruction from point clouds and building polygons with Roofer Online

Geonovum DTaaS Testbed 2026 Phase 2. Adoption topic #1: Implement and validate an OGC API Processes service

## Summary

3DGI added an OGC API – Processes interface to [Roofer Online](https://roofer-online.nl), which reconstructs 3D buildings from point clouds and building footprints. The contribution addresses Topic 1: exposing an existing calculation module through the nLDT architecture and making it usable by other vendors' clients.

There are two versions of the Roofer Online processes API.
- `v1`: A public demo that was developed for the testbed, and it uses fixture data. Live at [https://processes.staging.roofer-online.nl/ogcapi](https://processes.staging.roofer-online.nl/ogcapi). 
  - [process catalogue](https://processes.staging.roofer-online.nl/ogcapi/processes)
  - [Swagger UI](https://processes.staging.roofer-online.nl/ogcapi/docs)
  - [OpenAPI document](https://processes.staging.roofer-online.nl/ogcapi/openapi.json)
- `v2`: The client-facing live Roofer Online processes API, which requires a Roofer Online account and authentication. Live at  [https://roofer-online.nl/ogcapi](https://roofer-online.nl/ogcapi).

| | v1: public testbed demo | v2: live Roofer Online API |
| --- | --- | --- |
| Purpose | Let participants test discovery, execution, job handling and process chaining | Run building reconstruction within Roofer Online |
| Processing | Deterministic fixture results and sample CityJSON/GeoPackage files | Point-cloud ingestion, BAG selection, reconstruction and export |
| Access | Public, no access restriction | Public discovery; authenticated execution, jobs, results and artifact downloads |
| Processes | Separate validation, reconstruction and conversion processes | One reconstruction process incorporating preparation and requested exports |
| Execution | Synchronous and asynchronous | Asynchronous only |
| Testbed status | Tested| Not tested because authentication is required |


## Roofer Online


---

## Implementation

### Architecture

### Data

### Processes

### Live API

---

## Conformance

---

## Interoperability with other participants

### Future Insight

### IMAGEM

### Breinstein

---

## Findings

