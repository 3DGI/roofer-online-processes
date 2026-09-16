"""Roofer contracts shared by discovery, execution, and reference examples."""

import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from ogc_processes.interfaces import ContractViolation
from ogc_processes.models import Results
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from shapely import from_wkt

PositiveID = Annotated[int, Field(strict=True, gt=0)]
Nonblank = Annotated[str, Field(strict=True, pattern=r"\S")]
Format = Literal["obj", "gpkg", "cityjson", "cityjson_terrain", "3dtiles"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def unique(values: list[Any]) -> list[Any]:
    keys = [
        json.dumps(value, sort_keys=True) if isinstance(value, dict) else value
        for value in values
    ]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate entries are not permitted")
    return values


class UploadSource(ContractModel):
    kind: Literal["upload"]
    upload_url: Nonblank

    @field_validator("upload_url")
    @classmethod
    def http_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.fragment
        ):
            raise ValueError("An HTTP(S) URL without embedded credentials is required")
        return value


class AssetSource(ContractModel):
    kind: Literal["asset"]
    asset_id: PositiveID


# Separate source forms forbid fields belonging to other branches.
class RemoteSource(ContractModel):
    kind: Literal["url"]
    url: Nonblank

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        return UploadSource.http_url(value)


Source = Annotated[
    UploadSource | AssetSource | RemoteSource, Field(discriminator="kind")
]


class PreparationInputs(ContractModel):
    point_clouds: Annotated[
        list[Source], Field(min_length=1, json_schema_extra={"uniqueItems": True})
    ]

    @field_validator("point_clouds")
    @classmethod
    def no_duplicates(cls, values: list[Any]) -> list[Any]:
        unique([value.model_dump() for value in values])
        return values


class BAGAsset(AssetSource):
    pass


class BAGBuildings(ContractModel):
    kind: Literal["buildings"]
    building_ids: Annotated[
        list[Nonblank], Field(min_length=1, json_schema_extra={"uniqueItems": True})
    ]
    _unique = field_validator("building_ids")(unique)


class BAGArea(ContractModel):
    kind: Literal["area"]
    wkt: Nonblank
    crs: Literal["EPSG:28992"]

    @field_validator("wkt")
    @classmethod
    def polygon(cls, value: str) -> str:
        geometry = from_wkt(value, on_invalid="ignore")
        if (
            geometry is None
            or geometry.geom_type not in {"Polygon", "MultiPolygon"}
            or geometry.is_empty
            or not geometry.is_valid
        ):
            raise ValueError("A valid nonempty Polygon or MultiPolygon is required")
        return value


BAGSelector = Annotated[BAGAsset | BAGBuildings | BAGArea, Field(discriminator="kind")]
IDList = Annotated[
    list[PositiveID], Field(min_length=1, json_schema_extra={"uniqueItems": True})
]


class ReconstructionInputs(ContractModel):
    point_cloud_ids: IDList
    bag: BAGSelector
    name: Nonblank | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    _unique = field_validator("point_cloud_ids")(unique)

    @field_validator("config")
    @classmethod
    def finite_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        json.dumps(value, allow_nan=False)
        return value


class ConversionInputs(ContractModel):
    model_3d_id: PositiveID
    formats: Annotated[
        list[Format], Field(min_length=1, json_schema_extra={"uniqueItems": True})
    ]
    _unique = field_validator("formats")(unique)


class ExportInputs(ContractModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        json_schema_extra={
            "anyOf": [
                {
                    "required": ["sharedProfileId"],
                    "properties": {
                        "sharedProfileId": {"type": "string", "pattern": r"\S"}
                    },
                },
                {
                    "required": ["host", "port", "database", "user", "password"],
                    "properties": {
                        "host": {"type": "string", "pattern": r"\S"},
                        "database": {"type": "string", "pattern": r"\S"},
                        "user": {"type": "string", "pattern": r"\S"},
                        "password": {"type": "string", "pattern": r"\S"},
                        "port": {"type": "integer"},
                    },
                },
            ]
        },
    )
    model_3d_id: PositiveID
    sharedProfileId: Nonblank | None = None
    host: Nonblank | None = None
    port: Annotated[int, Field(strict=True, ge=1, le=65535)] | None = None
    database: Nonblank | None = None
    user: Nonblank | None = None
    password: Nonblank | None = None
    schema_: Nonblank = Field(default="citydb", alias="schema")
    useSSL: Annotated[bool, Field(strict=True)] = False
    importMode: Literal["import_all", "skip", "delete", "terminate"] = "import_all"
    reasonForUpdate: str | None = None
    updatingPerson: str | None = None

    @model_validator(mode="after")
    def connection(self) -> Self:
        if self.sharedProfileId is None and any(
            value is None
            for value in [self.host, self.port, self.database, self.user, self.password]
        ):
            raise ValueError("A profile or complete connection is required")
        return self


class Artifact(ContractModel):
    href: Nonblank
    type: Nonblank

    @field_validator("href")
    @classmethod
    def http_url(cls, value: str) -> str:
        return UploadSource.http_url(value)


class PointCloudOutcome(ContractModel):
    source_index: Annotated[int, Field(strict=True, ge=0)]
    outcome: Literal["ready", "invalid", "failed"]
    ready: Annotated[bool, Field(strict=True)]
    point_cloud_id: PositiveID | None = None
    crs: str | None = None
    bounds: list[Annotated[float, Field(allow_inf_nan=False)]] | None = None
    point_count: Annotated[int, Field(strict=True, ge=0)] | None = None
    classification_codes: list[Annotated[int, Field(strict=True, ge=0)]] | None = None
    point_density: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    diagnostic: Literal["unsupported_point_cloud", "preparation_failed"] | None = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.ready != (self.outcome == "ready") or (
            self.ready and self.point_cloud_id is None
        ):
            raise ValueError("Inconsistent readiness")
        if self.bounds is not None and len(self.bounds) not in {4, 6}:
            raise ValueError("Bounds require four or six numbers")
        if self.classification_codes is not None:
            unique(self.classification_codes)
        return self


class ValidationReport(ContractModel):
    all_ready: Annotated[bool, Field(strict=True)]
    point_clouds: Annotated[list[PointCloudOutcome], Field(min_length=1)]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if [item.source_index for item in self.point_clouds] != list(
            range(len(self.point_clouds))
        ) or self.all_ready != all(item.ready for item in self.point_clouds):
            raise ValueError("Inconsistent batch report")
        return self


class ConvertedModel(ContractModel):
    model_3d_id: PositiveID
    artifacts: Annotated[dict[Format, Artifact], Field(min_length=1)]


class BuildingModel(ConvertedModel):
    bag_id: PositiveID
    building_ids: Annotated[
        list[Nonblank], Field(min_length=1, json_schema_extra={"uniqueItems": True})
    ]
    bag_dataset_date: str | None = None
    name: Nonblank | None = None

    @field_validator("building_ids")
    @classmethod
    def sorted_ids(cls, value: list[str]) -> list[str]:
        unique(value)
        if value != sorted(value):
            raise ValueError("Building identifiers must be sorted")
        return value


class ExportReceipt(ContractModel):
    model_3d_id: PositiveID
    completed: Literal[True]
    sharedProfileId: Nonblank | None = None
    records_exported: Annotated[int, Field(strict=True, ge=0)] | None = None


@dataclass(frozen=True)
class ProcessContract:
    inputs: type[ContractModel]
    output_name: str
    output: type[ContractModel]
    example: dict[str, Any]


CONTRACTS = {
    "roofer:validate_point_cloud:v1": ProcessContract(
        PreparationInputs,
        "validation_report",
        ValidationReport,
        {
            "point_clouds": [
                {
                    "kind": "upload",
                    "upload_url": "https://roofer.example/api/v1/pointcloud/upload/123",
                },
                {"kind": "asset", "asset_id": 124},
                {"kind": "url", "url": "https://data.example/survey.laz"},
            ]
        },
    ),
    "roofer:reconstruct_buildings:v1": ProcessContract(
        ReconstructionInputs,
        "building_model",
        BuildingModel,
        {
            "point_cloud_ids": [123],
            "bag": {"kind": "buildings", "building_ids": ["0000000000000001"]},
            "name": "Demo",
            "config": {},
        },
    ),
    "roofer:convert_format:v1": ProcessContract(
        ConversionInputs,
        "converted_model",
        ConvertedModel,
        {"model_3d_id": 789, "formats": ["cityjson", "obj"]},
    ),
    "roofer:export_to_3dcitydb:v1": ProcessContract(
        ExportInputs,
        "export_receipt",
        ExportReceipt,
        {"model_3d_id": 789, "sharedProfileId": "municipality-citydb"},
    ),
}


class RooferContractValidator:
    def validate_inputs(
        self, process_id: str, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            normalized = (
                CONTRACTS[process_id]
                .inputs.model_validate(inputs)
                .model_dump(mode="json", by_alias=True, exclude_none=True)
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise ContractViolation("Process input validation failed.") from exc
        if normalized.get("sharedProfileId"):
            for field in [
                "host",
                "port",
                "database",
                "user",
                "password",
                "schema",
                "useSSL",
            ]:
                normalized.pop(field, None)
        return normalized

    def validate_results(self, process_id: str, results: Results) -> Results:
        contract = CONTRACTS[process_id]
        if set(results.outputs) != {contract.output_name}:
            raise ContractViolation("Invalid backend results.")
        try:
            output = contract.output.model_validate(
                results.outputs[contract.output_name]
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise ContractViolation("Invalid backend results.") from exc
        return Results(
            outputs={
                contract.output_name: output.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                )
            }
        )
