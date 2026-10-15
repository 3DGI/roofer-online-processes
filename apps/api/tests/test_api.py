from email import policy
from email.parser import BytesParser

from api.main import app
from api.process_contracts import CONTRACTS
from fastapi import Request
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, RefResolver
from ogc_processes.router import root_url

client = TestClient(app)


def test_mounted_swagger_docs_load_the_ogc_schema() -> None:
    for prefix in ("", "/public"):
        with TestClient(app, root_path=prefix) as docs_client:
            response = docs_client.get(f"{prefix}/ogcapi/docs")
            specification = docs_client.get(f"{prefix}/ogcapi/openapi.json")

        assert response.status_code == 200
        assert "swagger-ui" in response.text
        assert f"url: '{prefix}/ogcapi/openapi.json'" in response.text
        assert specification.status_code == 200
        assert "/processes" in specification.json()["paths"]
        assert {"url": f"{prefix}/ogcapi"} in specification.json()["servers"]


def test_root_url_combines_external_and_mount_paths_once() -> None:
    request = Request(
        {
            "type": "http",
            "scheme": "https",
            "server": ("api.example.test", 443),
            "headers": [],
            "root_path": "/public/ogcapi",
            "app_root_path": "/public",
            "path": "/public/ogcapi/",
            "query_string": b"",
        }
    )

    assert root_url(request) == "https://api.example.test/public/ogcapi"


def test_process_collection_exposes_published_processes() -> None:
    response = client.get("/ogcapi/processes")

    assert response.status_code == 200
    assert [process["id"] for process in response.json()["processes"]] == [
        "echo",
        "roofer:validate_point_cloud:v1",
        "roofer:reconstruct_buildings:v1",
        "roofer:convert_format:v1",
    ]


def test_mounted_ogc_application_has_relative_openapi_paths_and_v2_landing_links() -> None:
    landing = client.get("/ogcapi/")
    specification = client.get("/ogcapi/openapi.json")

    assert landing.status_code == 200
    service_desc = next(link for link in landing.json()["links"] if link["rel"] == "service-desc")
    assert service_desc["type"] == "application/vnd.oai.openapi+json;version=3.0"
    document = specification.json()
    assert document["openapi"] == "3.0.3"
    assert "/processes" in document["paths"]
    assert "/ogcapi/processes" not in document["paths"]

    outputs_parameter = next(
        parameter
        for parameter in document["paths"]["/jobs/{job_id}/results"]["get"]["parameters"]
        if parameter["name"] == "outputs"
    )
    assert outputs_parameter["schema"] == {
        "type": "array",
        "items": {"type": "string"},
        "title": "Outputs",
    }
    assert outputs_parameter["style"] == "form"
    assert outputs_parameter["explode"] is False


def test_openapi_documents_one_process_specific_execution_operation_per_published_process() -> None:
    published = [process["id"] for process in client.get("/ogcapi/processes").json()["processes"]]
    document = client.get("/ogcapi/openapi.json").json()
    execution_paths = {path: item["post"] for path, item in document["paths"].items() if path.endswith("/execution")}

    assert set(execution_paths) == {f"/processes/{process_id}/execution" for process_id in published}
    assert "/processes/{process_id}/execution" not in document["paths"]
    assert len({operation["operationId"] for operation in execution_paths.values()}) == len(published)

    components = document["components"]["schemas"]
    for process_id in published:
        process_key = process_id.replace(":", "_")
        operation = execution_paths[f"/processes/{process_id}/execution"]
        request_content = operation["requestBody"]["content"]["application/json"]
        body_schema = request_content["schema"]
        input_reference = body_schema["properties"]["inputs"]["$ref"]
        input_schema_name = input_reference.removeprefix("#/components/schemas/")
        input_schema = components[input_schema_name]
        description = client.get(f"/ogcapi/processes/{process_id}").json()
        assert input_schema_name == f"{process_key}_Inputs"
        assert set(input_schema["properties"]) == set(description["inputs"])
        assert "process" not in body_schema["properties"]
        assert "format" not in body_schema["properties"]
        assert "mediaType" not in body_schema["properties"]
        assert set(body_schema["properties"]["outputs"]["properties"]) == set(description["outputs"])
        assert body_schema["properties"]["response"]["enum"] == ["raw", "document"]
        assert "subscriber" in body_schema["properties"]
        for output_options in body_schema["properties"]["outputs"]["properties"].values():
            assert output_options["properties"]["transmissionMode"]["enum"] == ["value"]

        example = request_content["example"]["inputs"]
        if process_id in CONTRACTS:
            assert example == CONTRACTS[process_id].example
        else:
            assert process_id == "echo"
            assert example == {"value": "hello from Roofer"}

        required = set(input_schema.get("required", []))
        assert required == {name for name, item in description["inputs"].items() if item["minOccurs"] > 0}
        Draft202012Validator(
            input_schema,
            resolver=RefResolver.from_schema(document),
        ).validate(example)

    all_references = []

    def collect_references(value: object) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
                all_references.append(reference.removeprefix("#/components/schemas/"))
            for child in value.values():
                collect_references(child)
        elif isinstance(value, list):
            for child in value:
                collect_references(child)

    collect_references(document["paths"])
    collect_references(components)
    assert all(reference in components for reference in all_references)


def test_parent_openapi_prefixes_process_operations_and_parent_swagger_uses_parent_document() -> None:
    with TestClient(app) as docs_client:
        docs = docs_client.get("/docs")
        document = docs_client.get("/openapi.json").json()

    assert "url: '/openapi.json'" in docs.text
    for process_id in ("echo", *CONTRACTS.keys()):
        if process_id == "roofer:export_to_3dcitydb:v1":
            continue
        assert f"/ogcapi/processes/{process_id}/execution" in document["paths"]
    assert "/processes/echo/execution" not in document["paths"]


def test_async_execution_returns_job_location() -> None:
    response = client.post(
        "/ogcapi/processes/roofer%3Areconstruct_buildings%3Av1/execution",
        json={"inputs": {"point_cloud_ids": [1], "bag": {"kind": "asset", "asset_id": 2}}},
        headers={"Authorization": "Bearer test-user", "Prefer": "respond-async"},
    )

    assert response.status_code == 201
    assert response.headers["location"].startswith("http://testserver/ogcapi/jobs/")
    assert response.json()["links"][0]["href"] == response.headers["location"]
    assert response.json()["status"] == "accepted"
    assert response.json()["jobID"] == response.json()["id"]
    assert response.json()["type"] == "process"
    assert response.json()["links"][1]["rel"] == "http://www.opengis.net/def/rel/ogc/1.0/results"
    assert all("title" not in link for link in response.json()["links"])


def test_execution_defaults_to_sync_raw_and_document_uses_output_ids() -> None:
    response = client.post("/ogcapi/processes/echo/execution", json={"inputs": {"value": "hello"}})
    document = client.post(
        "/ogcapi/processes/echo/execution",
        json={"inputs": {"value": "hello"}, "response": "document"},
    )
    raw = client.post(
        "/ogcapi/processes/echo/execution",
        json={
            "inputs": {
                "value": "hello",
            },
            "outputs": {"value": {"transmissionMode": "value"}},
            "response": "raw",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("multipart/related")
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {response.headers['content-type']}\r\n\r\n".encode() + response.content
    )
    parts = list(message.iter_parts())
    assert [part["Content-ID"] for part in parts] == ["<value>", "<length>", "<values>", "<bbox>"]
    assert parts[0].get_content_type() == "text/plain"
    assert parts[0].get_content() == "hello"
    assert parts[1].get_payload(decode=True) == b"5"
    assert document.status_code == 200
    assert document.json() == {
        "value": "hello",
        "length": 5,
        "values": ["hello"],
        "bbox": {
            "value": {
                "bbox": [0, 0, 1, 1],
                "crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            }
        },
    }
    assert raw.status_code == 200
    assert raw.headers["content-type"].startswith("text/plain")
    assert raw.text == "hello"


def test_job_list_contains_ogc_10_fields_and_exception_shape() -> None:
    created = client.post(
        "/ogcapi/processes/roofer%3Areconstruct_buildings%3Av1/execution",
        json={"inputs": {"point_cloud_ids": [1], "bag": {"kind": "asset", "asset_id": 2}}},
        headers={"Prefer": "respond-async"},
    )
    listing = client.get("/ogcapi/jobs")
    missing = client.get("/ogcapi/jobs/not-a-job")

    assert created.status_code == 201
    assert listing.status_code == 200
    entry = next(job for job in listing.json()["jobs"] if job["id"] == created.json()["id"])
    assert entry["jobID"] == entry["id"]
    assert entry["type"] == "process"
    assert missing.status_code == 404
    assert missing.json()["type"] == ("http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-job")
    assert missing.json()["status"] == 404
    assert missing.json()["detail"] == "Job not found."


def test_sync_execution_returns_results() -> None:
    response = client.post(
        "/ogcapi/processes/roofer%3Avalidate_point_cloud%3Av1/execution",
        json={
            "inputs": {"point_clouds": [{"kind": "url", "url": "https://data.example/survey.laz"}]},
            "response": "document",
        },
        headers={"Prefer": "respond-sync"},
    )

    assert response.status_code == 200
    assert response.json()["validation_report"]["value"]["all_ready"] is True


def test_jobs_are_scoped_to_authenticated_subject() -> None:
    created = client.post(
        "/ogcapi/processes/roofer%3Areconstruct_buildings%3Av1/execution",
        json={
            "inputs": {
                "point_cloud_ids": [123],
                "bag": {"kind": "asset", "asset_id": 2},
            }
        },
        headers={"Authorization": "Bearer owner", "Prefer": "respond-async"},
    )
    job_id = created.json()["id"]

    response = client.get(f"/ogcapi/jobs/{job_id}", headers={"Authorization": "Bearer another-user"})

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_results_support_output_selection_and_per_output_retrieval() -> None:
    created = client.post(
        "/ogcapi/processes/roofer%3Aconvert_format%3Av1/execution",
        json={"inputs": {"model_3d_id": 789, "formats": ["gpkg"]}},
        headers={"Authorization": "Bearer result-user", "Prefer": "respond-async"},
    )
    job_id = created.json()["id"]

    selected = client.get(
        f"/ogcapi/jobs/{job_id}/results?outputs=converted_model",
        headers={"Authorization": "Bearer result-user"},
    )
    output = client.get(
        f"/ogcapi/jobs/{job_id}/results/converted_model/0",
        headers={"Authorization": "Bearer result-user"},
    )
    invalid = client.get(
        f"/ogcapi/jobs/{job_id}/results?outputs=unknown",
        headers={"Authorization": "Bearer result-user"},
    )

    assert selected.status_code == 200
    assert list(selected.json()) == ["converted_model"]
    assert f"/jobs/{job_id}/results/converted_model>" in selected.headers["link"]
    assert output.status_code == 200
    assert output.json() == selected.json()["converted_model"]["value"]
    assert invalid.status_code == 400
