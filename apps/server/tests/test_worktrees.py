from pathlib import Path
import subprocess
from aidp_server.cli import create_pairing_code
from aidp_server.db.models import GitWorktree, Task, TaskAttempt
from conftest import AppHarness


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True, timeout=10
    ).stdout.strip()


def repo(path: Path) -> Path:
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("# Base\n", encoding="utf-8")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "initial")
    return path


def auth(h: AppHarness) -> None:
    with h.session_factory() as s:
        code, _ = create_pairing_code(s)
    assert (
        h.client.post(
            "/auth/pair", json={"code": code, "device_name": "WT", "device_type": "web_ui"}
        ).status_code
        == 200
    )


def setup(h: AppHarness, path: Path) -> tuple[dict[str, object], str]:
    p = h.client.post("/projects", json={"name": "WT Project"}).json()
    r = h.client.post(
        f"/projects/{p['id']}/repositories",
        json={"repository_path": str(path), "repository_role": "primary"},
    ).json()
    t = h.client.post(
        f"/projects/{p['id']}/tasks",
        json={
            "repository_id": r["id"],
            "title": "Edit",
            "instructions": "Manual",
            "risk_level": "R1",
            "requested_worker_kind": "manual",
        },
    ).json()
    a = h.client.post(f"/tasks/{t['id']}/attempts", json={}).json()
    w = h.client.post("/workers", json={"display_name": "Manual", "worker_kind": "manual"}).json()
    assert (
        h.client.post(f"/workers/{w['id']}/claim", json={"task_attempt_id": a["id"]}).status_code
        == 200
    )
    return a, str(t["id"])


def test_worktree_api_requires_auth(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/worktrees/x").status_code == 401


def test_dirty_block_create_commit_and_artifacts(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    source = repo(tmp_path / "source")
    base = git(source, "rev-parse", "main")
    attempt, task_id = setup(app_harness, source)
    aid = str(attempt["id"])
    (source / "dirty.txt").write_text("dirty", encoding="utf-8")
    assert app_harness.client.post(f"/task-attempts/{aid}/worktree").status_code == 409
    (source / "dirty.txt").unlink()
    created = app_harness.client.post(f"/task-attempts/{aid}/worktree")
    assert created.status_code == 201
    wt = created.json()
    assert wt["branch_name"].startswith(f"aidp/task-{task_id[:8]}/attempt-1-")
    assert app_harness.client.post(f"/task-attempts/{aid}/worktree").status_code == 409
    path = Path(wt["worktree_path"])
    assert path.is_dir()
    assert (
        app_harness.client.post(
            f"/worktrees/{wt['id']}/commit-result", json={"commit_message": "manual result"}
        ).status_code
        == 409
    )
    (path / "README.md").write_text("# Changed\n", encoding="utf-8")
    status = app_harness.client.get(f"/worktrees/{wt['id']}/status")
    assert status.json()["is_dirty"] is True
    diff = app_harness.client.get(f"/worktrees/{wt['id']}/diff")
    assert "Changed" in diff.json()["diff"]
    committed = app_harness.client.post(
        f"/worktrees/{wt['id']}/commit-result", json={"commit_message": "chore: manual result"}
    )
    assert committed.status_code == 200 and committed.json()["result_commit_sha"]
    refs = app_harness.client.get(f"/task-attempts/{aid}/artifacts")
    assert {v["kind"] for v in refs.json()} == {"diff_patch", "git_status", "commit_log"}
    text = app_harness.client.get(f"/artifacts/{refs.json()[0]['id']}/text")
    assert text.status_code == 200
    with app_harness.session_factory() as s:
        a = s.get(TaskAttempt, aid)
        t = s.get(Task, task_id)
        w = s.get(GitWorktree, wt["id"])
        assert a and a.status.value == "committed"
        assert t and t.status.value == "waiting_for_review"
        assert w and w.result_commit_sha
    assert git(source, "rev-parse", "main") == base
    assert git(source, "status", "--porcelain") == ""
