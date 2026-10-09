from datetime import UTC, datetime, timedelta

import pytest
from ogc_processes.models import JobStatus, StatusCode
from ogc_processes.router import duration_matches


def make_job(
    *,
    status: StatusCode,
    started: datetime | None,
    finished: datetime | None = None,
) -> JobStatus:
    now = datetime.now(UTC)
    return JobStatus(
        id="job-1",
        jobID="job-1",
        processingEntityType="ogc-api-processes",
        processID="https://example.test/processes/reconstruct",
        status=status,
        created=now,
        started=started,
        finished=finished,
    )


@pytest.mark.parametrize(
    ("minimum", "maximum", "expected"),
    [
        (60, None, True),
        (None, 60, False),
        (60, 180, True),
    ],
)
def test_running_job_duration_uses_elapsed_time(
    minimum: int | None,
    maximum: int | None,
    expected: bool,
) -> None:
    started = datetime.now(UTC) - timedelta(minutes=2)
    job = make_job(status=StatusCode.running, started=started)

    assert duration_matches(job, minimum, maximum) is expected


def test_completed_job_duration_uses_finished_time() -> None:
    started = datetime.now(UTC) - timedelta(minutes=2)
    finished = started + timedelta(minutes=1)
    job = make_job(status=StatusCode.successful, started=started, finished=finished)

    assert duration_matches(job, 50, 70)


def test_accepted_job_has_no_runtime_duration() -> None:
    job = make_job(status=StatusCode.accepted, started=None)

    assert not duration_matches(job, 0, 60)
