# Roofer Online integration contract

The host adapter must provide:

- process submission for point-cloud validation, reconstruction, format conversion, and 3DCityDB export;
- status mapping from Roofer/Dagster states to OGC `accepted`, `running`, `successful`, `failed`, and `dismissed`;
- result references for generated CityJSON, OBJ, GeoPackage, 3D Tiles, and CityDB export outcomes;
- authentication using Roofer Online’s existing user system;
- ownership checks for every process and job operation;
- durable mapping between OGC job IDs and Roofer process/Dagster identifiers.

The first production deployment should mount the reusable router in the Roofer Online API. A
standalone HTTP gateway may be added later if the same contract can be exposed without duplicating
security or workflow state.

