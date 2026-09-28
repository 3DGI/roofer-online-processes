from unittest.mock import patch

import pytest
from api.process_contracts import CONTRACTS, RooferContractValidator
from api.reference_backend import (
    ReferenceAuthenticator,
    ReferenceBackend,
    ReferenceCatalog,
    ReferenceJobStore,
)
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from ogc_processes.interfaces import ContractViolation
from ogc_processes.models import Results
from ogc_processes.router import create_app


@pytest.fixture
def service():
    backend = ReferenceBackend(artifact_base_url="http://testserver")
    store = ReferenceJobStore()
    app = FastAPI()
    app.mount(
        "/ogcapi",
        create_app(
            catalog=ReferenceCatalog(),
            backend=backend,
            store=store,
            authenticator=ReferenceAuthenticator(),
            validator=RooferContractValidator(),
        ),
    )

    @app.get("/api/v1/reconstruction/{model_id}/export/{format}")
    def artifact(model_id: int, format: str):
        content = backend.artifact(model_id, format)
        if content is None:
            raise HTTPException(404)
        return Response(content, media_type=backend.artifact_media_type(format))

    return TestClient(app), backend, store


def execute(client, operation, inputs, sync=True):
    return client.post(
        f"/ogcapi/processes/roofer:{operation}:v1/execution",
        json={"inputs": inputs},
        headers={
            "Authorization": "Bearer owner",
            "Prefer": "respond-sync" if sync else "respond-async",
        },
    )


def test_artifact_urls_use_configured_public_base_url() -> None:
    backend = ReferenceBackend(artifact_base_url="https://api.example.test/proxy/")

    assert backend._artifacts(42, ["gpkg"])["gpkg"]["href"] == (
        "https://api.example.test/proxy/api/v1/reconstruction/42/export/gpkg"
    )
    assert ReferenceBackend().artifact_base_url == "http://localhost:8000"


PUBLISHED_CONTRACTS = [process_id for process_id in CONTRACTS if not process_id.endswith("export_to_3dcitydb:v1")]


@pytest.mark.parametrize("process_id", PUBLISHED_CONTRACTS)
def test_examples_and_published_schemas(service, process_id):
    client, _, _ = service
    contract = CONTRACTS[process_id]
    description = client.get(f"/ogcapi/processes/{process_id}").json()
    Draft202012Validator.check_schema(description["inputsSchema"])
    Draft202012Validator(description["inputsSchema"]).validate(contract.example)
    contract.inputs.model_validate(contract.example)
    for name, value in contract.example.items():
        Draft202012Validator(description["inputs"][name]["schema"]).validate({name: value})
    response = execute(client, process_id.split(":")[1], contract.example)
    assert response.status_code == 200, response.text
    output = response.json()["outputs"][contract.output_name]
    Draft202012Validator(description["outputs"][contract.output_name]["schema"]).validate(output)
    contract.output.model_validate(output)


def test_reconstruction_input_schemas_only_include_referenced_definitions():
    description = ReferenceCatalog().get_process("roofer:reconstruct_buildings:v1")
    assert description is not None
    definitions = {"BAGArea", "BAGAsset", "BAGBuildings"}

    for name in ["point_cloud_ids", "name", "config"]:
        assert not definitions.intersection(description.inputs[name].schema_.get("$defs", {}))

    bag_schema = description.inputs["bag"].schema_
    assert definitions.issubset(bag_schema["$defs"])
    validator = Draft202012Validator(bag_schema)
    for selector in [
        {"kind": "asset", "asset_id": 456},
        {"kind": "buildings", "building_ids": ["0000000000000001"]},
        {
            "kind": "area",
            "wkt": "POLYGON ((-1 -1,3 -1,3 3,-1 3,-1 -1))",
            "crs": "EPSG:28992",
        },
    ]:
        validator.validate({"bag": selector})


INVALID = [
    {},
    {"point_clouds": []},
    {"point_clouds": [{"kind": "asset", "asset_id": 123, "url": "secret"}]},
    {"point_clouds": [{"kind": "asset", "asset_id": 123}]},
    {"point_clouds": [{"kind": "upload", "upload_url": "https://example.org/a.laz"}]},
    {"point_clouds": [{"kind": "url", "url": "file:///secret"}]},
    {"point_clouds": [{"kind": "url", "url": "https://user:secret@data.example/a.laz"}]},
]


@pytest.mark.parametrize("inputs", INVALID)
def test_invalid_inputs_have_no_side_effects(service, inputs):
    client, backend, store = service
    response = execute(client, "validate_point_cloud", inputs)
    assert response.status_code == 400
    assert "secret" not in response.text
    assert backend._counter == 0
    assert store.list("owner") == []


@pytest.mark.parametrize(
    "bag",
    [
        None,
        {},
        {"kind": "asset", "asset_id": False},
        {"kind": "buildings", "building_ids": []},
        {"kind": "buildings", "building_ids": [" "]},
        {"kind": "buildings", "building_ids": ["missing"]},
        {"kind": "buildings", "building_ids": ["0000000000000001"] * 2},
        {"kind": "asset", "asset_id": 2, "building_ids": ["1"]},
        *[
            {"kind": "area", "wkt": wkt, "crs": "EPSG:28992"}
            for wkt in [
                "invalid",
                "POINT (0 0)",
                "POLYGON EMPTY",
                "POLYGON ((0 0,2 2,0 2,2 0,0 0))",
                "POLYGON ((30 30,31 30,31 31,30 30))",
            ]
        ],
        {"kind": "area", "wkt": "POLYGON ((0 0,2 0,2 2,0 0))", "crs": "EPSG:4326"},
    ],
)
def test_invalid_selectors_before_submission(service, bag):
    client, backend, store = service
    response = execute(client, "reconstruct_buildings", {"point_cloud_ids": [123], "bag": bag})
    assert response.status_code == 400
    assert backend._counter == 0
    assert not store.list("owner")


def test_remote_point_cloud_placeholders_always_succeed(service):
    client, backend, _ = service
    sources = [
        {"kind": "url", "url": url}
        for url in [
            "https://data.example/survey.laz",
            "https://data.example/invalid.laz",
            "https://unknown.example/any-cloud.laz?signature=secret",
        ]
    ]
    response = execute(client, "validate_point_cloud", {"point_clouds": sources})
    assert response.status_code == 200
    assert "https://" not in response.text and "secret" not in response.text
    report = response.json()["outputs"]["validation_report"]
    assert report["all_ready"] is True
    assert [item["outcome"] for item in report["point_clouds"]] == ["ready"] * 3
    cloud = report["point_clouds"][0]["point_cloud_id"]
    bag = {"kind": "asset", "asset_id": 2}
    assert execute(client, "reconstruct_buildings", {"point_cloud_ids": [cloud], "bag": bag}).status_code == 200
    assert all(item["ready"] for item in report["point_clouds"])
    assert not backend._owned_cloud(cloud, "another-user")


@pytest.mark.parametrize("sync", [True, False])
def test_point_cloud_validation_sleeps_for_five_seconds(service, sync):
    client, _, _ = service
    with patch("api.reference_backend.sleep") as sleeper:
        response = execute(
            client,
            "validate_point_cloud",
            {"point_clouds": [{"kind": "url", "url": "https://data.example/a.laz"}]},
            sync=sync,
        )
    assert response.status_code == (200 if sync else 201)
    sleeper.assert_called_once_with(5)


@pytest.mark.parametrize(
    "wkt",
    [
        "POLYGON ((0.5 0.5,1.5 0.5,1.5 1.5,0.5 1.5,0.5 0.5))",
        (
            "MULTIPOLYGON (((-0.5 -0.5,2.5 -0.5,2.5 2.5,-0.5 2.5,-0.5 -0.5)),"
            "((3.5 -0.5,6.5 -0.5,6.5 2.5,3.5 2.5,3.5 -0.5)))"
        ),
    ],
)
def test_buffered_area_and_limit(service, wkt):
    client, backend, _ = service
    inputs = {
        "point_cloud_ids": [123],
        "bag": {"kind": "area", "wkt": wkt, "crs": "EPSG:28992"},
    }
    response = execute(client, "reconstruct_buildings", inputs)
    assert response.status_code == 200
    ids = response.json()["outputs"]["building_model"]["building_ids"]
    assert ids[0] == "0000000000000001"
    backend.feature_limit = 0
    counter = backend._counter
    assert execute(client, "reconstruct_buildings", inputs).status_code == 400
    assert backend._counter == counter


def test_retrieval_artifacts_and_bad_backend(service):
    client, backend, _ = service
    created = execute(
        client,
        "convert_format",
        {"model_3d_id": 789, "formats": ["gpkg", "cityjson"]},
        sync=False,
    )
    location = created.headers["location"]
    headers = {"Authorization": "Bearer owner"}
    assert client.get(location, headers=headers).json()["status"] == "successful"
    complete = client.get(location + "/results", headers=headers).json()["outputs"]["converted_model"]
    assert (
        client.get(location + "/results?outputs=converted_model", headers=headers).json()["outputs"]["converted_model"]
        == complete
    )
    assert client.get(location + "/results/converted_model", headers=headers).json() == complete
    artifact = client.get(complete["artifacts"]["gpkg"]["href"])
    assert artifact.headers["content-type"] == "application/geopackage+sqlite3"
    assert artifact.content == (backend.data_dir / "reconstruction.gpkg").read_bytes()
    cityjson_url = backend._artifacts(789, ["cityjson"])["cityjson"]["href"]
    cityjson = client.get(cityjson_url)
    assert cityjson.status_code == 200
    assert cityjson.headers["content-type"] == "application/json"
    assert cityjson.content == (backend.data_dir / "reconstruction.city.json").read_bytes()
    assert (
        client.get(
            complete["artifacts"]["gpkg"]["href"],
            headers={"Authorization": "Bearer other"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/reconstruction/789/export/unsupported").status_code == 404
    backend._results["reference-1"] = (
        "owner",
        Results(outputs={"converted_model": {"password": "secret"}}),
    )
    for suffix in [
        "/results",
        "/results?outputs=converted_model",
        "/results/converted_model",
        "/results/converted_model/0",
    ]:
        response = client.get(location + suffix, headers=headers)
        assert response.status_code == 500 and "secret" not in response.text
    original = backend.results
    backend.results = lambda *args: Results(outputs={"converted_model": {"password": "secret"}})
    assert execute(client, "convert_format", {"model_3d_id": 789, "formats": ["gpkg"]}).status_code == 500
    backend.results = original


def test_unpublished_citydb_contract_defaults_precedence_and_schema(service):
    client, _, _ = service
    validator = RooferContractValidator()
    process = "roofer:export_to_3dcitydb:v1"
    explicit = {
        "model_3d_id": 789,
        "host": "db.example",
        "port": 5432,
        "database": "db",
        "user": "operator",
        "password": " secret ",
    }
    normalized = validator.validate_inputs(process, explicit)
    assert normalized["password"] == " secret " and normalized["schema"] == "citydb"
    assert normalized["useSSL"] is False and normalized["importMode"] == "import_all"
    profile = validator.validate_inputs(process, explicit | {"sharedProfileId": "profile"})
    assert not set(explicit.keys() - {"model_3d_id"}) & set(profile)
    schema = CONTRACTS[process].inputs.model_json_schema(by_alias=True)
    Draft202012Validator.check_schema(schema)
    assert list(Draft202012Validator(schema).iter_errors({"model_3d_id": 789}))
    for inputs in [
        {"model_3d_id": 789},
        explicit | {"port": True},
        explicit | {"useSSL": "false"},
        explicit | {"importMode": "invalid"},
        explicit | {"unknown": "secret"},
    ]:
        with pytest.raises(ContractViolation):
            validator.validate_inputs(process, inputs)
    assert client.get(f"/ogcapi/processes/{process}").status_code == 404
    assert execute(client, "export_to_3dcitydb", explicit).status_code == 404


@pytest.mark.parametrize(
    "operation,inputs",
    [
        ("convert_format", {"model_3d_id": 789, "formats": ["obj", "obj"]}),
        ("convert_format", {"model_3d_id": 789, "formats": ["unsupported"]}),
        ("convert_format", {"model_3d_id": 789, "formats": []}),
        (
            "reconstruct_buildings",
            {"point_cloud_ids": [123, 123], "bag": {"kind": "asset", "asset_id": 2}},
        ),
        (
            "reconstruct_buildings",
            {"point_cloud_ids": [], "bag": {"kind": "asset", "asset_id": 2}},
        ),
    ],
)
def test_other_invalid_lists_have_no_side_effects(service, operation, inputs):
    client, backend, store = service
    assert execute(client, operation, inputs).status_code == 400
    assert backend._counter == 0 and not store.list("owner")


def test_upload_input_is_rejected_and_identifier_selection_is_sorted(service):
    client, backend, store = service
    upload_url = "https://roofer.example/api/v1/pointcloud/upload/123"
    assert (
        execute(
            client,
            "validate_point_cloud",
            {"point_clouds": [{"kind": "upload", "upload_url": upload_url}]},
        ).status_code
        == 400
    )
    assert backend._counter == 0 and not store.list("owner")
    response = execute(
        client,
        "reconstruct_buildings",
        {
            "point_cloud_ids": [123],
            "bag": {
                "kind": "buildings",
                "building_ids": ["0000000000000002", "0000000000000001"],
            },
        },
    )
    model = response.json()["outputs"]["building_model"]
    assert model["building_ids"] == ["0000000000000001", "0000000000000002"]
    reconstruction_download = client.get(model["artifacts"]["gpkg"]["href"])
    assert reconstruction_download.status_code == 200
    assert reconstruction_download.content == (backend.data_dir / "reconstruction.gpkg").read_bytes()
    reused = execute(
        client,
        "reconstruct_buildings",
        {
            "point_cloud_ids": [123],
            "bag": {"kind": "asset", "asset_id": model["bag_id"]},
        },
    )
    assert reused.json()["outputs"]["building_model"]["building_ids"] == model["building_ids"]
    assert model["bag_id"] not in [identifier for owner, identifier in backend.bags if owner == "other"]
    # Disjoint polygons' one-metre buffers overlap and collectively contain footprint 1.
    wkt = "MULTIPOLYGON (((-1 -1,0.8 -1,0.8 3,-1 3,-1 -1)),((1.2 -1,3 -1,3 3,1.2 3,1.2 -1)))"
    response = execute(
        client,
        "reconstruct_buildings",
        {
            "point_cloud_ids": [123],
            "bag": {"kind": "area", "wkt": wkt, "crs": "EPSG:28992"},
        },
    )
    assert response.json()["outputs"]["building_model"]["building_ids"] == ["0000000000000001"]
