from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "MediaFlow Backend"
    env: str = "dev"
    cors_origins: str

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
    dedup_window_minutes: int = 60  # within this window, same request reuses existing job

    # Backoff
    max_attempts: int = 4
    backoff_base_seconds: float = 2.0
    ytdlp_retries: int = 0
    ytdlp_fragment_retries: int = 0
    ytdlp_extractor_retries: int = 0

    # Optional cookies (for legit authenticated access)
    cookies_file: str | None = None  # set in .env as an absolute path

settings = Settings()
