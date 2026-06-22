from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "processing", "succeeded", "failed", "cancelled"]


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    poll_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    trace_id: str | None = None


class JobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    result: dict | None = None
    error_message: str | None = None
