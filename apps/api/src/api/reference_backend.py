"""Deterministic reference services used for local development and tests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ogc_processes.models import (
    InputDescription,
    JobControlOption,
    Link,
    OutputDescription,
    ProcessDescription,
    ProcessSummary,
    Results,
    StatusCode,
    TransmissionMode,
)


@dataclass(frozen=True)
class ReferencePrincipal:
    subject: str


class ReferenceAuthenticator:
    """Accept a bearer token as the demo subject."""

    def authenticate(self, authorization: str | None) -> ReferencePrincipal:
        if authorization is None or not authorization.startswith("Bearer "):
            return ReferencePrincipal(subject="demo")
        token = authorization.removeprefix("Bearer ").strip()
        return ReferencePrincipal(subject=token or "demo")


def _process(process_id: str, title: str, description: str) -> ProcessDescription:
    return ProcessDescription(
        id=process_id,
        title=title,
        description=description,
        version="1.0.0",
        keywords=["roofer", "3d", "buildings"],
        links=[Link(href=f"/ogcapi/processes/{process_id}", rel="self")],
        inputs={
            "inputs": InputDescription(
                title="Process inputs",
                description=description,
                schema={"type": "object"},
                minOccurs=1,
                maxOccurs=1,
            )
        },
        outputs={
            "result": OutputDescription(
                title="Process result",
                schema={"type": "object"},
            )
        },
        jobControlOptions=[
            JobControlOption.execute_async,
            JobControlOption.execute_sync,
        ],
        outputTransmission=[TransmissionMode.value, TransmissionMode.reference],
    )


class ReferenceCatalog:
    def __init__(self) -> None:
        self._processes = [
            _process(
                "roofer:validate_point_cloud:v1",
                "Point Cloud Validation",
                "Validates point-cloud suitability.",
            ),
            _process(
                "roofer:reconstruct_buildings:v1",
                "3D Building Reconstruction",
                "Reconstructs building models from point clouds and BAG polygons.",
            ),
            _process(
                "roofer:convert_format:v1",
                "Format Conversion",
                "Converts CityJSON to publication formats.",
            ),
            _process(
                "roofer:export_to_3dcitydb:v1",
                "Export to 3DCityDB",
                "Exports CityJSON to a 3DCityDB database.",
            ),
        ]

    def list_processes(self) -> list[ProcessSummary]:
        return [
            ProcessSummary.model_validate(process.model_dump())
            for process in self._processes
        ]

    def get_process(self, process_id: str) -> ProcessDescription | None:
        return next(
            (process for process in self._processes if process.id == process_id), None
        )


@dataclass(frozen=True)
class ReferenceSubmission:
    upstream_id: str
    status: StatusCode
    message: str | None


class ReferenceBackend:
    def __init__(self) -> None:
        self._counter = 0
        self._dismissed: set[str] = set()

    def submit(
        self,
        process_id: str,
        inputs: dict[str, Any],
        subject: str,
        mode: JobControlOption,
    ) -> ReferenceSubmission:
        del process_id, inputs, subject
        self._counter += 1
        if mode == JobControlOption.execute_sync:
            return ReferenceSubmission(
                f"reference-{self._counter}",
                StatusCode.successful,
                "Reference execution completed",
            )
        return ReferenceSubmission(
            f"reference-{self._counter}",
            StatusCode.accepted,
            "Reference execution accepted",
        )

    def status(
        self, upstream_id: str, subject: str
    ) -> tuple[StatusCode, str | None, int | None, datetime | None, datetime | None]:
        del subject
        if upstream_id in self._dismissed:
            return (
                StatusCode.dismissed,
                "Reference job dismissed",
                None,
                None,
                datetime.now(UTC),
            )
        return (
            StatusCode.successful,
            "Reference execution completed",
            100,
            datetime.now(UTC),
            datetime.now(UTC),
        )

    def results(self, upstream_id: str, subject: str) -> Results | None:
        del subject
        return Results(
            outputs={"result": {"upstream_id": upstream_id, "status": "successful"}}
        )

    def dismiss(self, upstream_id: str, subject: str) -> bool:
        del subject
        self._dismissed.add(upstream_id)
        return True


class ReferenceJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, tuple[Any, str, str]] = {}

    def create(self, job: Any, upstream_id: str, subject: str) -> None:
        self._jobs[job.jobID] = (job, upstream_id, subject)

    def get(self, job_id: str, subject: str) -> tuple[Any, str] | None:
        record = self._jobs.get(job_id)
        if record is None or record[2] != subject:
            return None
        return record[0], record[1]

    def list(self, subject: str) -> list[tuple[Any, str]]:
        return [
            (job, upstream_id)
            for job, upstream_id, owner in self._jobs.values()
            if owner == subject
        ]

    def update(self, job: Any) -> None:
        record = self._jobs.get(job.jobID)
        if record is not None:
            self._jobs[job.jobID] = (job, record[1], record[2])
