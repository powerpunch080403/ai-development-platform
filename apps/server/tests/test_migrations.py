from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from aidp_server.config import get_settings


def _alembic_config() -> Config:
    server_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(server_root / "alembic.ini")
    alembic_config.set_main_option("script_location", str(server_root / "migrations"))
    return alembic_config


def test_alembic_has_single_head() -> None:
    script = ScriptDirectory.from_config(_alembic_config())

    assert script.get_heads() == ["20260624_0012"]


def test_initial_migration_upgrades_and_downgrades_temporary_sqlite(
    tmp_path: Path, monkeypatch: object
) -> None:
    database_path = tmp_path / "migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    alembic_config = _alembic_config()

    monkeypatch.setenv("AIDP_APP_DATA_DIR", str(tmp_path / "app-data"))  # type: ignore[attr-defined]
    monkeypatch.setenv("AIDP_DATABASE_URL", database_url)  # type: ignore[attr-defined]
    get_settings.cache_clear()

    try:
        command.upgrade(alembic_config, "head")
        engine = create_engine(database_url)
        try:
            inspector = inspect(engine)
            table_names = set(inspector.get_table_names())
            task_columns = {column["name"] for column in inspector.get_columns("tasks")}
            tool_call_columns = {column["name"] for column in inspector.get_columns("tool_calls")}
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
            "work_items",
            "tasks",
            "task_attempts",
            "workers",
            "git_worktrees",
            "artifact_refs",
            "merge_reviews",
            "task_work_room_messages",
        }.issubset(table_names)
        assert "write_scope_json" in task_columns
        assert "result_json" in tool_call_columns

        command.downgrade(alembic_config, "base")
    finally:
        get_settings.cache_clear()
