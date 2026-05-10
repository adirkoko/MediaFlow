# backend/app/models/schemas.py
from enum import Enum
import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.registration import USERNAME_PATTERN
from app.core.users import ALLOWED_USER_ROLES, ALLOWED_USER_STATUSES, USER_STATUS_DELETED
from app.services.download_validation import validate_download_request, validate_youtube_url


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegistrationRequestCreate(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=4, max_length=64)
    email: str | None = Field(default=None, max_length=254)
    message: str | None = Field(default=None, max_length=500)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        clean = value.strip().lower()
        if not USERNAME_PATTERN.fullmatch(clean):
            raise ValueError(
                "Username must use only letters, numbers, dot, underscore, or dash"
            )
        return clean

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip().lower()
        if not clean:
            return None
        if len(clean) > 254 or not re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean):
            raise ValueError("Email is invalid")
        return clean

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None


class RegistrationRequestSubmitResponse(BaseModel):
    status: str = "pending"
    message: str = "Registration request submitted and is pending admin approval."


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


class AdminUserResponse(BaseModel):
    id: str
    username: str
    email: str | None = None
    role: str
    status: str
    token_version: int
    created_at: str
    updated_at: str
    last_login_at: str | None = None
    deleted_at: str | None = None


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    email: str | None = None
    role: str = "user"
    status: str = "active"

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = value.strip().lower()
        if role not in ALLOWED_USER_ROLES:
            raise ValueError("Unsupported user role")
        return role

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        status = value.strip().lower()
        if status not in ALLOWED_USER_STATUSES:
            raise ValueError("Unsupported user status")
        if status == USER_STATUS_DELETED:
            raise ValueError("Users cannot be created directly as deleted")
        return status


class AdminUpdateUserRequest(BaseModel):
    username: str | None = Field(default=None, min_length=1)
    email: str | None = None
    role: str | None = None
    status: str | None = None

    @field_validator("role")
    @classmethod
    def validate_optional_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        role = value.strip().lower()
        if role not in ALLOWED_USER_ROLES:
            raise ValueError("Unsupported user role")
        return role

    @field_validator("status")
    @classmethod
    def validate_optional_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        status = value.strip().lower()
        if status not in ALLOWED_USER_STATUSES:
            raise ValueError("Unsupported user status")
        return status


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1)


class AdminRegistrationRequestResponse(BaseModel):
    id: int
    username: str
    email: str | None = None
    message: str | None = None
    status: str
    requested_at: str
    reviewed_at: str | None = None
    reviewed_by_user_id: str | None = None
    decision_reason: str | None = None
    request_ip_hash: str | None = None
    user_agent: str | None = None
    created_at: str
    updated_at: str


class AdminRejectRegistrationRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None


class QuotaUpdateRequest(BaseModel):
    max_active_jobs: int | None = None
    max_jobs_per_day: int | None = None
    max_jobs_per_week: int | None = None
    max_jobs_per_month: int | None = None
    max_credits_per_day: int | None = None
    max_credits_per_week: int | None = None
    max_credits_per_month: int | None = None
    max_playlist_items_per_job: int | None = None
    max_playlist_items_per_day: int | None = None
    max_video_duration_seconds: int | None = None
    max_video_quality: str | None = None
    max_output_mb_per_day: int | None = None
    max_output_mb_per_month: int | None = None

    @field_validator("max_video_quality")
    @classmethod
    def validate_video_quality(cls, value: str | None) -> str | None:
        if value is None:
            return None
        quality = value.strip().lower()
        if quality.isdigit():
            quality = f"{quality}p"
        allowed = {"best", "144p", "240p", "360p", "480p", "720p", "1080p", "1440p", "2160p"}
        if quality not in allowed:
            raise ValueError("Unsupported video quality")
        return quality


class RoleQuotaResponse(BaseModel):
    role: str
    quota: dict
    created_at: str | None = None
    updated_at: str | None = None


class UserQuotaResponse(BaseModel):
    user_id: str
    role: str
    effective_quota: dict
    override_quota: dict | None = None


class UsageSummaryResponse(BaseModel):
    range: str
    summary: dict




