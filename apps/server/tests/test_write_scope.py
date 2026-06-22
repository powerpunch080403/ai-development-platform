from pathlib import Path

import pytest

from aidp_server.db.models import GitWorktree, Task, TaskAttempt
from conftest import AppHarness
from test_worktrees import auth, git, repo


def create_task(
    harness: AppHarness,
    project_id: str,
    repository_id: str | None = None,
    *,
    write_scope: dict[str, object] | None = None,
    instructions: str = "Scoped task",
    worker_kind: str = "manual",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Write scope task",
        "instructions": instructions,
        "repository_id": repository_id,
        "risk_level": "R1",
        "requested_worker_kind": worker_kind,
    }
    if write_scope is not None:
        payload["write_scope"] = write_scope
    response = harness.client.post(f"/projects/{project_id}/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def setup_worktree(
    harness: AppHarness,
    tmp_path: Path,
    *,
    write_scope: dict[str, object],
    worker_kind: str = "manual",
    instructions: str = "Scoped task",
) -> tuple[Path, dict[str, object], dict[str, object], dict[str, object]]:
    source = repo(tmp_path / f"scope-{worker_kind}-{len(list(tmp_path.iterdir()))}")
    project = harness.client.post("/projects", json={"name": "Scope Project"}).json()
    repository = harness.client.post(
        f"/projects/{project['id']}/repositories",
        json={"repository_path": str(source), "repository_role": "primary"},
    ).json()
    task = create_task(
        harness,
        str(project["id"]),
        str(repository["id"]),
        write_scope=write_scope,
        instructions=instructions,
        worker_kind=worker_kind,
    )
    attempt = harness.client.post(f"/tasks/{task['id']}/attempts", json={}).json()
    worker = harness.client.post(
        "/workers",
        json={"display_name": f"Scope {worker_kind}", "worker_kind": worker_kind},
    ).json()
    claim = harness.client.post(
        f"/workers/{worker['id']}/claim", json={"task_attempt_id": attempt["id"]}
    )
    assert claim.status_code == 200, claim.text
    worktree = harness.client.post(f"/task-attempts/{attempt['id']}/worktree", json={})
    assert worktree.status_code == 201, worktree.text
    return source, task, attempt, worktree.json()


def test_task_write_scope_defaults_and_round_trips(app_harness: AppHarness) -> None:
    auth(app_harness)
    project = app_harness.client.post("/projects", json={"name": "Defaults"}).json()
    default_task = create_task(app_harness, str(project["id"]))
    assert default_task["write_scope"] == {
        "mode": "paths",
        "paths": ["."],
        "allow_new_files": True,
    }
    scoped_task = create_task(
        app_harness,
        str(project["id"]),
        write_scope={"mode": "paths", "paths": ["README.md"], "allow_new_files": False},
    )
    assert scoped_task["write_scope"] == {
        "mode": "paths",
        "paths": ["README.md"],
        "allow_new_files": False,
    }


@pytest.mark.parametrize(
    "scope",
    [
        {"mode": "paths", "paths": ["C:\\temp\\file.txt"], "allow_new_files": True},
        {"mode": "paths", "paths": ["../outside.txt"], "allow_new_files": True},
        {"mode": "paths", "paths": [], "allow_new_files": True},
    ],
)
def test_invalid_write_scope_is_rejected(app_harness: AppHarness, scope: dict[str, object]) -> None:
    auth(app_harness)
    project = app_harness.client.post("/projects", json={"name": "Invalid"}).json()
    response = app_harness.client.post(
        f"/projects/{project['id']}/tasks",
        json={
            "title": "Invalid scope",
            "instructions": "No write",
            "risk_level": "R1",
            "write_scope": scope,
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "WRITE_SCOPE_INVALID"


def test_raw_commit_allows_scoped_existing_file(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    _, _, _, worktree = setup_worktree(
        app_harness,
        tmp_path,
        write_scope={"mode": "paths", "paths": ["README.md"], "allow_new_files": False},
    )
    path = Path(str(worktree["worktree_path"]))
    (path / "README.md").write_text("# Allowed\n", encoding="utf-8")
    response = app_harness.client.post(
        f"/worktrees/{worktree['id']}/commit-result", json={"commit_message": "docs: allowed"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["result_commit_sha"]


def test_raw_commit_blocks_outside_scope_without_state_change(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    auth(app_harness)
    _, task, attempt, worktree = setup_worktree(
        app_harness,
        tmp_path,
        write_scope={"mode": "paths", "paths": ["README.md"], "allow_new_files": True},
    )
    path = Path(str(worktree["worktree_path"]))
    head_before = git(path, "rev-parse", "HEAD")
    (path / "docs").mkdir()
    (path / "docs" / "outside.md").write_text("outside", encoding="utf-8")
    response = app_harness.client.post(
        f"/worktrees/{worktree['id']}/commit-result", json={"commit_message": "bad"}
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "WRITE_SCOPE_VIOLATION"
    assert git(path, "rev-parse", "HEAD") == head_before
    with app_harness.session_factory() as session:
        stored_attempt = session.get(TaskAttempt, str(attempt["id"]))
        stored_task = session.get(Task, str(task["id"]))
        stored_worktree = session.get(GitWorktree, str(worktree["id"]))
        assert stored_attempt is not None and stored_attempt.status.value == "running_worker"
        assert stored_task is not None and stored_task.status.value == "running"
        assert stored_worktree is not None and stored_worktree.result_commit_sha is None


def test_raw_commit_blocks_new_file_when_disallowed(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    auth(app_harness)
    _, _, _, worktree = setup_worktree(
        app_harness,
        tmp_path,
        write_scope={"mode": "paths", "paths": ["src/"], "allow_new_files": False},
    )
    path = Path(str(worktree["worktree_path"]))
    (path / "src").mkdir()
    (path / "src" / "new.py").write_text("print('new')\n", encoding="utf-8")
    response = app_harness.client.post(
        f"/worktrees/{worktree['id']}/commit-result", json={"commit_message": "bad new file"}
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["paths"] == ["src/new.py"]


def test_mock_worker_blocks_path_outside_scope(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    _, _, attempt, worktree = setup_worktree(
        app_harness,
        tmp_path,
        write_scope={"mode": "paths", "paths": ["README.md"], "allow_new_files": True},
        worker_kind="mock",
        instructions="MOCK_APPEND docs/outside.md: blocked",
    )
    response = app_harness.client.post(f"/task-attempts/{attempt['id']}/run-mock-worker", json={})
    assert response.status_code == 200, response.text
    assert response.json()["worker_run"]["status"] == "failed"
    assert not (Path(str(worktree["worktree_path"])) / "docs" / "outside.md").exists()


def test_manual_submit_blocks_path_outside_scope(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    _, _, attempt, worktree = setup_worktree(
        app_harness,
        tmp_path,
        write_scope={"mode": "paths", "paths": ["README.md"], "allow_new_files": True},
    )
    started = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/manual-worker/start", json={}
    )
    assert started.status_code == 200, started.text
    path = Path(str(worktree["worktree_path"]))
    (path / "outside.txt").write_text("blocked", encoding="utf-8")
    response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/manual-worker/submit", json={}
    )
    assert response.status_code == 409, response.text
    assert "write_scope" in response.json()["detail"]
    assert git(path, "status", "--porcelain") == "?? outside.txt"


def test_external_cli_context_contains_write_scope(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    _, _, attempt, _ = setup_worktree(
        app_harness,
        tmp_path,
        write_scope={"mode": "paths", "paths": ["README.md"], "allow_new_files": False},
        worker_kind="external_cli",
    )
    response = app_harness.client.get(f"/task-attempts/{attempt['id']}/external-cli/context")
    assert response.status_code == 200, response.text
    assert response.json()["write_scope"] == {
        "mode": "paths",
        "paths": ["README.md"],
        "allow_new_files": False,
    }
    assert "Only modify files within the declared write_scope." in response.json()["constraints"]
