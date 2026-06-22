from pathlib import Path

from aidp_server.db.models import GitWorktree, GitWorktreeStatus
from conftest import AppHarness
from test_worktrees import auth, git, repo, setup


def test_cleanup_requires_authentication(app_harness: AppHarness) -> None:
    assert app_harness.client.post("/worktrees/x/cleanup", json={}).status_code == 401
    assert app_harness.client.get("/worktrees/cleanup-pending").status_code == 401


def test_ready_and_outside_paths_cannot_be_cleaned(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    source = repo(tmp_path / "source")
    attempt, _ = setup(app_harness, source)
    created = app_harness.client.post(f"/task-attempts/{attempt['id']}/worktree").json()
    assert (
        app_harness.client.post(f"/worktrees/{created['id']}/cleanup", json={}).status_code == 409
    )
    with app_harness.session_factory() as session:
        worktree = session.get(GitWorktree, created["id"])
        assert worktree is not None
        worktree.status = GitWorktreeStatus.ABANDONED
        worktree.worktree_path = str(source)
        session.commit()
    assert (
        app_harness.client.post(f"/worktrees/{created['id']}/cleanup", json={}).status_code == 409
    )


def test_missing_unregistered_worktree_can_be_marked_cleaned(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    auth(app_harness)
    source = repo(tmp_path / "source-missing")
    attempt, _ = setup(app_harness, source)
    created = app_harness.client.post(f"/task-attempts/{attempt['id']}/worktree").json()
    worktree_path = Path(created["worktree_path"])
    git(source, "worktree", "remove", str(worktree_path))
    with app_harness.session_factory() as session:
        worktree = session.get(GitWorktree, created["id"])
        assert worktree is not None
        worktree.status = GitWorktreeStatus.ABANDONED
        session.commit()
    cleaned = app_harness.client.post(f"/worktrees/{created['id']}/cleanup", json={})
    assert cleaned.status_code == 200
    assert cleaned.json()["status"] == "cleaned"
