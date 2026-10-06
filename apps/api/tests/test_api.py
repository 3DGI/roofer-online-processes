from email import policy
from email.parser import BytesParser

from api.main import app
from fastapi import Request
from fastapi.testclient import TestClient
from ogc_processes.router import root_url

client = TestClient(app)


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
