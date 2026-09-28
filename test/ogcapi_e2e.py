"""Independent end-to-end example for the public OGC API.

Run against a running service with::

    uv run --package roofer-online-processes-api uvicorn api.main:app
    python test/ogcapi_e2e.py

Set OGC_API_URL to use another service. This script uses only the Python
standard library and the reference service's documented fixture inputs.
"""

import json
import logging
import os
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

OGC_API_URL = os.environ.get("OGC_API_URL", "http://localhost:8000/ogcapi").rstrip("/")
SUBJECT = "ogcapi-e2e-example"
HEADERS = {"Authorization": f"Bearer {SUBJECT}"}
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ogcapi-e2e")


class OGCAPIEndToEnd(unittest.TestCase):
    def request(self, method, path, *, body=None, headers=None):
        url = urljoin(f"{OGC_API_URL}/", path.lstrip("/"))
        request_headers = dict(HEADERS)
        if headers:
            request_headers.update(headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=request_headers, method=method)
        logger.info(">>> %s %s", method, url)
        if request_headers:
            logger.info(">>> headers: %s", request_headers)
        if body is not None:
            logger.info(">>> body: %s", json.dumps(body, sort_keys=True))
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read()
                content_type = response.headers.get_content_type()
                self.log_response(response.status, content_type, payload)
                return response.status, response.headers, payload, content_type
        except HTTPError as error:
            payload = error.read()
            self.log_response(error.code, error.headers.get_content_type(), payload)
            detail = payload.decode("utf-8", errors="replace")
            self.fail(f"{method} {url} returned HTTP {error.code}: {detail}")

    @staticmethod
    def log_response(status, content_type, payload):
        text = payload.decode("utf-8", errors="replace")
        try:
            text = json.dumps(json.loads(text), indent=2, sort_keys=True)
        except (json.JSONDecodeError, TypeError):
            pass
        preview = text if len(text) <= 1200 else f"{text[:1200]}… (truncated)"
        logger.info("<<< HTTP %s (%s)", status, content_type)
        logger.info("<<< body: %s", preview or "<empty>")

    def get_json(self, path):
        status, _, payload, _ = self.request("GET", path)
        self.assertEqual(status, 200)
        return json.loads(payload)

    def execute_async(self, process_id, inputs):
        encoded_id = quote(process_id, safe="")
        status, headers, payload, _ = self.request(
            "POST",
            f"processes/{encoded_id}/execution",
            body={"inputs": inputs},
            headers={"Prefer": "respond-async"},
        )
        self.assertEqual(status, 201)
        job = json.loads(payload)
        location = headers["Location"]
        self.assertEqual(job["status"], "accepted")
        self.assertTrue(urlparse(location).path.endswith(f"/jobs/{job['id']}"))
        return job, location

    def wait_for_success(self, location):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            url = urljoin(f"{OGC_API_URL}/", location)
            status, _, payload, _ = self.request("GET", url)
            self.assertEqual(status, 200)
            job = json.loads(payload)
            if job["status"] == "successful":
                return job
            self.assertNotEqual(job["status"], "failed", job)
            time.sleep(1)
        self.fail(f"Job did not finish within 60 seconds: {location}")

    def test_public_workflow(self):
        # Discover the service and inspect its advertised public interface.
        landing = self.get_json("/")
        links = {link["rel"]: link["href"] for link in landing["links"]}
        self.assertIn("conformance", links)
        self.assertIn("processes", links)
        self.assertIn("jobs", links)
        self.assertTrue(links["service-desc"].endswith("/openapi.json"))

        conformance = self.get_json("conformance")
        self.assertTrue(conformance["conformsTo"])
        status, _, payload, content_type = self.request("GET", "openapi.json")
        self.assertEqual(status, 200)
        self.assertIn("json", content_type)
        openapi = json.loads(payload)
        self.assertEqual(openapi["openapi"], "3.0.3")
        for path in ("/processes", "/jobs", "/jobs/{job_id}/results"):
            self.assertIn(path, openapi["paths"])

        processes = self.get_json("processes")["processes"]
        process_ids = {process["id"] for process in processes}
        expected = {
            "roofer:validate_point_cloud:v1",
            "roofer:reconstruct_buildings:v1",
            "roofer:convert_format:v1",
        }
        self.assertTrue(expected.issubset(process_ids))
        for process_id in expected:
            description = self.get_json(f"processes/{quote(process_id, safe='')}")
            self.assertEqual(description["id"], process_id)

        # Validate a fixture cloud using synchronous execution.
        status, _, payload, _ = self.request(
            "POST",
            f"processes/{quote('roofer:validate_point_cloud:v1', safe='')}/execution",
            body={"inputs": {"point_clouds": [{"kind": "url", "url": "https://data.example/survey.laz"}]}},
            headers={"Prefer": "respond-sync"},
        )
        self.assertEqual(status, 200)
        report = json.loads(payload)["outputs"]["validation_report"]
        self.assertTrue(report["all_ready"])

        # Reconstruct asynchronously, then inspect the job and both result forms.
        reconstruction_id = "roofer:reconstruct_buildings:v1"
        reconstruction, location = self.execute_async(
            reconstruction_id,
            {
                "point_cloud_ids": [123],
                "bag": {"kind": "asset", "asset_id": 2},
            },
        )
        completed = self.wait_for_success(location)
        self.assertEqual(completed["id"], reconstruction["id"])
        job = self.get_json(f"jobs/{reconstruction['id']}")
        self.assertEqual(job["status"], "successful")
        reconstruction_results = self.get_json(f"jobs/{reconstruction['id']}/results")
        output_id = "building_model"
        self.assertIn(output_id, reconstruction_results["outputs"])
        item = self.get_json(f"jobs/{reconstruction['id']}/results/{output_id}/0")
        self.assertEqual(item, reconstruction_results["outputs"][output_id])

        # Convert the fixture model asynchronously and select its result output.
        conversion_id = "roofer:convert_format:v1"
        conversion, conversion_location = self.execute_async(
            conversion_id, {"model_3d_id": 789, "formats": ["cityjson"]}
        )
        self.wait_for_success(conversion_location)
        selected = self.get_json(f"jobs/{conversion['id']}/results?{urlencode({'outputs': 'converted_model'})}")
        self.assertEqual(list(selected["outputs"]), ["converted_model"])
        conversion_item = self.get_json(f"jobs/{conversion['id']}/results/converted_model/0")
        self.assertEqual(conversion_item, selected["outputs"]["converted_model"])

        jobs = self.get_json("jobs")["jobs"]
        listed_ids = {job["id"] for job in jobs}
        self.assertTrue({reconstruction["id"], conversion["id"]}.issubset(listed_ids))


if __name__ == "__main__":
    unittest.main(verbosity=2)
