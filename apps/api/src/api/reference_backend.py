"""Deterministic reference services used for local development and tests."""

from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from zipfile import ZipFile

from ogc_processes.interfaces import ContractViolation
from ogc_processes.models import (
    InputDescription,
    JobControlOption,
    JobStatus,
    OutputDescription,
    ProcessDescription,
    ProcessSummary,
    Results,
    StatusCode,
    TransmissionMode,
)
from shapely import from_wkt
from shapely.geometry import box

from api.process_contracts import CONTRACTS


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


class ReferenceCatalog:
    def __init__(self) -> None:
        self._processes = []
        for process_id, contract in CONTRACTS.items():
            schema = contract.inputs.model_json_schema(by_alias=True)
            definitions = schema.get("$defs", {})
            self._processes.append(
                ProcessDescription(
                    id=process_id,
                    title=process_id.split(":")[1].replace("_", " ").title(),
                    description="Deterministic reference workflow.",
                    inputsSchema=schema,
                    version="1.0.0",
                    inputs={
                        name: InputDescription(
                            title=name,
                            schema=field | {"$defs": definitions},
                            minOccurs=1 if name in schema.get("required", []) else 0,
                            maxOccurs=1,
                        )
                        for name, field in schema["properties"].items()
                    },
                    outputs={
                        contract.output_name: OutputDescription(
                            title=contract.output_name,
                            schema=contract.output.model_json_schema(),
                        )
                    },
                    jobControlOptions=[
                        JobControlOption.execute_async,
                        JobControlOption.execute_sync,
                    ],
                    outputTransmission=[TransmissionMode.value],
                )
            )

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
    """Registered fixture sources without external downloads or a BAG database.

    Built-in IDs are isolated per subject. Generated assets retain ownership.
    """

    def __init__(
        self, feature_limit: int = 10, artifact_base_url: str = "http://localhost:8000"
    ) -> None:
        self.artifact_base_url = artifact_base_url.rstrip("/")
        self._counter = 0
        self.feature_limit = feature_limit
        self._results: dict[str, tuple[str, Results]] = {}
        self.point_clouds: dict[tuple[str, int], bool] = {}
        self.bags: dict[tuple[str, int], list[str]] = {}
        self.models: dict[tuple[str, int], list[str]] = {}
        self.uploads = {
            "https://roofer.example/api/v1/pointcloud/upload/123": (123, True, None),
            "https://roofer.example/api/v1/pointcloud/upload/125": (125, False, None),
        }
        self.remote_sources = {
            "https://data.example/survey.laz": "ready",
            "https://data.example/invalid.laz": "invalid",
            "https://data.example/failed.laz": "failed",
        }
        self.footprints = {
            "0000000000000001": box(0, 0, 2, 2),
            "0000000000000002": box(4, 0, 6, 2),
            "0000000000000003": box(8, 0, 10, 2),
        }

    def _owned_cloud(self, cloud_id: int, subject: str) -> bool:
        return self.point_clouds.get((subject, cloud_id), cloud_id in {1, 123, 124})

    def _bag_selection(self, selector: dict[str, Any], subject: str) -> list[str]:
        if selector["kind"] == "asset":
            selected = self.bags.get(
                (subject, selector["asset_id"]),
                ["0000000000000001"] if selector["asset_id"] in {2, 456} else [],
            )
        elif selector["kind"] == "buildings":
            selected = selector["building_ids"]
            if any(identifier not in self.footprints for identifier in selected):
                raise ContractViolation("Requested buildings are unavailable.")
        else:
            area = from_wkt(selector["wkt"]).buffer(1)
            selected = [
                identifier
                for identifier, footprint in self.footprints.items()
                if area.contains(footprint)
            ]
        if not selected or len(selected) > self.feature_limit:
            raise ContractViolation(
                "BAG selection is empty or exceeds the feature limit."
            )
        return sorted(selected)

    def submit(
        self,
        process_id: str,
        inputs: dict[str, Any],
        subject: str,
        mode: JobControlOption,
    ) -> ReferenceSubmission:
        operation = process_id.split(":")[1]
        selection = None
        if operation == "validate_point_cloud":
            for source in inputs["point_clouds"]:
                if source["kind"] == "upload":
                    upload = self.uploads.get(source["upload_url"])
                    if (
                        upload is None
                        or not upload[1]
                        or upload[2] not in {None, subject}
                    ):
                        raise ContractViolation("Upload is unavailable or incomplete.")
                if (
                    source["kind"] == "asset"
                    and not self._owned_cloud(source["asset_id"], subject)
                    and (subject, source["asset_id"]) not in self.point_clouds
                ):
                    raise ContractViolation("Point cloud is unavailable.")
        elif operation == "reconstruct_buildings":
            if not all(
                self._owned_cloud(identifier, subject)
                for identifier in inputs["point_cloud_ids"]
            ):
                raise ContractViolation("Ready owned point clouds are required.")
            selection = self._bag_selection(inputs["bag"], subject)
        else:
            if (subject, inputs["model_3d_id"]) not in self.models and inputs[
                "model_3d_id"
            ] != 789:
                raise ContractViolation("Ready owned model is required.")
        self._counter += 1
        upstream_id = f"reference-{self._counter}"
        generated_id = 10000 + self._counter
        if operation == "validate_point_cloud":
            outcomes = []
            for index, source in enumerate(inputs["point_clouds"]):
                cloud_id = None
                outcome = "ready"
                if source["kind"] == "upload":
                    cloud_id = self.uploads[source["upload_url"]][0]
                elif source["kind"] == "asset":
                    cloud_id = source["asset_id"]
                    outcome = (
                        "ready" if self._owned_cloud(cloud_id, subject) else "invalid"
                    )
                else:
                    outcome = self.remote_sources.get(source["url"], "failed")
                    if outcome != "failed":
                        cloud_id = generated_id * 100 + index
                item = {
                    "source_index": index,
                    "outcome": outcome,
                    "ready": outcome == "ready",
                }
                if cloud_id is not None:
                    self.point_clouds[subject, cloud_id] = outcome == "ready"
                    item["point_cloud_id"] = cloud_id
                if outcome == "ready":
                    item.update(
                        crs="EPSG:28992",
                        bounds=[0, 0, 10, 2],
                        point_count=100,
                        point_density=5.0,
                    )
                else:
                    item["diagnostic"] = (
                        "unsupported_point_cloud"
                        if outcome == "invalid"
                        else "preparation_failed"
                    )
                outcomes.append(item)
            payload = {
                "all_ready": all(item["ready"] for item in outcomes),
                "point_clouds": outcomes,
            }
        elif operation == "reconstruct_buildings":
            assert selection is not None
            bag_id = (
                inputs["bag"]["asset_id"]
                if inputs["bag"]["kind"] == "asset"
                else generated_id
            )
            self.bags[subject, bag_id] = selection
            formats = ["cityjson", "obj", "gpkg", "3dtiles"]
            self.models[subject, generated_id] = formats
            payload = {
                "model_3d_id": generated_id,
                "bag_id": bag_id,
                "building_ids": selection,
                "artifacts": self._artifacts(generated_id, formats),
                "bag_dataset_date": "2026-01-01",
            }
            if inputs.get("name"):
                payload["name"] = inputs["name"]
        elif operation == "convert_format":
            self.models[subject, inputs["model_3d_id"]] = sorted(
                set(self.models.get((subject, inputs["model_3d_id"]), []))
                | set(inputs["formats"])
            )
            payload = {
                "model_3d_id": inputs["model_3d_id"],
                "artifacts": self._artifacts(inputs["model_3d_id"], inputs["formats"]),
            }
        else:
            payload = {
                "model_3d_id": inputs["model_3d_id"],
                "completed": True,
                "records_exported": 1,
            }
            if inputs.get("sharedProfileId"):
                payload["sharedProfileId"] = inputs["sharedProfileId"]
        self._results[upstream_id] = (
            subject,
            Results(outputs={CONTRACTS[process_id].output_name: payload}),
        )
        return ReferenceSubmission(
            upstream_id,
            StatusCode.successful
            if mode == JobControlOption.execute_sync
            else StatusCode.accepted,
            "Reference execution completed"
            if mode == JobControlOption.execute_sync
            else "Reference execution accepted",
        )

    def _artifacts(self, model_id: int, formats: list[str]) -> dict[str, Any]:
        return {
            format: {
                "href": (
                    f"{self.artifact_base_url}/api/v1/reconstruction/"
                    f"{model_id}/export/{format}"
                ),
                "type": "application/zip",
            }
            for format in formats
        }

    def artifact(self, model_id: int, format: str, subject: str) -> bytes | None:
        if format not in self.models.get((subject, model_id), []):
            return None
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr(
                "README.txt",
                f"Deterministic demo artifact: {format}; model {model_id}.",
            )
        return buffer.getvalue()

    def status(
        self, upstream_id: str, subject: str
    ) -> tuple[StatusCode, str | None, int | None, datetime | None, datetime | None]:
        return (
            StatusCode.successful,
            "Reference execution completed",
            100,
            datetime.now(UTC),
            datetime.now(UTC),
        )

    def results(self, upstream_id: str, subject: str) -> Results | None:
        record = self._results.get(upstream_id)
        return record[1] if record is not None and record[0] == subject else None

    def output(self, upstream_id: str, output_id: str, subject: str) -> Any | None:
        results = self.results(upstream_id, subject)
        return results.outputs.get(output_id) if results is not None else None


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
