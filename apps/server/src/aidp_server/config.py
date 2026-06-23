from functools import lru_cache
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
    database_url: str | None = None
    web_origin: str = "http://localhost:5173"
    session_cookie_name: str = "aidp_session"
    
    enable_experimental_antigravity_cli: bool = False
    antigravity_cli_path: str | None = None
    antigravity_cli_timeout_seconds: int = 300
    antigravity_cli_allow_dangerous_skip_permissions: bool = False

    allow_real_codex_owner_provider: bool = False
    codex_cli_command: str = "codex"
    codex_cli_timeout_seconds: int = 120

    allow_fake_owner_provider: bool = False

    @property
    def session_cookie_secure(self) -> bool:
        return self.env.lower() == "production"

    @property
    def app_data_dir_path(self) -> Path:
        return self.app_data_dir.expanduser().resolve()

    @property
    def database_url_resolved(self) -> str:
        if self.database_url:
            return self.database_url

        database_path = (self.app_data_dir_path / "aidev.sqlite3").as_posix()
        return f"sqlite:///{database_path}"

    @property
    def worktrees_dir_path(self) -> Path:
        return (self.app_data_dir_path / "worktrees").resolve()

    @property
    def artifacts_dir_path(self) -> Path:
        return (self.app_data_dir_path / "artifacts").resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_app_data_dir(settings: Settings | None = None) -> Path:
    resolved_settings = settings or get_settings()
    app_data_dir = resolved_settings.app_data_dir_path
    app_data_dir.mkdir(parents=True, exist_ok=True)
    return app_data_dir


def ensure_runtime_dirs(settings: Settings | None = None) -> tuple[Path, Path]:
    resolved = settings or get_settings()
    ensure_app_data_dir(resolved)
    resolved.worktrees_dir_path.mkdir(parents=True, exist_ok=True)
    resolved.artifacts_dir_path.mkdir(parents=True, exist_ok=True)
    return resolved.worktrees_dir_path, resolved.artifacts_dir_path
