#!/usr/bin/env bash
# Start the API, then run: bash test/ogcapi_e2e.sh

API=http://localhost:8000/ogcapi
AUTH='Authorization: Bearer ogcapi-e2e-example'

# Discover the API and its processes.
curl -i -H "$AUTH" "$API/"
curl -i -H "$AUTH" "$API/conformance"
curl -i -H "$AUTH" "$API/openapi.json"
curl -i -H "$AUTH" "$API/processes"
curl -i -H "$AUTH" "$API/processes/roofer%3Avalidate_point_cloud%3Av1"
curl -i -H "$AUTH" "$API/processes/roofer%3Areconstruct_buildings%3Av1"
curl -i -H "$AUTH" "$API/processes/roofer%3Aconvert_format%3Av1"

# Validate a point cloud.
curl -i -H "$AUTH" -H 'Prefer: respond-sync' -H 'Content-Type: application/json' \
  -d '{"inputs":{"point_clouds":[{"kind":"asset","asset_id":123}]}}' \
  "$API/processes/roofer%3Avalidate_point_cloud%3Av1/execution"

# Start a reconstruction job. Copy the job URL and ID from the response below.
curl -i -H "$AUTH" -H 'Prefer: respond-async' -H 'Content-Type: application/json' \
  -d '{"inputs":{"point_cloud_ids":[123],"bag":{"kind":"asset","asset_id":2}}}' \
  "$API/processes/roofer%3Areconstruct_buildings%3Av1/execution"

# Replace JOB_URL and JOB_ID with values from the response. Run these after the job completes.
curl -i -H "$AUTH" 'JOB_URL'
curl -i -H "$AUTH" "$API/jobs/JOB_ID"
curl -i -H "$AUTH" "$API/jobs/JOB_ID/results"
curl -i -H "$AUTH" "$API/jobs/JOB_ID/results/building_model/0"

# Start a format conversion job.
curl -i -H "$AUTH" -H 'Prefer: respond-async' -H 'Content-Type: application/json' \
  -d '{"inputs":{"model_3d_id":789,"formats":["cityjson"]}}' \
  "$API/processes/roofer%3Aconvert_format%3Av1/execution"

# Replace JOB_ID with the conversion job ID. Run these after it completes.
curl -i -H "$AUTH" "$API/jobs/JOB_ID/results?outputs=converted_model"
curl -i -H "$AUTH" "$API/jobs/JOB_ID/results/converted_model/0"
curl -i -H "$AUTH" "$API/jobs"
