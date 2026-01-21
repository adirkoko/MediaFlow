from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "MediaFlow Backend"
    env: str = "dev"

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


settings = Settings()
