from pathlib import Path

from aidp_server.config import Settings, ensure_app_data_dir


def test_default_app_data_directory_is_runtime_data() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_data_dir == Path("./runtime-data")


def test_app_data_directory_and_default_database_url_use_configured_path(tmp_path: Path) -> None:
    app_data_dir = tmp_path / "app-data"
    settings = Settings(_env_file=None, app_data_dir=app_data_dir, database_url=None)

    created_path = ensure_app_data_dir(settings)

    assert created_path == app_data_dir.resolve()
    assert created_path.is_dir()
    assert (
        settings.database_url_resolved == f"sqlite:///{(created_path / 'aidev.sqlite3').as_posix()}"
    )
