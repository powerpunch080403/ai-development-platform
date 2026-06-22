from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from aidp_server.config import get_settings


def test_initial_migration_upgrades_and_downgrades_temporary_sqlite(
    tmp_path: Path, monkeypatch: object
) -> None:
    database_path = tmp_path / "migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    server_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(server_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(server_root / "migrations"))

    monkeypatch.setenv("AIDP_APP_DATA_DIR", str(tmp_path / "app-data"))  # type: ignore[attr-defined]
    monkeypatch.setenv("AIDP_DATABASE_URL", database_url)  # type: ignore[attr-defined]
    get_settings.cache_clear()

    try:
        command.upgrade(alembic_config, "head")
        engine = create_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

        assert {
            "alembic_version",
            "local_users",
            "devices",
            "sessions",
            "pairing_codes",
            "projects",
            "project_repositories",
            "conversations",
            "messages",
            "agent_runs",
            "agent_run_steps",
            "tool_registry",
            "tool_calls",
            "audit_events",
        }.issubset(table_names)

        command.downgrade(alembic_config, "base")
    finally:
        get_settings.cache_clear()
