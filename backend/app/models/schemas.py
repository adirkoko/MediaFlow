from enum import Enum
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    status: str = "ok"


class MediaMode(str, Enum):
    audio = "audio"
    video = "video"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class CreateJobRequest(BaseModel):
    url: str = Field(min_length=5)
    mode: MediaMode
    quality: str = Field(default="best", min_length=1)


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    reused: bool = False


class JobResponse(BaseModel):
    job_id: str
    user: str
    url: str
    mode: MediaMode
    quality: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None
    output_filename: str | None = None
    output_type: str | None = None
    error_code: str | None = None

