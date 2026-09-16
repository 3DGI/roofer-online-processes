import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from api.process_contracts import CONTRACTS, RooferContractValidator
from api.reference_backend import (
    ReferenceAuthenticator,
    ReferenceBackend,
    ReferenceCatalog,
    ReferenceJobStore,
)
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
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
    def artifact(request: Request, model_id: int, format: str):
        owner = (
            ReferenceAuthenticator()
            .authenticate(request.headers.get("authorization"))
            .subject
        )
        content = backend.artifact(model_id, format, owner)
        if content is None:
            raise HTTPException(404)
        return Response(content, media_type="application/zip")

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


@pytest.mark.parametrize("process_id", CONTRACTS)
def test_examples_and_published_schemas(service, process_id):
    client, _, _ = service
    contract = CONTRACTS[process_id]
    description = client.get(f"/ogcapi/processes/{process_id}").json()
    Draft202012Validator.check_schema(description["inputsSchema"])
    Draft202012Validator(description["inputsSchema"]).validate(contract.example)
    contract.inputs.model_validate(contract.example)
    for name, value in contract.example.items():
        Draft202012Validator(description["inputs"][name]["schema"]).validate(value)
    response = execute(client, process_id.split(":")[1], contract.example)
    assert response.status_code == 200, response.text
    output = response.json()["outputs"][contract.output_name]
    Draft202012Validator(
        description["outputs"][contract.output_name]["schema"]
    ).validate(output)
    contract.output.model_validate(output)


INVALID = [
    {},
    {"point_clouds": []},
    {"point_clouds": [{"kind": "asset"}]},
    {"point_clouds": [{"kind": "asset", "asset_id": 123, "url": "secret"}]},
    {"point_clouds": [{"kind": "url", "url": "file:///secret"}]},
    {
        "point_clouds": [
            {"kind": "url", "url": "https://user:secret@data.example/a.laz"}
        ]
    },
    {"point_clouds": [{"kind": "asset", "asset_id": 123}] * 2},
    {
        "point_clouds": [
            {
                "kind": "upload",
                "upload_url": "https://roofer.example/api/v1/pointcloud/upload/125",
            }
        ]
    },
]
INVALID += [
    {"point_clouds": [{"kind": "asset", "asset_id": value}]}
    for value in [0, -1, True, 1.2, "123"]
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
    response = execute(
        client, "reconstruct_buildings", {"point_cloud_ids": [123], "bag": bag}
    )
    assert response.status_code == 400
    assert backend._counter == 0
    assert not store.list("owner")


def test_partial_preparation_and_readiness(service):
    client, backend, _ = service
    sources = [
        {"kind": "url", "url": url}
        for url in [
            "https://data.example/survey.laz",
            "https://data.example/invalid.laz",
            "https://data.example/failed.laz?signature=secret",
        ]
    ]
    response = execute(client, "validate_point_cloud", {"point_clouds": sources})
    assert response.status_code == 200
    assert "https://" not in response.text and "secret" not in response.text
    report = response.json()["outputs"]["validation_report"]
    assert report["all_ready"] is False
    assert [item["outcome"] for item in report["point_clouds"]] == [
        "ready",
        "invalid",
        "failed",
    ]
    cloud = report["point_clouds"][0]["point_cloud_id"]
    bag = {"kind": "asset", "asset_id": 2}
    assert (
        execute(
            client, "reconstruct_buildings", {"point_cloud_ids": [cloud], "bag": bag}
        ).status_code
        == 200
    )
    invalid = report["point_clouds"][1]["point_cloud_id"]
    assert (
        execute(
            client, "reconstruct_buildings", {"point_cloud_ids": [invalid], "bag": bag}
        ).status_code
        == 400
    )
    assert not backend._owned_cloud(cloud, "another-user")


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
        client, "convert_format", {"model_3d_id": 789, "formats": ["obj"]}, sync=False
    )
    location = created.headers["location"]
    headers = {"Authorization": "Bearer owner"}
    assert client.get(location, headers=headers).json()["status"] == "successful"
    complete = client.get(location + "/results", headers=headers).json()["outputs"][
        "converted_model"
    ]
    assert (
        client.get(
            location + "/results?outputs=converted_model", headers=headers
        ).json()["outputs"]["converted_model"]
        == complete
    )
    assert (
        client.get(location + "/results/converted_model", headers=headers).json()
        == complete
    )
    artifact = client.get(complete["artifacts"]["obj"]["href"], headers=headers)
    assert artifact.headers["content-type"] == "application/zip"
    assert ZipFile(BytesIO(artifact.content)).testzip() is None
    assert (
        client.get(
            complete["artifacts"]["obj"]["href"],
            headers={"Authorization": "Bearer other"},
        ).status_code
        == 404
    )
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
    backend.results = lambda *args: Results(
        outputs={"converted_model": {"password": "secret"}}
    )
    assert (
        execute(
            client, "convert_format", {"model_3d_id": 789, "formats": ["obj"]}
        ).status_code
        == 500
    )
    backend.results = original


def test_citydb_defaults_precedence_and_schema(service):
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
    profile = validator.validate_inputs(
        process, explicit | {"sharedProfileId": "profile"}
    )
    assert not set(explicit.keys() - {"model_3d_id"}) & set(profile)
    for inputs in [
        {"model_3d_id": 789},
        explicit | {"port": True},
        explicit | {"useSSL": "false"},
        explicit | {"importMode": "invalid"},
        explicit | {"unknown": "secret"},
    ]:
        response = execute(client, "export_to_3dcitydb", inputs)
        assert response.status_code == 400 and "secret" not in response.text
    schema = client.get(f"/ogcapi/processes/{process}").json()["inputsSchema"]
    assert list(Draft202012Validator(schema).iter_errors({"model_3d_id": 789}))
    receipt = execute(client, "export_to_3dcitydb", explicit).json()
    assert "secret" not in json.dumps(receipt) and "db.example" not in json.dumps(
        receipt
    )


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


def test_exact_identifier_selection_owned_upload_and_overlap(service):
    client, backend, store = service
    upload_url = "https://roofer.example/api/v1/pointcloud/upload/123"
    backend.uploads[upload_url] = (123, True, "other")
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
    reused = execute(
        client,
        "reconstruct_buildings",
        {
            "point_cloud_ids": [123],
            "bag": {"kind": "asset", "asset_id": model["bag_id"]},
        },
    )
    assert (
        reused.json()["outputs"]["building_model"]["building_ids"]
        == model["building_ids"]
    )
    assert model["bag_id"] not in [
        identifier for owner, identifier in backend.bags if owner == "other"
    ]
    # Disjoint polygons' one-metre buffers overlap and collectively contain footprint 1.
    wkt = (
        "MULTIPOLYGON (((-1 -1,0.8 -1,0.8 3,-1 3,-1 -1)),"
        "((1.2 -1,3 -1,3 3,1.2 3,1.2 -1)))"
    )
    response = execute(
        client,
        "reconstruct_buildings",
        {
            "point_cloud_ids": [123],
            "bag": {"kind": "area", "wkt": wkt, "crs": "EPSG:28992"},
        },
    )
    assert response.json()["outputs"]["building_model"]["building_ids"] == [
        "0000000000000001"
    ]
