# backend/app/models/schemas.py
from enum import Enum
from pydantic import BaseModel, Field, model_validator

from app.services.download_validation import validate_download_request, validate_youtube_url


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
    canceled = "canceled"
    succeeded = "succeeded"
    failed = "failed"


class CreateJobRequest(BaseModel):
    url: str = Field(min_length=5)
    mode: MediaMode
    quality: str = Field(default="best", min_length=1)

    @model_validator(mode="after")
    def validate_download_options(self) -> "CreateJobRequest":
        opts = validate_download_request(
            url=self.url,
            mode=self.mode.value,
            quality=self.quality,
        )
        self.url = opts.url
        self.quality = opts.quality
        return self


class PreviewRequest(BaseModel):
    url: str = Field(min_length=5)

    @model_validator(mode="after")
    def validate_url(self) -> "PreviewRequest":
        self.url = validate_youtube_url(self.url)
        return self


class VideoQualityPreviewResponse(BaseModel):
    quality: str
    height: int | None = None
    ext: str | None = None
    filesize_bytes: int | None = None
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None


class PreviewResponse(BaseModel):
    url: str
    webpage_url: str | None = None
    title: str
    thumbnail: str | None = None
    uploader: str | None = None
    duration_seconds: int | None = None
    is_playlist: bool
    playlist_count: int | None = None
    audio_ext: str | None = None
    audio_filesize_bytes: int | None = None
    video_qualities: list[VideoQualityPreviewResponse] = Field(default_factory=list)


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    reused: bool = False


class CancelJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    cancel_requested: bool = True


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
    progress_percent: int | None = None
    stage: str | None = None
    updated_at: str | None = None
    eta_seconds: int | None = None
    speed_bps: int | None = None
    playlist_total: int | None = None
    playlist_succeeded: int | None = None
    playlist_failed: int | None = None




