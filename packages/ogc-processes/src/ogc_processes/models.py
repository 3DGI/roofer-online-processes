"""OGC API - Processes Part 1 version 2 resource models."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobControlOption(str, Enum):
    """Execution modes advertised by a process."""

    execute_async = "execute-async"
    execute_sync = "execute-sync"


class TransmissionMode(str, Enum):
    """Ways in which a process can return outputs."""

    value = "value"
    reference = "reference"


class ResponseType(str, Enum):
    """Requested response document format."""

    document = "document"
    raw = "raw"


class StatusCode(str, Enum):
    """OGC job status values."""

    accepted = "accepted"
    running = "running"
    successful = "successful"
    failed = "failed"


class Link(BaseModel):
    """A hypermedia link in an OGC resource."""

    href: str
    rel: str
    type: str | None = None
    title: str | None = None


class LandingPage(BaseModel):
    """OGC API landing page."""

    title: str | None = None
    description: str | None = None
    links: list[Link]


class Conformance(BaseModel):
    """Conformance classes implemented by the service."""

    conformsTo: list[str]


class InputDescription(BaseModel):
    """Description of one process input."""

    title: str | None = None
    description: str | None = None
    schema_: dict[str, Any] = Field(alias="schema")
    minOccurs: int = Field(0, ge=0)
    maxOccurs: int | str = "unbounded"

    model_config = {"populate_by_name": True}


class OutputDescription(BaseModel):
    """Description of one process output."""

    title: str | None = None
    description: str | None = None
    schema_: dict[str, Any] = Field(alias="schema")

    model_config = {"populate_by_name": True}


class ProcessSummary(BaseModel):
    """Summary shown in the process collection."""

    id: str
    title: str
    description: str
    version: str
    keywords: list[str] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)


class ProcessDescription(ProcessSummary):
    """Complete process description."""

    inputs: dict[str, InputDescription]
    outputs: dict[str, OutputDescription]
    jobControlOptions: list[JobControlOption]
    outputTransmission: list[TransmissionMode]


class ProcessList(BaseModel):
    """Process collection response."""

    processes: list[ProcessSummary]
    links: list[Link] = Field(default_factory=list)


class ExecuteRequest(BaseModel):
    """Execution request accepted by the Core endpoint."""

    inputs: dict[str, Any] = Field(default_factory=dict)
    response: ResponseType | None = None
    subscriber: dict[str, Any] | None = None


class JobStatus(BaseModel):
    """OGC API Processes 2.0 job resource."""

    id: str
    processID: str
    processingEntityType: Literal["ogc-api-processes"] = "ogc-api-processes"
    status: StatusCode
    message: str | None = None
    created: datetime
    started: datetime | None = None
    finished: datetime | None = None
    updated: datetime | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    links: list[Link] = Field(default_factory=list)


class JobList(BaseModel):
    """Job collection response."""

    jobs: list[JobStatus]
    links: list[Link] = Field(default_factory=list)


class Results(BaseModel):
    """Results of a completed job."""

    outputs: dict[str, Any]
    links: list[Link] = Field(default_factory=list)


class ExceptionReport(BaseModel):
    """RFC 7807 problem details response."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
