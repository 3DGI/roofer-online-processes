from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_process_collection_exposes_proposal_processes() -> None:
    response = client.get("/ogcapi/processes")

    assert response.status_code == 200
    assert [process["id"] for process in response.json()["processes"]] == [
        "roofer:validate_point_cloud:v1",
        "roofer:reconstruct_buildings:v1",
        "roofer:convert_format:v1",
        "roofer:export_to_3dcitydb:v1",
    ]


def test_mounted_ogc_application_has_relative_openapi_paths_and_v2_landing_links() -> (
    None
):
    landing = client.get("/ogcapi/")
    specification = client.get("/ogcapi/openapi.json")

    assert landing.status_code == 200
    assert any(link["rel"] == "service-desc" for link in landing.json()["links"])
    assert "/processes" in specification.json()["paths"]
    assert "/ogcapi/processes" not in specification.json()["paths"]


def test_async_execution_returns_job_location() -> None:
    response = client.post(
        "/ogcapi/processes/roofer%3Areconstruct_buildings%3Av1/execution",
        json={"inputs": {"point_cloud_ids": [1], "bag_id": 2}},
        headers={"Authorization": "Bearer test-user"},
    )

    assert response.status_code == 201
    assert response.headers["location"].startswith("http://testserver/ogcapi/jobs/")
    assert response.json()["status"] == "accepted"


def test_sync_execution_returns_results() -> None:
    response = client.post(
        "/ogcapi/processes/roofer%3Avalidate_point_cloud%3Av1/execution",
        json={"inputs": {"point_cloud": "demo.laz"}},
        headers={"Prefer": "respond-sync"},
    )

    assert response.status_code == 200
    assert response.json()["outputs"]["validation_report"]["status"] == "successful"


def test_jobs_are_scoped_to_authenticated_subject() -> None:
    created = client.post(
        "/ogcapi/processes/roofer%3Areconstruct_buildings%3Av1/execution",
        json={"inputs": {}},
        headers={"Authorization": "Bearer owner"},
    )
    job_id = created.json()["id"]

    response = client.get(
        f"/ogcapi/jobs/{job_id}", headers={"Authorization": "Bearer another-user"}
    )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_results_support_output_selection_and_per_output_retrieval() -> None:
    created = client.post(
        "/ogcapi/processes/roofer%3Aconvert_format%3Av1/execution",
        json={"inputs": {}},
        headers={"Authorization": "Bearer result-user"},
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
    assert list(selected.json()["outputs"]) == ["converted_model"]
    assert output.status_code == 200
    assert output.json()["reference"].startswith("urn:roofer:result:")
    assert invalid.status_code == 400
