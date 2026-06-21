from pathlib import Path

from fastapi.testclient import TestClient

from aidp_server.config import Settings, get_settings
from aidp_server.main import app


def test_system_status_reports_reachable_database_without_exposing_full_path(
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        app_data_dir=tmp_path / "app-data",
        database_url=None,
    )
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        response = TestClient(app).get("/system/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "service": "aidp-server",
        "status": "ok",
        "environment": "test",
        "app_data_dir": "app-data",
        "database": {
            "url": "sqlite:///<app-data-dir>/aidev.sqlite3",
            "reachable": True,
        },
    }
