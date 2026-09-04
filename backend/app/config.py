from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/job_radar.db"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-luna"
    scan_interval_seconds: int = 600
    # Backward-compatible environment setting; seconds is the active control.
    scan_interval_minutes: int = 10
    request_timeout_seconds: int = 60
    cors_origins: str = "http://localhost:3000"
    seed_demo_jobs: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    alert_from: str = ""
    alert_to: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
