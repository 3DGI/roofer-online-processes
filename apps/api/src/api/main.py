"""Reference FastAPI service for the reusable OGC protocol layer."""

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from ogc_processes.router import create_app

from api.process_contracts import RooferContractValidator
from api.reference_backend import (
    ReferenceAuthenticator,
    ReferenceBackend,
    ReferenceCatalog,
    ReferenceJobStore,
)

catalog = ReferenceCatalog()
backend = ReferenceBackend(
    artifact_base_url=os.getenv(
        "ROOFER_PROCESSES_PUBLIC_BASE_URL", "http://localhost:8000"
    )
)
store = ReferenceJobStore()

app = FastAPI(title="Roofer Online Processes", version="0.1.0")
app.mount(
    "/ogcapi",
    create_app(
        validator=RooferContractValidator(),
        catalog=catalog,
        backend=backend,
        store=store,
        authenticator=ReferenceAuthenticator(),
    ),
)


@app.get("/")
def root() -> dict[str, object]:
    return {
        "service": "roofer-online-processes",
        "docs": "/docs",
        "links": [{"rel": "ogcapi", "href": "/ogcapi/"}],
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/v1/reconstruction/{model_3d_id}/export/{format}")
def artifact(request: Request, model_3d_id: int, format: str) -> Response:
    owner = (
        ReferenceAuthenticator()
        .authenticate(request.headers.get("authorization"))
        .subject
    )
    content = backend.artifact(model_3d_id, format, owner)
    if content is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return Response(content=content, media_type="application/zip")
