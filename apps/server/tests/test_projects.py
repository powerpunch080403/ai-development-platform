from pathlib import Path
import subprocess
from typing import cast

from httpx import Response
from sqlalchemy import select

from aidp_server.cli import create_pairing_code
from aidp_server.db.models import (
    AccountLinkStatus,
    LocalUser,
    Project,
    ProjectRepository,
    ProjectStatus,
)
from conftest import AppHarness


def authenticate(harness: AppHarness) -> None:
    with harness.session_factory() as session:
        code, _ = create_pairing_code(session)
    response = harness.client.post(
        "/auth/pair",
        json={"code": code, "device_name": "Project tests", "device_type": "web_ui"},
    )
    assert response.status_code == 200


def create_project(harness: AppHarness, name: str = "Test Project") -> dict[str, object]:
    response = harness.client.post(
        "/projects", json={"name": name, "description": "Test description"}
    )
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


def run_git(path: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        shell=False,
    )


def make_git_repository(path: Path, branch: str = "main") -> Path:
    path.mkdir()
    run_git(path, "init", "-b", branch)
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("# Test\n", encoding="utf-8")
    run_git(path, "add", "README.md")
    run_git(path, "commit", "-m", "initial")
    return path


def register_repository(
    harness: AppHarness,
    project_id: object,
    repository_path: Path,
    role: str | None = None,
) -> Response:
    payload: dict[str, object] = {"repository_path": str(repository_path)}
    if role is not None:
        payload["repository_role"] = role
    return cast(Response, harness.client.post(f"/projects/{project_id}/repositories", json=payload))


def test_project_api_requires_authentication(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/projects").status_code == 401
    assert app_harness.client.post("/projects", json={"name": "Nope"}).status_code == 401


def test_project_creation_and_list_are_scoped_to_current_user(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    created = create_project(app_harness)
    with app_harness.session_factory() as session:
        other_user = LocalUser(
            display_name="Other",
            account_id=None,
            account_link_status=AccountLinkStatus.LOCAL_ONLY,
        )
        session.add(other_user)
        session.flush()
        session.add(
            Project(local_user_id=other_user.id, name="Other project", status=ProjectStatus.ACTIVE)
        )
        session.commit()

    response = app_harness.client.get("/projects")
    assert response.status_code == 200
    assert [project["id"] for project in response.json()] == [created["id"]]
    assert app_harness.client.get(f"/projects/{created['id']}").status_code == 200


def test_git_repository_registration_normalizes_root_and_detects_clean_status(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    authenticate(app_harness)
    project = create_project(app_harness)
    repository = make_git_repository(tmp_path / "repo")
    nested = repository / "nested"
    nested.mkdir()

    response = register_repository(app_harness, project["id"], nested)
    assert response.status_code == 201
    body = response.json()
    assert body["repository_path"] == str(repository.resolve())
    assert body["repository_role"] == "primary"
    assert body["current_branch"] == "main"
    assert body["default_branch"] == "main"
    assert body["is_dirty"] is False


def test_non_git_and_duplicate_repository_registration_fail(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    authenticate(app_harness)
    project = create_project(app_harness)
    non_git = tmp_path / "not-git"
    non_git.mkdir()
    (non_git / ".git").write_text("not a git directory", encoding="utf-8")
    assert register_repository(app_harness, project["id"], non_git).status_code == 422

    repository = make_git_repository(tmp_path / "repo")
    assert register_repository(app_harness, project["id"], repository).status_code == 201
    assert register_repository(app_harness, project["id"], repository).status_code == 409


def test_project_rejects_second_primary_repository(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    project = create_project(app_harness)
    first = make_git_repository(tmp_path / "first")
    second = make_git_repository(tmp_path / "second")

    assert register_repository(app_harness, project["id"], first, "primary").status_code == 201
    assert register_repository(app_harness, project["id"], second, "primary").status_code == 409
    assert register_repository(app_harness, project["id"], second, "supporting").status_code == 201


def test_refresh_status_updates_dirty_and_clean_database_state(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    authenticate(app_harness)
    project = create_project(app_harness)
    repository_path = make_git_repository(tmp_path / "repo")
    registered = register_repository(app_harness, project["id"], repository_path).json()
    repository_id = registered["id"]
    assert registered["is_dirty"] is False

    dirty_file = repository_path / "untracked.txt"
    dirty_file.write_text("dirty", encoding="utf-8")
    dirty = app_harness.client.post(f"/repositories/{repository_id}/refresh-status")
    assert dirty.status_code == 200
    assert dirty.json()["is_dirty"] is True
    assert "untracked.txt" in dirty.json()["porcelain"]
    with app_harness.session_factory() as session:
        stored = session.scalar(
            select(ProjectRepository).where(ProjectRepository.id == repository_id)
        )
        assert stored is not None and stored.is_dirty is True

    dirty_file.unlink()
    clean = app_harness.client.post(f"/repositories/{repository_id}/refresh-status")
    assert clean.status_code == 200
    assert clean.json()["is_dirty"] is False
    stored_status = app_harness.client.get(f"/repositories/{repository_id}/status")
    assert stored_status.status_code == 200
    assert stored_status.json()["is_dirty"] is False
