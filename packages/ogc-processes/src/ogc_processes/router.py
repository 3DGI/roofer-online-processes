"""Mountable OGC API - Processes Part 1 version 2 application."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ogc_processes.interfaces import (
    Authenticator,
    ExecutionBackend,
    JobStore,
    ProcessCatalog,
)
from ogc_processes.models import (
    Conformance,
    ExceptionReport,
    ExecuteRequest,
    JobControlOption,
    JobList,
    JobStatus,
    LandingPage,
    Link,
    ProcessDescription,
    ProcessList,
    Results,
    StatusCode,
)

CONFORMANCE_CORE = "http://www.opengis.net/spec/ogcapi-processes-1/2.0/conf/core"
CONFORMANCE_JSON = "http://www.opengis.net/spec/ogcapi-processes-1/2.0/conf/json"
CONFORMANCE_PROCESS_DESCRIPTION = (
    "http://www.opengis.net/spec/ogcapi-processes-1/2.0/conf/ogc-process-description"
)
CONFORMANCE_JOB_LIST = (
    "http://www.opengis.net/spec/ogcapi-processes-1/2.0/conf/job-list"
)
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ExceptionReport},
    404: {"model": ExceptionReport},
    500: {"model": ExceptionReport},
}


def create_app(
    *,
    catalog: ProcessCatalog,
    backend: ExecutionBackend,
    store: JobStore,
    authenticator: Authenticator,
) -> FastAPI:
    """Create the OGC sub-application with host dependencies injected."""
    app = FastAPI(
        title="Roofer Online OGC API - Processes",
        version="2.0.0",
        docs_url=None,
        redoc_url=None,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = (
            exc.detail
            if isinstance(exc.detail, str)
            else "Request could not be completed."
        )
        return problem_response(request, exc.status_code, detail)

    @app.exception_handler(RequestValidationError)
    async def validation_problem(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del exc
        return problem_response(request, 400, "Request validation failed.")

    def root_url(request: Request) -> str:
        return (
            f"{str(request.base_url).rstrip('/')}{request.scope.get('root_path', '')}"
        )

    def subject(request: Request) -> str:
        return authenticator.authenticate(request.headers.get("authorization")).subject

    def job_links(request: Request, job_id: str) -> list[Link]:
        root = root_url(request)
        return [
            Link(href=f"{root}/jobs/{job_id}", rel="self", type="application/json"),
            Link(
                href=f"{root}/jobs/{job_id}/results",
                rel="results",
                type="application/json",
            ),
        ]

    def refreshed_job(request: Request, job_id: str, owner: str) -> JobStatus:
        stored = store.get(job_id, owner)
        if stored is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        job, upstream_id = stored
        job.status, job.message, job.progress, job.started, job.finished = (
            backend.status(upstream_id, owner)
        )
        job.updated = datetime.now(UTC)
        store.update(job)
        return job

    def completed_job(request: Request, job_id: str, owner: str) -> JobStatus:
        job = refreshed_job(request, job_id, owner)
        if job.status == StatusCode.failed:
            raise HTTPException(status_code=500, detail="Job processing failed.")
        if job.status != StatusCode.successful:
            raise HTTPException(status_code=404, detail="Results are not available.")
        return job

    @app.get("/", response_model=LandingPage, responses=PROBLEM_RESPONSES)
    def landing(request: Request) -> LandingPage:
        root = root_url(request)
        return LandingPage(
            title="Roofer Online OGC API - Processes",
            description="OGC API - Processes interface for Roofer Online workflows.",
            links=[
                Link(href=f"{root}/", rel="self", type="application/json"),
                Link(
                    href=f"{root}/openapi.json",
                    rel="service-desc",
                    type="application/vnd.oai.openapi+json;version=3.1",
                ),
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

    @app.get("/conformance", response_model=Conformance)
    def conformance() -> Conformance:
        return Conformance(
            conformsTo=[
                CONFORMANCE_CORE,
                CONFORMANCE_JSON,
                CONFORMANCE_PROCESS_DESCRIPTION,
                CONFORMANCE_JOB_LIST,
            ]
        )

    @app.get("/processes", response_model=ProcessList, responses=PROBLEM_RESPONSES)
    def list_processes(request: Request) -> ProcessList:
        root = root_url(request)
        return ProcessList(
            processes=catalog.list_processes(),
            links=[Link(href=f"{root}/processes", rel="self", type="application/json")],
        )

    @app.get(
        "/processes/{process_id}",
        response_model=ProcessDescription,
        responses=PROBLEM_RESPONSES,
    )
    def get_process(process_id: str) -> ProcessDescription:
        process = catalog.get_process(process_id)
        if process is None:
            raise HTTPException(status_code=404, detail="Process not found.")
        return process

    @app.post(
        "/processes/{process_id}/execution",
        response_model=None,
        responses={
            200: {"model": Results},
            201: {"model": JobStatus},
            **PROBLEM_RESPONSES,
        },
    )
    def execute(
        request: Request, process_id: str, payload: ExecuteRequest
    ) -> JSONResponse | Results:
        process = catalog.get_process(process_id)
        if process is None:
            raise HTTPException(status_code=404, detail="Process not found.")
        mode = execution_mode(request.headers.get("prefer"))
        if mode not in process.jobControlOptions:
            raise HTTPException(
                status_code=400, detail="Requested execution mode is unavailable."
            )
        owner = subject(request)
        submission = backend.submit(process_id, payload.inputs, owner, mode)
        now = datetime.now(UTC)
        job_id = str(uuid4())
        job = JobStatus(
            id=job_id,
            processID=process_id,
            status=submission.status,
            message=submission.message,
            created=now,
            finished=now
            if submission.status in {StatusCode.successful, StatusCode.failed}
            else None,
            updated=now,
            progress=100 if submission.status == StatusCode.successful else 0,
            links=job_links(request, job_id),
        )
        store.create(job, submission.upstream_id, owner)
        if mode == JobControlOption.execute_sync:
            results = backend.results(submission.upstream_id, owner)
            if results is None:
                raise HTTPException(
                    status_code=500, detail="Execution returned no results."
                )
            return results
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            headers={
                "Location": f"{root_url(request)}/jobs/{job_id}",
                "Preference-Applied": "respond-async",
            },
            content=job.model_dump(mode="json"),
        )

    @app.get("/jobs", response_model=JobList, responses=PROBLEM_RESPONSES)
    def list_jobs(
        request: Request,
        type: str | None = None,
        processID: str | None = None,
        status: StatusCode | None = None,
        datetime_: str | None = Query(default=None, alias="datetime"),
        minDuration: float | None = Query(default=None, ge=0),
        maxDuration: float | None = Query(default=None, ge=0),
        limit: int = Query(default=10, ge=1, le=1000),
    ) -> JobList:
        if type is not None and type != "ogc-api-processes":
            raise HTTPException(
                status_code=400, detail="Unsupported processing entity type."
            )
        if (
            minDuration is not None
            and maxDuration is not None
            and minDuration > maxDuration
        ):
            raise HTTPException(
                status_code=400, detail="minDuration must not exceed maxDuration."
            )
        owner = subject(request)
        jobs = [refreshed_job(request, job.id, owner) for job, _ in store.list(owner)]
        jobs = filter_jobs(jobs, processID, status, datetime_, minDuration, maxDuration)
        return JobList(
            jobs=jobs[:limit],
            links=[
                Link(
                    href=f"{root_url(request)}/jobs",
                    rel="self",
                    type="application/json",
                )
            ],
        )

    @app.get("/jobs/{job_id}", response_model=JobStatus, responses=PROBLEM_RESPONSES)
    def get_job(request: Request, job_id: str) -> JobStatus:
        return refreshed_job(request, job_id, subject(request))

    @app.get(
        "/jobs/{job_id}/results", response_model=Results, responses=PROBLEM_RESPONSES
    )
    def get_results(
        request: Request, job_id: str, outputs: str | None = None
    ) -> Results:
        owner = subject(request)
        job = completed_job(request, job_id, owner)
        stored = store.get(job.id, owner)
        if stored is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        results = backend.results(stored[1], owner)
        if results is None:
            raise HTTPException(status_code=404, detail="Results are not available.")
        selected = select_outputs(results, outputs)
        selected.links = [
            Link(
                href=f"{root_url(request)}/jobs/{job.id}/results/{output_id}",
                rel="item",
                type="application/json",
                title=output_id,
            )
            for output_id in selected.outputs
        ]
        return selected

    @app.get(
        "/jobs/{job_id}/results/{output_id}",
        response_model=None,
        responses=PROBLEM_RESPONSES,
    )
    @app.get(
        "/jobs/{job_id}/results/{output_id}/0",
        response_model=None,
        responses=PROBLEM_RESPONSES,
    )
    def get_output(request: Request, job_id: str, output_id: str) -> Any:
        owner = subject(request)
        job = completed_job(request, job_id, owner)
        stored = store.get(job.id, owner)
        if stored is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        output = backend.output(stored[1], output_id, owner)
        if output is None:
            raise HTTPException(status_code=404, detail="Output is not available.")
        return output

    return app


def problem_response(request: Request, status_code: int, detail: str) -> JSONResponse:
    """Return an RFC 7807 response for protocol and validation errors."""
    title = {400: "Bad Request", 404: "Not Found", 500: "Internal Server Error"}.get(
        status_code, "Error"
    )
    report = ExceptionReport(
        title=title, status=status_code, detail=detail, instance=str(request.url)
    )
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content=report.model_dump(),
    )


def execution_mode(prefer: str | None) -> JobControlOption:
    """Negotiate execution mode from the RFC 7240 Prefer header."""
    if prefer is not None and "respond-sync" in prefer:
        return JobControlOption.execute_sync
    return JobControlOption.execute_async


def select_outputs(results: Results, requested: str | None) -> Results:
    """Validate and select comma-separated output identifiers."""
    if requested is None:
        return Results(outputs=results.outputs.copy())
    output_ids = [output_id for output_id in requested.split(",") if output_id]
    if not output_ids or any(
        output_id not in results.outputs for output_id in output_ids
    ):
        raise HTTPException(
            status_code=400, detail="Requested output is not available."
        )
    return Results(
        outputs={output_id: results.outputs[output_id] for output_id in output_ids}
    )


def filter_jobs(
    jobs: list[JobStatus],
    process_id: str | None,
    job_status: StatusCode | None,
    datetime_filter: str | None,
    minimum: float | None,
    maximum: float | None,
) -> list[JobStatus]:
    """Apply the Job List filters supported by the reference store."""
    filtered = [
        job for job in jobs if process_id is None or job.processID == process_id
    ]
    filtered = [
        job for job in filtered if job_status is None or job.status == job_status
    ]
    if datetime_filter is not None:
        filtered = [job for job in filtered if datetime_matches(job, datetime_filter)]
    if minimum is not None or maximum is not None:
        filtered = [job for job in filtered if duration_matches(job, minimum, maximum)]
    return filtered


def datetime_matches(job: JobStatus, value: str) -> bool:
    """Match an ISO 8601 instant or interval against job creation time."""
    if "/" in value:
        start_text, end_text = value.split("/", maxsplit=1)
        start = parse_datetime(start_text) if start_text != ".." else None
        end = parse_datetime(end_text) if end_text != ".." else None
        return (start is None or job.created >= start) and (
            end is None or job.created <= end
        )
    instant = parse_datetime(value)
    return instant is not None and job.created == instant


def parse_datetime(value: str) -> datetime | None:
    """Parse ISO 8601 without using exception flow outside this boundary."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_matches(
    job: JobStatus, minimum: float | None, maximum: float | None
) -> bool:
    """Match elapsed job duration bounds in seconds."""
    if job.started is None or job.finished is None:
        return False
    elapsed = (job.finished - job.started).total_seconds()
    return (minimum is None or elapsed >= minimum) and (
        maximum is None or elapsed <= maximum
    )
