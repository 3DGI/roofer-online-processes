"""Run the OGC API - Processes 1.0 ETS hosted by the local TEAM Engine container."""

from __future__ import annotations

import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

TEAM_ENGINE_URL = os.environ.get("TEAM_ENGINE_URL", "http://localhost:8080/teamengine")
IUT_URL = os.environ.get("OGC_IUT_URL", "http://localhost:8000/ogcapi/")
ETS_CODE = "ogcapi-processes-1.0"
ETS_VERSION = "1.3"
REPORT = Path("artifacts/ogc-processes-ets.xml")


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    endpoint = f"{TEAM_ENGINE_URL}/rest/suites/{ETS_CODE}/{ETS_VERSION}/run?" + urllib.parse.urlencode(
        {"iut": IUT_URL, "echoprocessid": "echo"}
    )
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(None, TEAM_ENGINE_URL, "ogctest", "ogctest")
    opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_mgr))
    request = urllib.request.Request(endpoint, headers={"Accept": "application/rdf+xml"})

    try:
        with opener.open(request, timeout=600) as response:
            report = response.read()
    except Exception as exc:  # surfaced in Actions log with endpoint context
        print(f"TEAM Engine ETS request failed: {exc}", file=sys.stderr)
        return 1

    REPORT.write_bytes(report)
    try:
        root = ET.fromstring(report)
    except ET.ParseError as exc:
        print(f"TEAM Engine returned an unreadable report: {exc}", file=sys.stderr)
        return 1

    failed = [
        value
        for element in root.iter()
        for key, value in element.attrib.items()
        if key.endswith("}resource") and value.rstrip("/").endswith("#failed")
    ]
    if failed:
        print(f"OGC API - Processes ETS reported {len(failed)} failed test result(s).")
        print(f"Full EARL report: {REPORT}")
        return 1

    print(f"OGC API - Processes ETS completed without failed outcomes. Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
