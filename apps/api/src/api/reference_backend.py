"""Deterministic reference services used for local development and tests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ogc_processes.models import (
    InputDescription,
    JobControlOption,
    JobStatus,
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


def _process(
    process_id: str,
    title: str,
    description: str,
    input_name: str,
    input_description: str,
    output_name: str,
    output_description: str,
) -> ProcessDescription:
    return ProcessDescription(
        id=process_id,
        title=title,
        description=description,
        version="1.0.0",
        keywords=["roofer", "3d", "buildings"],
        links=[Link(href=f"/ogcapi/processes/{process_id}", rel="self")],
        inputs={
            input_name: InputDescription(
                title=input_name.replace("_", " ").title(),
                description=input_description,
                schema={"type": "object"},
                minOccurs=1,
                maxOccurs=1,
            )
        },
        outputs={
            output_name: OutputDescription(
                title=output_name.replace("_", " ").title(),
                description=output_description,
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
                "point_cloud",
                "A point-cloud reference to validate.",
                "validation_report",
                "Deterministic point-cloud validation report.",
            ),
            _process(
                "roofer:reconstruct_buildings:v1",
                "3D Building Reconstruction",
                "Reconstructs building models from point clouds and BAG polygons.",
                "reconstruction_request",
                "Point-cloud and building-footprint reconstruction request.",
                "building_model",
                "Deterministic reconstructed building-model reference.",
            ),
            _process(
                "roofer:convert_format:v1",
                "Format Conversion",
                "Converts CityJSON to publication formats.",
                "conversion_request",
                "Source model and target-format conversion request.",
                "converted_model",
                "Deterministic converted model reference.",
            ),
            _process(
                "roofer:export_to_3dcitydb:v1",
                "Export to 3DCityDB",
                "Exports CityJSON to a 3DCityDB database.",
                "export_request",
                "CityJSON export request.",
                "export_receipt",
                "Deterministic 3DCityDB export receipt.",
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
        self._processes: dict[str, str] = {}

    def submit(
        self,
        process_id: str,
        inputs: dict[str, Any],
        subject: str,
        mode: JobControlOption,
    ) -> ReferenceSubmission:
        del inputs, subject
        self._counter += 1
        upstream_id = f"reference-{self._counter}"
        self._processes[upstream_id] = process_id
        if mode == JobControlOption.execute_sync:
            return ReferenceSubmission(
                upstream_id,
                StatusCode.successful,
                "Reference execution completed",
            )
        return ReferenceSubmission(
            upstream_id,
            StatusCode.accepted,
            "Reference execution accepted",
        )

    def status(
        self, upstream_id: str, subject: str
    ) -> tuple[StatusCode, str | None, int | None, datetime | None, datetime | None]:
        del subject
        return (
            StatusCode.successful,
            "Reference execution completed",
            100,
            datetime.now(UTC),
            datetime.now(UTC),
        )

    def results(self, upstream_id: str, subject: str) -> Results | None:
        del subject
        output_id = {
            "roofer:validate_point_cloud:v1": "validation_report",
            "roofer:reconstruct_buildings:v1": "building_model",
            "roofer:convert_format:v1": "converted_model",
            "roofer:export_to_3dcitydb:v1": "export_receipt",
        }.get(self._processes.get(upstream_id, ""))
        if output_id is None:
            return None
        return Results(
            outputs={
                output_id: {
                    "reference": f"urn:roofer:result:{upstream_id}",
                    "status": "successful",
                }
            }
        )

    def output(self, upstream_id: str, output_id: str, subject: str) -> Any | None:
        results = self.results(upstream_id, subject)
        if results is None:
            return None
        return results.outputs.get(output_id)


class ReferenceJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, tuple[JobStatus, str, str]] = {}

    def create(self, job: JobStatus, upstream_id: str, subject: str) -> None:
        self._jobs[job.id] = (job, upstream_id, subject)

    def get(self, job_id: str, subject: str) -> tuple[JobStatus, str] | None:
        record = self._jobs.get(job_id)
        if record is None or record[2] != subject:
            return None
        return record[0], record[1]

    def list(self, subject: str) -> list[tuple[JobStatus, str]]:
        return [
            (job, upstream_id)
            for job, upstream_id, owner in self._jobs.values()
            if owner == subject
        ]

    def update(self, job: JobStatus) -> None:
        record = self._jobs.get(job.id)
        if record is not None:
            self._jobs[job.id] = (job, record[1], record[2])
