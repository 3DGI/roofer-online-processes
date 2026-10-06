"""Production contracts must reject invalid requests before host submission."""

import math

import pytest
from jsonschema import Draft202012Validator
from ogc_processes.interfaces import ContractViolation
from ogc_processes.models import JobControlOption, Results
from pydantic import ValidationError
from roofer_processes_contracts.catalog import RooferCatalog, RooferContractValidator
from roofer_processes_contracts.models import PROCESS_ID, ReconstructionInputs


def inputs(**overrides: object) -> dict[str, object]:
    return {
        "point_clouds": [{"kind": "url", "url": "https://data.example/survey.laz?signature=secret"}],
        "bag": {"kind": "buildings", "building_ids": ["0000000000000001"]},
        **overrides,
    }


def test_defaults_and_published_schema() -> None:
    model = ReconstructionInputs.model_validate(inputs())
    assert model.formats == ["cityjson"]
    assert model.config.terrain is True
    normalized = model.model_dump(mode="json", by_alias=True)
    assert normalized["config"]["bld-class"] == 6
    assert normalized["config"]["terrain-grid-cellsize"] == 5
    catalog = RooferCatalog()
    assert [process.id for process in catalog.list_processes()] == [PROCESS_ID]
    assert catalog.get_process("roofer:reconstruct_buildings:v1") is None
    description = catalog.get_process(PROCESS_ID)
    assert description.jobControlOptions == [JobControlOption.execute_async]
    Draft202012Validator.check_schema(description.inputsSchema)
    Draft202012Validator(description.inputsSchema).validate(normalized)


@pytest.mark.parametrize(
    "overrides",
    [
        {"point_clouds": []},
        {"point_clouds": [{"kind": "asset", "asset_id": 1}]},
        {"point_clouds": [{"kind": "url", "url": "file:///secret.laz"}]},
        {"point_clouds": [{"kind": "url", "url": "https://user:secret@data.example/survey.laz"}]},
        {"bag": {"kind": "asset", "asset_id": 1}},
        {"bag": {"kind": "buildings", "building_ids": ["x", "x"]}},
        {"bag": {"kind": "area", "wkt": "POINT(1 2)", "crs": "EPSG:28992"}},
        {"formats": []},
        {"formats": ["cityjson", "cityjson"]},
        {"formats": ["unsupported"]},
        {"formats": ["cityjson_terrain"], "config": {"terrain": False}},
        {"config": {"terrain": "false"}},
        {"config": {"output": "/etc/secret"}},
        {"config": {"complexity-factor": math.inf}},
        {"config": {"bld-class": True}},
        {"config": {"plane-detect-k": -1}},
    ],
)
def test_invalid_input_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises((ValidationError, ValueError)):
        ReconstructionInputs.model_validate(inputs(**overrides))
    with pytest.raises(ContractViolation):
        RooferContractValidator().validate_inputs(PROCESS_ID, inputs(**overrides))


def test_all_formats_and_safe_zip_result() -> None:
    formats = ["cityjson", "gpkg", "obj", "cityjson_terrain", "3dtiles"]
    normalized = RooferContractValidator().validate_inputs(PROCESS_ID, inputs(formats=formats))
    assert normalized["formats"] == formats
    result = RooferContractValidator().validate_results(
        PROCESS_ID,
        Results(
            outputs={
                "building_model": {
                    "model_3d_id": 1,
                    "bag_id": 2,
                    "building_ids": ["0000000000000001"],
                    "artifacts": {
                        fmt: {
                            "href": f"https://roofer.example/api/v1/reconstruction/1/export/{fmt}",
                            "type": "application/zip",
                        }
                        for fmt in formats
                    },
                }
            }
        ),
    )
    assert set(result.outputs["building_model"]["artifacts"]) == set(formats)
    with pytest.raises(ContractViolation):
        RooferContractValidator().validate_results(PROCESS_ID, Results(outputs={"validation_report": {}}))
