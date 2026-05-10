from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "MediaFlow Backend"
    env: str = "dev"
    cors_origins: str | None = None

    # Auth
    jwt_secret: str = "CHANGE_ME"
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 60

    # Paths
    users_file: str = "data/users.json"
    db_path: str = "data/app.sqlite"
    outputs_dir: str = "outputs"

    # Load / concurrency control
    max_parallel_jobs: int = 2
    queue_max_size: int = 50

    # Output cleanup
    outputs_ttl_hours: int = 24
    outputs_ttl_minutes: int | None = None
    outputs_cleanup_interval_minutes: int = 60

    # Metadata embedding
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    thumbnail_convert_format: str = "jpg"  # "jpg" is recommended for compatibility

    # Quota & dedup
    max_active_jobs_per_user: int = 2
    dedup_window_minutes: int = (
        60  # within this window, same request reuses existing job
    )

    # Login protection
    login_max_failed_per_username: int = 5
    login_max_failed_per_ip: int = 20
    login_window_minutes: int = 10
    login_block_minutes: int = 15

    # Lightweight job endpoint rate limits (per process in this phase)
    job_create_rate_limit_per_minute: int = 20
    job_preview_rate_limit_per_minute: int = 30

    # Controlled access request flow
    registration_requests_enabled: bool = True
    registration_rate_limit_per_ip_per_hour: int = 5
    registration_rate_limit_per_ip_per_day: int = 20
    registration_max_pending_per_ip: int = 3
    registration_message_max_length: int = 500

    # Backoff
    max_attempts: int = 4
    backoff_base_seconds: float = 2.0
    ytdlp_retries: int = 0
    ytdlp_fragment_retries: int = 0
    ytdlp_extractor_retries: int = 0
    node_path: str | None = None
    ytdlp_remote_components: str | None = None

    # Optional cookies (for legit authenticated access)
    cookies_file: str | None = None  # set in .env as an absolute path

    @field_validator("outputs_ttl_minutes", mode="before")
    @classmethod
    def parse_outputs_ttl_minutes(cls, value: object) -> object:
        # Allow empty env value (e.g. OUTPUTS_TTL_MINUTES=) to behave like "not set".
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator(
        "cookies_file",
        "node_path",
        "ytdlp_remote_components",
        mode="before",
    )
    @classmethod
    def parse_optional_strings(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


settings = Settings()
