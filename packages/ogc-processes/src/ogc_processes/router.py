"""Mountable OGC API - Processes Part 1 version 2 application."""

import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Body, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from ogc_processes.interfaces import (
    Authenticator,
    ContractViolation,
    ExecutionBackend,
    JobStore,
    ProcessCatalog,
    ProcessContractValidator,
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

CONFORMANCE_CORE = (
    "http://www.opengis.net/spec/ogcapi-processes-1/2.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core",
)
CONFORMANCE_JSON = (
    "http://www.opengis.net/spec/ogcapi-processes-1/2.0/conf/json",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/json",
)
CONFORMANCE_PROCESS_DESCRIPTION = (
    "http://www.opengis.net/spec/ogcapi-processes-1/2.0/conf/ogc-process-description",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/ogc-process-description",
)
CONFORMANCE_JOB_LIST = (
    "http://www.opengis.net/spec/ogcapi-processes-1/2.0/conf/job-list",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/job-list",
)
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ExceptionReport, "content": {"application/json": {}}},
    404: {"model": ExceptionReport, "content": {"application/json": {}}},
    500: {"model": ExceptionReport, "content": {"application/json": {}}},
}
REL_CONFORMANCE = "http://www.opengis.net/def/rel/ogc/1.0/conformance"
REL_PROCESSES = "http://www.opengis.net/def/rel/ogc/1.0/processes"
REL_RESULTS = "http://www.opengis.net/def/rel/ogc/1.0/results"


def root_url(request: Request) -> str:
    """Build the public mount URL from the external prefix and mounted path."""
    root_path = request.scope.get("root_path", "").rstrip("/")
    app_root_path = request.scope.get("app_root_path", "").rstrip("/")
    mount_path = root_path
    if app_root_path and root_path.startswith(app_root_path):
        mount_path = root_path[len(app_root_path) :]
    return f"{str(request.base_url).rstrip('/')}{mount_path}"


def _normalize_openapi_30(node: Any) -> None:
    """Rewrite Pydantic's OpenAPI 3.1 constructs for OpenAPI 3.0 clients."""
    if isinstance(node, dict):
        if "const" in node:
            node["enum"] = [node.pop("const")]
        any_of = node.get("anyOf")
        if isinstance(any_of, list) and len(any_of) == 2:
            nullable = next(
                (item for item in any_of if isinstance(item, dict) and item.get("type") == "null"),
                None,
            )
            non_null = next(
                (item for item in any_of if isinstance(item, dict) and item.get("type") != "null"),
                None,
            )
            if nullable is not None and non_null is not None:
                outer = {key: value for key, value in node.items() if key != "anyOf"}
                node.clear()
                node.update(non_null)
                node.update(outer)
                node["nullable"] = True
        for value in node.values():
            _normalize_openapi_30(value)
    elif isinstance(node, list):
        for value in node:
            _normalize_openapi_30(value)


def create_app(
    *,
    catalog: ProcessCatalog,
    backend: ExecutionBackend,
    store: JobStore,
    authenticator: Authenticator,
    validator: ProcessContractValidator,
) -> FastAPI:
    """Create the OGC sub-application with host dependencies injected."""
    app = FastAPI(
        title="Roofer Online OGC API - Processes",
        version="2.0.0",
        docs_url=None,
        redoc_url=None,
    )
    app.openapi_version = "3.0.3"
    native_openapi = app.openapi

    def openapi_30() -> dict[str, Any]:
        schema = native_openapi()
        _normalize_openapi_30(schema)
        execution = schema.get("paths", {}).get("/processes/{process_id}/execution", {}).get("post")
        if isinstance(execution, dict):
            execution["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "process": {"type": "string", "format": "uri"},
                                "inputs": {"type": "object", "additionalProperties": {}},
                                "outputs": {
                                    "type": "object",
                                    "additionalProperties": {
                                        "type": "object",
                                        "properties": {
                                            "transmissionMode": {
                                                "type": "string",
                                                "enum": ["value", "reference"],
                                            },
                                            "format": {"type": "object"},
                                            "mediaType": {"type": "string"},
                                        },
                                    },
                                },
                                "response": {
                                    "type": "string",
                                    "enum": ["raw", "document"],
                                    "default": "raw",
                                },
                                "subscriber": {"type": "object"},
                            },
                        }
                    }
                },
            }
        for path_item in schema.get("paths", {}).values():
            if not isinstance(path_item, dict):
                continue
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                for parameter in operation.get("parameters", []):
                    if not isinstance(parameter, dict):
                        continue
                    if parameter.get("name") != "outputs":
                        continue
                    parameter_schema = parameter.get("schema")
                    if not isinstance(parameter_schema, dict):
                        continue
                    for key in ("style", "explode"):
                        if key in parameter_schema:
                            parameter[key] = parameter_schema.pop(key)
                    parameter_schema.pop("nullable", None)
        return schema

    app.openapi = openapi_30  # type: ignore[method-assign]

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request could not be completed."
        return problem_response(request, exc.status_code, detail)

    @app.exception_handler(RequestValidationError)
    async def validation_problem(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        return problem_response(request, 400, "Request validation failed.")

    @app.exception_handler(ContractViolation)
    async def contract_problem(request: Request, exc: ContractViolation) -> JSONResponse:
        del exc
        return problem_response(request, 400, "Process input validation failed.")

    def validated_results(process_id: str, upstream_id: str, owner: str) -> Results:
        results = backend.results(upstream_id, owner)
        if results is None:
            raise HTTPException(status_code=500, detail="Execution returned no results.")
        try:
            return validator.validate_results(process_id, results)
        except ContractViolation as exc:
            raise HTTPException(status_code=500, detail="Invalid backend results.") from exc

    def subject(request: Request) -> str:
        return authenticator.authenticate(request.headers.get("authorization")).subject

    def job_links(request: Request, job_id: str) -> list[Link]:
        root = root_url(request)
        return [
            Link(href=f"{root}/jobs/{job_id}", rel="self", type="application/json"),
            Link(
                href=f"{root}/jobs/{job_id}/results",
                rel=REL_RESULTS,
                type="application/json",
            ),
        ]

    def refreshed_job(request: Request, job_id: str, owner: str) -> JobStatus:
        stored = store.get(job_id, owner)
        if stored is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        job, upstream_id = stored
        job.status, job.message, job.progress, job.started, job.finished = backend.status(upstream_id, owner)
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

    @app.get(
        "/",
        response_model=LandingPage,
        response_model_exclude_none=True,
        responses=PROBLEM_RESPONSES,
    )
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
                    type="application/vnd.oai.openapi+json;version=3.0",
                ),
                Link(
                    href=f"{root}/conformance",
                    rel=REL_CONFORMANCE,
                    type="application/json",
                ),
                Link(
                    href=f"{root}/processes",
                    rel=REL_PROCESSES,
                    type="application/json",
                ),
                Link(href=f"{root}/jobs", rel="jobs", type="application/json"),
            ],
        )

    @app.get("/conformance", response_model=Conformance)
    def conformance() -> Conformance:
        return Conformance(
            conformsTo=[
                *CONFORMANCE_CORE,
                *CONFORMANCE_JSON,
                *CONFORMANCE_PROCESS_DESCRIPTION,
                *CONFORMANCE_JOB_LIST,
            ]
        )

    @app.get(
        "/processes",
        response_model=ProcessList,
        response_model_exclude_none=True,
        responses=PROBLEM_RESPONSES,
    )
    def list_processes(request: Request, limit: Annotated[int, Query(ge=1, le=1000)] = 10) -> ProcessList:
        root = root_url(request)
        return ProcessList(
            processes=catalog.list_processes()[:limit],
            links=[Link(href=f"{root}/processes", rel="self", type="application/json")],
        )

    @app.get(
        "/processes/{process_id}",
        response_model=ProcessDescription,
        response_model_exclude_none=True,
        responses=PROBLEM_RESPONSES,
    )
    def get_process(request: Request, process_id: str) -> ProcessDescription:
        process = catalog.get_process(process_id)
        if process is None:
            raise HTTPException(status_code=404, detail="Process not found.")
        root = root_url(request)
        href = f"{root}/processes/{process_id}"
        process.links = [
            Link(href=href, rel="self", type="application/json"),
            Link(href=f"{root}/processes", rel="alternate", type="application/json"),
            Link(
                href="https://www.opengis.net/def/profile/OGC/0/ogc-process-description",
                rel="profile",
                type="application/json",
            ),
        ]
        return process

    @app.post(
        "/processes/{process_id}/execution",
        response_model=None,
        responses={
            200: {
                "description": "Synchronous result in the requested raw or document form.",
                "content": {
                    "application/json": {"schema": {"type": "object", "additionalProperties": True}},
                    "text/plain": {"schema": {"type": "string"}},
                    "multipart/related": {"schema": {"type": "string", "format": "binary"}},
                },
            },
            201: {"model": JobStatus},
            **PROBLEM_RESPONSES,
        },
    )
    def execute(
        request: Request,
        process_id: str,
        payload: Annotated[ExecuteRequest, Body(default_factory=ExecuteRequest)],
    ) -> Response | dict[str, Any]:
        process = catalog.get_process(process_id)
        if process is None:
            raise HTTPException(status_code=404, detail="Process not found.")
        mode = execution_mode(request.headers.get("prefer"))
        if mode not in process.jobControlOptions:
            raise HTTPException(status_code=400, detail="Requested execution mode is unavailable.")
        if payload.outputs is not None:
            if not payload.outputs or any(name not in process.outputs for name in payload.outputs):
                raise HTTPException(status_code=400, detail="Requested output is not available.")
            if any(option.transmissionMode not in process.outputTransmission for option in payload.outputs.values()):
                raise HTTPException(status_code=400, detail="Requested output transmission is unavailable.")
        owner = subject(request)
        inputs = validator.validate_inputs(process_id, payload.inputs)
        submission = backend.submit(process_id, inputs, owner, mode)
        now = datetime.now(UTC)
        job_id = str(uuid4())
        job = JobStatus(
            id=job_id,
            jobID=job_id,
            processID=process_id,
            processingEntityType="ogc-api-processes",
            status=submission.status,
            message=submission.message,
            created=now,
            finished=now if submission.status in {StatusCode.successful, StatusCode.failed} else None,
            updated=now,
            progress=100 if submission.status == StatusCode.successful else 0,
            links=job_links(request, job_id),
        )
        store.create(job, submission.upstream_id, owner)
        if mode == JobControlOption.execute_sync:
            results = validated_results(process_id, submission.upstream_id, owner)
            results = select_outputs(results, list(payload.outputs) if payload.outputs is not None else None)
            if payload.response == "raw":
                if len(results.outputs) == 1:
                    value = next(iter(results.outputs.values()))
                    return PlainTextResponse(value) if isinstance(value, str) else JSONResponse(content=value)
                return multipart_results(results)
            return result_document(results)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            headers={
                "Location": f"{root_url(request)}/jobs/{job_id}",
                "Preference-Applied": "respond-async",
            },
            content=job.model_dump(mode="json", exclude_none=True),
        )

    @app.get(
        "/jobs",
        response_model=JobList,
        response_model_exclude_none=True,
        responses=PROBLEM_RESPONSES,
    )
    def list_jobs(
        request: Request,
        type: Annotated[list[str] | None, Query()] = None,
        processID: Annotated[list[str] | None, Query()] = None,
        status: Annotated[list[StatusCode] | None, Query()] = None,
        datetime_: Annotated[str | None, Query(alias="datetime")] = None,
        minDuration: Annotated[int | None, Query(ge=0)] = None,
        maxDuration: Annotated[int | None, Query(ge=0)] = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 10,
    ) -> JobList:
        if type is not None and any(item not in {"process", "ogc-api-processes"} for item in type):
            raise HTTPException(status_code=400, detail="Unsupported processing entity type.")
        if minDuration is not None and maxDuration is not None and minDuration > maxDuration:
            raise HTTPException(status_code=400, detail="minDuration must not exceed maxDuration.")
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

    @app.get(
        "/jobs/{job_id}",
        response_model=JobStatus,
        response_model_exclude_none=True,
        responses=PROBLEM_RESPONSES,
    )
    def get_job(request: Request, job_id: str) -> JobStatus:
        return refreshed_job(request, job_id, subject(request))

    @app.get(
        "/jobs/{job_id}/results",
        response_model=dict[str, Any],
        response_model_exclude_none=True,
        responses=PROBLEM_RESPONSES,
    )
    def get_results(
        request: Request,
        job_id: str,
        outputs: Annotated[list[str] | None, Query(style="form", explode=False)] = None,
    ) -> JSONResponse:
        owner = subject(request)
        job = completed_job(request, job_id, owner)
        stored = store.get(job.id, owner)
        if stored is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        results = validated_results(job.processID, stored[1], owner)
        selected = select_outputs(results, outputs)
        links = [
            f'<{root_url(request)}/jobs/{job.id}/results/{output_id}>; rel="item"; type="application/json"'
            for output_id in selected.outputs
        ]
        return JSONResponse(content=result_document(selected), headers={"Link": ", ".join(links)})

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
        output = validated_results(job.processID, stored[1], owner).outputs.get(output_id)
        if output is None:
            raise HTTPException(status_code=404, detail="Output is not available.")
        return output

    return app


def multipart_results(results: Results) -> Response:
    """Transmit multiple raw outputs in their native media types."""
    boundary = uuid4().hex
    parts = [
        f"--{boundary}\r\nContent-Type: {'text/plain; charset=utf-8' if isinstance(value, str) else 'application/json'}"
        f"\r\nContent-ID: <{name}>\r\n\r\n"
        f"{value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}\r\n"
        for name, value in results.outputs.items()
    ]
    return Response(
        content="".join(parts) + f"--{boundary}--\r\n",
        media_type=f'multipart/related; boundary="{boundary}"',
    )


def result_document(results: Results) -> dict[str, Any]:
    """Encode output IDs at the document root and qualify object values."""
    return {name: {"value": value} if isinstance(value, dict) else value for name, value in results.outputs.items()}


def problem_response(request: Request, status_code: int, detail: str) -> JSONResponse:
    """Return an OGC API 1.0 exception response."""
    base_type = "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0"
    if detail == "Results are not available.":
        exception_type = f"{base_type}/result-not-ready"
    elif status_code == 404 and "/processes/" in request.url.path:
        exception_type = f"{base_type}/no-such-process"
    elif status_code == 404 and "/jobs/" in request.url.path:
        exception_type = f"{base_type}/no-such-job"
    else:
        exception_type = "about:blank"
    report = ExceptionReport(
        type=exception_type,
        title={
            400: "Bad Request",
            404: "Not Found",
            500: "Internal Server Error",
        }.get(status_code, "Error"),
        status=status_code,
        detail=detail,
        code={400: "BadRequest", 404: "NotFound", 500: "InternalServerError"}.get(status_code, "Error"),
        description=detail,
    )
    return JSONResponse(
        status_code=status_code,
        media_type="application/json",
        content=report.model_dump(exclude_none=True),
    )


def execution_mode(prefer: str | None) -> JobControlOption:
    """Negotiate execution mode from the RFC 7240 Prefer header."""
    directives = {directive.strip().split("=", 1)[0] for directive in (prefer or "").split(",")}
    if "respond-async" in directives:
        return JobControlOption.execute_async
    return JobControlOption.execute_sync


def select_outputs(results: Results, requested: list[str] | None) -> Results:
    """Validate and select comma-separated output identifiers."""
    if requested is None:
        return Results(outputs=results.outputs.copy())
    output_ids = [output_id for value in requested for output_id in value.split(",") if output_id]
    if not output_ids or any(output_id not in results.outputs for output_id in output_ids):
        raise HTTPException(status_code=400, detail="Requested output is not available.")
    return Results(outputs={output_id: results.outputs[output_id] for output_id in output_ids})


def filter_jobs(
    jobs: list[JobStatus],
    process_id: list[str] | None,
    job_status: list[StatusCode] | None,
    datetime_filter: str | None,
    minimum: int | None,
    maximum: int | None,
) -> list[JobStatus]:
    """Apply the Job List filters supported by the reference store."""
    filtered = [job for job in jobs if process_id is None or job.processID in process_id]
    filtered = [job for job in filtered if job_status is None or job.status in job_status]
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
        return (start is None or job.created >= start) and (end is None or job.created <= end)
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


def duration_matches(job: JobStatus, minimum: int | None, maximum: int | None) -> bool:
    """Match elapsed job duration bounds in seconds."""
    if job.started is None or job.finished is None:
        return False
    elapsed = (job.finished - job.started).total_seconds()
    return (minimum is None or elapsed >= minimum) and (maximum is None or elapsed <= maximum)
