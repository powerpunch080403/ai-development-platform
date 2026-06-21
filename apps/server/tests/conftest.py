from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from aidp_server.config import Settings, get_settings
from aidp_server.db.base import Base
from aidp_server.db.session import get_session
from aidp_server.main import app


@dataclass
class AppHarness:
    client: TestClient
    session_factory: sessionmaker[Session]
    settings: Settings


@pytest.fixture
def app_harness(tmp_path: Path) -> Generator[AppHarness, None, None]:
    database_path = tmp_path / "test.sqlite3"
    engine: Engine = create_engine(
        f"sqlite:///{database_path.as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="test",
        app_data_dir=tmp_path,
        database_url=f"sqlite:///{database_path.as_posix()}",
    )

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            yield AppHarness(client=client, session_factory=factory, settings=settings)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
