from pathlib import Path
from aidp_server.db.models import GitWorktree, MergeReview, Task, TaskAttempt
from conftest import AppHarness
from test_worktrees import auth, git, repo, setup


def committed(h: AppHarness, tmp_path: Path, name: str) -> tuple[Path, dict[str, object], str, str]:
    source = repo(tmp_path / name)
    attempt, task_id = setup(h, source)
    aid = str(attempt["id"])
    wt = h.client.post(f"/task-attempts/{aid}/worktree").json()
    path = Path(wt["worktree_path"])
    (path / "README.md").write_text("# Reviewed\n", encoding="utf-8")
    result = h.client.post(
        f"/worktrees/{wt['id']}/commit-result", json={"commit_message": "worker intermediate"}
    )
    assert result.status_code == 200
    return source, wt, aid, task_id


def test_review_requires_auth(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/reviews/merge-ready").status_code == 401


def test_review_prepare_approve_and_squash(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    source, wt, aid, task_id = committed(app_harness, tmp_path, "merge")
    base = git(source, "rev-parse", "main")
    ready = app_harness.client.get("/reviews/merge-ready")
    assert any(v["task_attempt_id"] == aid for v in ready.json())
    detail = app_harness.client.get(f"/task-attempts/{aid}/review")
    assert "Reviewed" in detail.json()["diff"] and detail.json()["base_head_matches"]
    (source / "dirty.txt").write_text("x", encoding="utf-8")
    assert app_harness.client.post(f"/task-attempts/{aid}/merge/prepare").status_code == 409
    (source / "dirty.txt").unlink()
    assert (
        app_harness.client.post(
            f"/task-attempts/{aid}/review/approve", json={"review_summary": "Approved"}
        ).status_code
        == 200
    )
    assert app_harness.client.post(f"/task-attempts/{aid}/merge/prepare").status_code == 200
    merged = app_harness.client.post(
        f"/task-attempts/{aid}/merge/squash", json={"commit_message": "chore: squash result"}
    )
    assert merged.status_code == 200
    sha = merged.json()["merge_commit_sha"]
    assert sha and sha != base
    assert int(git(source, "rev-list", "--count", "main")) == 2
    assert git(source, "rev-parse", f"{sha}^") == base
    with app_harness.session_factory() as s:
        a = s.get(TaskAttempt, aid)
        t = s.get(Task, task_id)
        w = s.get(GitWorktree, wt["id"])
        r = s.query(MergeReview).filter_by(task_attempt_id=aid).one()
        assert a and a.status.value == "merged"
        assert t and t.status.value == "completed"
        assert w and w.status.value == "merged"
        assert r.merge_commit_sha == sha
    artifacts = app_harness.client.get(f"/task-attempts/{aid}/artifacts").json()
    assert any(v["kind"] == "generated_report" for v in artifacts)
    assert git(source, "status", "--porcelain") == ""


def test_reject_and_stale_base(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    source, wt, aid, task_id = committed(app_harness, tmp_path, "reject")
    rejected = app_harness.client.post(
        f"/task-attempts/{aid}/review/reject", json={"review_summary": "Changes"}
    )
    assert rejected.status_code == 200
    with app_harness.session_factory() as s:
        a = s.get(TaskAttempt, aid)
        t = s.get(Task, task_id)
        assert a and a.status.value == "rejected"
        assert t and t.status.value == "changes_requested"
    source2, _, aid2, _ = committed(app_harness, tmp_path, "stale")
    (source2 / "other.txt").write_text("advance", encoding="utf-8")
    git(source2, "add", "other.txt")
    git(source2, "commit", "-m", "advance base")
    assert app_harness.client.post(f"/task-attempts/{aid2}/merge/prepare").status_code == 409
