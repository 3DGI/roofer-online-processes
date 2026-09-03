"""Dependency-injection interfaces for the OGC protocol layer."""

from datetime import datetime
from typing import Any, Protocol

from .models import (
    JobControlOption,
    JobStatus,
    ProcessDescription,
    ProcessSummary,
    Results,
    StatusCode,
)


class Principal(Protocol):
    """Authenticated caller supplied by the host application."""

    @property
    def subject(self) -> str: ...


class Authenticator(Protocol):
    """Host authentication boundary."""

    def authenticate(self, authorization: str | None) -> Principal: ...


class ProcessCatalog(Protocol):
    """Source of public process metadata."""

    def list_processes(self) -> list[ProcessSummary]: ...

    def get_process(self, process_id: str) -> ProcessDescription | None: ...


class Submission(Protocol):
    """Result of submitting work to a host workflow engine."""

    @property
    def upstream_id(self) -> str: ...

    @property
    def status(self) -> StatusCode: ...

    @property
    def message(self) -> str | None: ...


class ExecutionBackend(Protocol):
    """Host-specific execution and status boundary."""

    def submit(
        self,
        process_id: str,
        inputs: dict[str, Any],
        subject: str,
        mode: JobControlOption,
    ) -> Submission: ...

    def status(
        self, upstream_id: str, subject: str
    ) -> tuple[
        StatusCode, str | None, int | None, datetime | None, datetime | None
    ]: ...

    def results(self, upstream_id: str, subject: str) -> Results | None: ...

    def dismiss(self, upstream_id: str, subject: str) -> bool: ...


class JobStore(Protocol):
    """Persistence boundary for public OGC job resources."""

    def create(self, job: JobStatus, upstream_id: str, subject: str) -> None: ...

    def get(self, job_id: str, subject: str) -> tuple[JobStatus, str] | None: ...

    def list(self, subject: str) -> list[tuple[JobStatus, str]]: ...

    def update(self, job: JobStatus) -> None: ...
