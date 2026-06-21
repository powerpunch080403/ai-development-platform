from collections.abc import Generator
from functools import lru_cache

from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from aidp_server.config import Settings, ensure_app_data_dir, get_settings


def create_engine_from_settings(settings: Settings) -> Engine:
    ensure_app_data_dir(settings)
    database_url = settings.database_url_resolved
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@lru_cache
def get_engine() -> Engine:
    return create_engine_from_settings(get_settings())


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    with get_session_factory()() as session:
        yield session


def init_db() -> None:
    """Prepare the app-data directory and verify connectivity.

    Schema creation is intentionally owned by Alembic migrations.
    """

    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
