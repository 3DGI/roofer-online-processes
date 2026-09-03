# Proof-of-concept assessment

The proof of concept in `../test-roofer-online-processes` is used as design input only.

Retained ideas:

- a Python workspace managed with `uv`;
- a FastAPI reference app;
- OGC concerns split into landing, conformance, process, and job modules;
- a small local command interface for running checks.

Intentionally not ported:

- the in-memory dummy data store;
- placeholder Dagster pipeline assets;
- POC-specific process identifiers and permissive execution behavior;
- direct coupling between the API and a test pipeline.

The new implementation starts with proposal-defined process identifiers and injected boundaries so
the production adapter can be developed and tested separately from the protocol package.

