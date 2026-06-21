from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Minimal local runtime configuration loaded from AIDP_* variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AIDP_",
        extra="ignore",
    )

    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    app_data_dir: Path = Path("./runtime-data")
    database_url: str = "sqlite:///./runtime-data/aidev.sqlite3"
    web_origin: str = "http://localhost:5173"


settings = Settings()
