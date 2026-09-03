"""Reference FastAPI service for the reusable OGC protocol layer."""

from fastapi import FastAPI
from ogc_processes.router import create_router

from api.reference_backend import (
    ReferenceAuthenticator,
    ReferenceBackend,
    ReferenceCatalog,
    ReferenceJobStore,
)

catalog = ReferenceCatalog()
backend = ReferenceBackend()
store = ReferenceJobStore()

app = FastAPI(title="Roofer Online OGC API - Processes", version="0.1.0")
app.include_router(
    create_router(
        catalog=catalog,
        backend=backend,
        store=store,
        authenticator=ReferenceAuthenticator(),
        prefix="/ogcapi",
    )
)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "roofer-online-processes", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}
