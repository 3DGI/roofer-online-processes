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


def test_async_execution_returns_job_location() -> None:
    response = client.post(
        "/ogcapi/processes/roofer%3Areconstruct_buildings%3Av1/execution",
        json={"inputs": {"point_cloud_ids": [1], "bag_id": 2}, "mode": "execute-async"},
        headers={"Authorization": "Bearer test-user"},
    )

    assert response.status_code == 201
    assert response.headers["location"].startswith("http://testserver/ogcapi/jobs/")
    assert response.json()["status"] == "accepted"


def test_sync_execution_returns_results() -> None:
    response = client.post(
        "/ogcapi/processes/roofer%3Avalidate_point_cloud%3Av1/execution",
        json={"inputs": {"point_cloud": "demo.laz"}, "mode": "execute-sync"},
    )

    assert response.status_code == 200
    assert response.json()["outputs"]["result"]["status"] == "successful"


def test_jobs_are_scoped_to_authenticated_subject() -> None:
    created = client.post(
        "/ogcapi/processes/roofer%3Areconstruct_buildings%3Av1/execution",
        json={"inputs": {}, "mode": "execute-async"},
        headers={"Authorization": "Bearer owner"},
    )
    job_id = created.json()["jobID"]

    response = client.get(
        f"/ogcapi/jobs/{job_id}", headers={"Authorization": "Bearer another-user"}
    )

    assert response.status_code == 404
