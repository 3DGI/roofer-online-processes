"""V2 domain contracts; V1 fixture contracts remain independent."""

from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from shapely import from_wkt

PROCESS_ID = "roofer:reconstruct_buildings:v2"
Format = Literal["cityjson", "gpkg", "obj", "cityjson_terrain", "3dtiles"]
Nonblank = Annotated[str, Field(strict=True, min_length=1, pattern=r"\S")]
PositiveID = Annotated[int, Field(strict=True, gt=0)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True)


class RooferConfig(ContractModel):
    """The numeric and boolean options in Roofer's current configuration form."""

    bld_class: Annotated[int, Field(strict=True, ge=0, le=255, alias="bld-class")] = 6
    grnd_class: Annotated[int, Field(strict=True, ge=0, le=255, alias="grnd-class")] = 2
    ceil_point_density: Annotated[float, Field(strict=True, gt=0, alias="ceil-point-density")] = 20.0
    lod11_fallback_area: Annotated[int, Field(strict=True, gt=0, alias="lod11-fallback-area")] = 30000
    clear_insufficient: Annotated[bool, Field(strict=True, alias="clear-insufficient")] = True
    complexity_factor: Annotated[float, Field(strict=True, ge=0, le=1, alias="complexity-factor")] = 0.888
    clip_terrain: Annotated[bool, Field(strict=True, alias="clip-terrain")] = True
    lod13_step_height: Annotated[float, Field(strict=True, gt=0, alias="lod13-step-height")] = 3.0
    plane_detect_k: Annotated[int, Field(strict=True, ge=3, alias="plane-detect-k")] = 15
    plane_detect_min_points: Annotated[int, Field(strict=True, ge=3, alias="plane-detect-min-points")] = 15
    plane_detect_epsilon: Annotated[float, Field(strict=True, gt=0, alias="plane-detect-epsilon")] = 0.3
    lod11_fallback_planes: Annotated[int, Field(strict=True, gt=0, alias="lod11-fallback-planes")] = 900
    terrain: Annotated[bool, Field(strict=True)] = True
    terrain_grid_cellsize: Annotated[float, Field(strict=True, gt=0, alias="terrain-grid-cellsize")] = 5.0


class RemoteSource(ContractModel):
    kind: Literal["url"]
    url: Nonblank

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.fragment
            or parts.port not in {None, 80, 443}
        ):
            raise ValueError("An HTTP(S) URL on a standard HTTP(S) port is required")
        return value


class BAGBuildings(ContractModel):
    kind: Literal["buildings"]
    building_ids: Annotated[list[Nonblank], Field(min_length=1, json_schema_extra={"uniqueItems": True})]

    @field_validator("building_ids")
    @classmethod
    def unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Duplicate building identifiers")
        return values


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
            or geometry.has_z
        ):
            raise ValueError("A valid nonempty two-dimensional polygon is required")
        return value


class ReconstructionInputs(ContractModel):
    point_clouds: Annotated[list[RemoteSource], Field(min_length=1, json_schema_extra={"uniqueItems": True})]
    bag: Annotated[BAGBuildings | BAGArea, Field(discriminator="kind")]
    name: Annotated[Nonblank, Field(max_length=200)] | None = None
    config: RooferConfig = Field(default_factory=RooferConfig)
    formats: Annotated[list[Format], Field(min_length=1, json_schema_extra={"uniqueItems": True})] = Field(
        default_factory=lambda: ["cityjson"]
    )

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len({source.url for source in self.point_clouds}) != len(self.point_clouds):
            raise ValueError("Duplicate source URLs")
        if len(set(self.formats)) != len(self.formats):
            raise ValueError("Duplicate formats")
        if "cityjson_terrain" in self.formats and not self.config.terrain:
            raise ValueError("Terrain CityJSON requires terrain=true")
        return self


class Artifact(ContractModel):
    href: Nonblank
    type: Literal["application/zip"] = "application/zip"

    @field_validator("href")
    @classmethod
    def http_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("An HTTP(S) artifact URL is required")
        return value


class BuildingModel(ContractModel):
    model_3d_id: PositiveID
    bag_id: PositiveID
    building_ids: Annotated[list[Nonblank], Field(min_length=1, json_schema_extra={"uniqueItems": True})]
    bag_dataset_date: str | None = None
    name: str | None = None
    artifacts: Annotated[dict[Format, Artifact], Field(min_length=1)]

    @field_validator("building_ids")
    @classmethod
    def sorted_unique(cls, values: list[str]) -> list[str]:
        if values != sorted(set(values)):
            raise ValueError("Building identifiers must be sorted and unique")
        return values
