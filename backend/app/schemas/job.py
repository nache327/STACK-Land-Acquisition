import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.job import JobStatus

TargetUse = Literal["self_storage", "mini_warehouse", "light_industrial", "luxury_garage_condo"]

ALL_USES: list[TargetUse] = [
    "self_storage",
    "mini_warehouse",
    "light_industrial",
    "luxury_garage_condo",
]


class JobCreate(BaseModel):
    """POST /api/jobs body."""
    # Either a city name ("Draper, UT") or an ArcGIS map URL
    jurisdiction: str = Field(..., min_length=2, max_length=512)
    # URL to Municode / eCode360 / city website — OR omit if uploading PDF
    ordinance_url: str | None = Field(None, max_length=1024)
    target_uses: list[TargetUse] = Field(default_factory=lambda: list(ALL_USES))
    force: bool = False


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    jurisdiction_id: uuid.UUID | None
    status: JobStatus
    jurisdiction_input: str | None
    ordinance_url: str | None
    target_uses: list[str] | None
    error_message: str | None
    progress: dict | None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    force: bool = False
    dedupe_key: str | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    attempts: int = 0
    created_at: datetime
    updated_at: datetime


class JobStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: uuid.UUID | None
    step: str
    status: str
    attempt: int
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None
    step_metadata: dict | None
    created_at: datetime
    updated_at: datetime


class JobArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: uuid.UUID
    step: str
    artifact_type: str
    artifact_metadata: dict | None
    storage_uri: str | None
    created_at: datetime


class JobAdminRead(BaseModel):
    job: JobRead
    steps: list[JobStepRead]
    artifacts: list[JobArtifactRead]
