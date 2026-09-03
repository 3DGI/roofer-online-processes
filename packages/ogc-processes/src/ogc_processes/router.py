"""FastAPI router for OGC API - Processes Core."""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from .interfaces import Authenticator, ExecutionBackend, JobStore, ProcessCatalog
from .models import (
    Conformance,
    ExecuteRequest,
    JobList,
    JobStatus,
    LandingPage,
    Link,
    ProcessDescription,
    ProcessList,
    Results,
    StatusCode,
)

CONFORMANCE_CORE = "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core"
CONFORMANCE_JSON = "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/json"


def create_router(
    *,
    catalog: ProcessCatalog,
    backend: ExecutionBackend,
    store: JobStore,
    authenticator: Authenticator,
    prefix: str,
) -> APIRouter:
    """Create an OGC router with all host dependencies injected."""
    router = APIRouter(prefix=prefix, tags=["OGC Processes"])

    def base_url(request: Request) -> str:
        return str(request.base_url).rstrip("/") + prefix

    def principal(request: Request) -> str:
        return authenticator.authenticate(request.headers.get("authorization")).subject

    def job_links(request: Request, job_id: str) -> list[Link]:
        root = base_url(request)
        return [
            Link(href=f"{root}/jobs/{job_id}", rel="self", type="application/json"),
            Link(
                href=f"{root}/jobs/{job_id}/results",
                rel="results",
                type="application/json",
            ),
        ]

    @router.get("", response_model=LandingPage)
    def landing(request: Request) -> LandingPage:
        root = base_url(request)
        return LandingPage(
            title="Roofer Online OGC API - Processes",
            description="OGC API - Processes interface for Roofer Online workflows.",
            links=[
                Link(href=root, rel="self", type="application/json"),
                Link(
                    href=f"{root}/conformance",
                    rel="conformance",
                    type="application/json",
                ),
                Link(
                    href=f"{root}/processes", rel="processes", type="application/json"
                ),
                Link(href=f"{root}/jobs", rel="jobs", type="application/json"),
            ],
        )

    @router.get("/conformance", response_model=Conformance)
    def conformance() -> Conformance:
        return Conformance(conformsTo=[CONFORMANCE_CORE, CONFORMANCE_JSON])

    @router.get("/processes", response_model=ProcessList)
    def list_processes(request: Request) -> ProcessList:
        root = base_url(request)
        processes = catalog.list_processes()
        return ProcessList(
            processes=processes,
            links=[Link(href=f"{root}/processes", rel="self", type="application/json")],
        )

    @router.get("/processes/{process_id}", response_model=ProcessDescription)
    def get_process(process_id: str) -> ProcessDescription:
        process = catalog.get_process(process_id)
        if process is None:
            raise HTTPException(status_code=404, detail="Process not found")
        return process

    @router.post("/processes/{process_id}/execution", response_model=None)
    def execute(
        request: Request,
        process_id: str,
        payload: ExecuteRequest,
    ) -> JSONResponse | Results:
        process = catalog.get_process(process_id)
        if process is None:
            raise HTTPException(status_code=404, detail="Process not found")
        subject = principal(request)
        selected_mode = payload.mode
        if selected_mode is None:
            selected_mode = process.jobControlOptions[0]
        submission = backend.submit(process_id, payload.inputs, subject, selected_mode)
        now = datetime.now(UTC)
        job_id = str(uuid4())
        job = JobStatus(
            jobID=job_id,
            processID=process_id,
            status=submission.status,
            message=submission.message,
            created=now,
            started=now if submission.status == StatusCode.running else None,
            finished=now if submission.status == StatusCode.successful else None,
            updated=now,
            progress=100 if submission.status == StatusCode.successful else 0,
            links=job_links(request, job_id),
        )
        store.create(job, submission.upstream_id, subject)
        if (
            selected_mode.value == "execute-sync"
            and submission.status == StatusCode.successful
        ):
            results = backend.results(submission.upstream_id, subject)
            if results is None:
                raise HTTPException(
                    status_code=500, detail="Execution returned no results"
                )
            return results
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            headers={"Location": f"{base_url(request)}/jobs/{job_id}"},
            content=job.model_dump(mode="json"),
        )

    def refreshed_job(request: Request, job_id: str, subject: str) -> JobStatus:
        stored = store.get(job_id, subject)
        if stored is None:
            raise HTTPException(status_code=404, detail="Job not found")
        job, upstream_id = stored
        current_status, message, progress, started, finished = backend.status(
            upstream_id, subject
        )
        job.status = current_status
        job.message = message
        job.progress = progress
        job.started = started
        job.finished = finished
        job.updated = datetime.now(UTC)
        store.update(job)
        return job

    @router.get("/jobs", response_model=JobList)
    def list_jobs(request: Request) -> JobList:
        subject = principal(request)
        jobs = [
            refreshed_job(request, job.jobID, subject) for job, _ in store.list(subject)
        ]
        return JobList(
            jobs=jobs, links=[Link(href=f"{base_url(request)}/jobs", rel="self")]
        )

    @router.get("/jobs/{job_id}", response_model=JobStatus)
    def get_job(request: Request, job_id: str) -> JobStatus:
        return refreshed_job(request, job_id, principal(request))

    @router.delete("/jobs/{job_id}", response_model=JobStatus)
    def dismiss_job(request: Request, job_id: str) -> JobStatus:
        subject = principal(request)
        stored = store.get(job_id, subject)
        if stored is None:
            raise HTTPException(status_code=404, detail="Job not found")
        job, upstream_id = stored
        if not backend.dismiss(upstream_id, subject):
            raise HTTPException(status_code=409, detail="Job could not be dismissed")
        job.status = StatusCode.dismissed
        job.updated = datetime.now(UTC)
        store.update(job)
        return job

    @router.get("/jobs/{job_id}/results", response_model=Results)
    def get_results(request: Request, job_id: str) -> Results:
        subject = principal(request)
        job = refreshed_job(request, job_id, subject)
        if job.status != StatusCode.successful:
            raise HTTPException(
                status_code=400, detail="Job has not completed successfully"
            )
        stored = store.get(job_id, subject)
        if stored is None:
            raise HTTPException(status_code=404, detail="Job not found")
        results = backend.results(stored[1], subject)
        if results is None:
            raise HTTPException(status_code=404, detail="Results not found")
        return results

    return router
