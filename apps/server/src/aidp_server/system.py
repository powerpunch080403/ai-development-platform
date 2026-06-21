from pathlib import Path
from typing import Annotated, TypedDict

from fastapi import APIRouter, Depends
from sqlalchemy import make_url, text

from aidp_server.config import Settings, ensure_app_data_dir, get_settings
from aidp_server.db.session import create_engine_from_settings


class DatabaseStatus(TypedDict):
    url: str
    reachable: bool


class SystemStatus(TypedDict):
    service: str
    status: str
    environment: str
    app_data_dir: str
    database: DatabaseStatus


router = APIRouter(prefix="/system", tags=["system"])


def display_database_url(settings: Settings) -> str:
    url = make_url(settings.database_url_resolved)
    if url.drivername.startswith("sqlite"):
        if url.database is None or url.database in {"", ":memory:"}:
            return "sqlite:///:memory:"
        return f"sqlite:///<app-data-dir>/{Path(url.database).name}"
    return url.render_as_string(hide_password=True)


@router.get("/status")
def get_system_status(settings: Annotated[Settings, Depends(get_settings)]) -> SystemStatus:
    app_data_dir = ensure_app_data_dir(settings)
    engine = create_engine_from_settings(settings)
    reachable = False
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        reachable = True
    finally:
        engine.dispose()

    return {
        "service": "aidp-server",
        "status": "ok",
        "environment": settings.env,
        "app_data_dir": app_data_dir.name,
        "database": {
            "url": display_database_url(settings),
            "reachable": reachable,
        },
    }
