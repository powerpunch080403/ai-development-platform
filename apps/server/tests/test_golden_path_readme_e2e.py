from pathlib import Path
import subprocess

from aidp_server.cli import create_pairing_code
from conftest import AppHarness


def git(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=10,
        shell=False,
    )


def authenticate(harness: AppHarness) -> None:
    with harness.session_factory() as session:
        code, _ = create_pairing_code(session)
    response = harness.client.post(
        "/auth/pair",
        json={"code": code, "device_name": "Golden Path Web UI", "device_type": "web_ui"},
    )
    assert response.status_code == 200


def test_readme_edit_golden_path_end_to_end(app_harness: AppHarness, tmp_path: Path) -> None:
    implementation_repo = Path(__file__).resolve().parents[3]
    implementation_head_before = git(implementation_repo, "rev-parse", "HEAD").stdout.strip()

    source = tmp_path / "golden-path-repo"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "test@example.com")
    git(source, "config", "user.name", "Test User")
    (source / "README.md").write_text("# Golden Path\n", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-m", "initial")
    base_sha = git(source, "rev-parse", "HEAD").stdout.strip()

    authenticate(app_harness)
    project = app_harness.client.post("/projects", json={"name": "Golden Path"}).json()
    repository = app_harness.client.post(
        f"/projects/{project['id']}/repositories",
        json={"repository_path": str(source), "repository_role": "primary"},
    ).json()
    work_item = app_harness.client.post(
        f"/projects/{project['id']}/work-items",
        json={"title": "README improvement", "work_item_type": "improvement"},
    ).json()
    task = app_harness.client.post(
        f"/projects/{project['id']}/tasks",
        json={
            "repository_id": repository["id"],
            "work_item_id": work_item["id"],
            "title": "Add Golden Path note",
            "instructions": "Append the validated MVP note to README.md.",
            "risk_level": "R1",
            "requested_worker_kind": "manual",
        },
    ).json()
    assert task["status"] == "draft"

    attempt = app_harness.client.post(f"/tasks/{task['id']}/attempts", json={}).json()
    assert attempt["status"] == "created"
    worker = app_harness.client.post(
        "/workers", json={"display_name": "Manual Worker", "worker_kind": "manual"}
    ).json()
    assert worker["status"] == "available"
    claimed = app_harness.client.post(
        f"/workers/{worker['id']}/claim", json={"task_attempt_id": attempt["id"]}
    ).json()
    assert claimed["status"] == "running_worker"
    assert app_harness.client.get(f"/tasks/{task['id']}").json()["status"] == "running"
    assert app_harness.client.get(f"/workers/{worker['id']}").json()["status"] == "claimed"

    worktree = app_harness.client.post(f"/task-attempts/{attempt['id']}/worktree").json()
    assert worktree["status"] == "ready"
    worktree_path = Path(worktree["worktree_path"])
    readme = worktree_path / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nLocal Worker Golden Path validated.\n",
        encoding="utf-8",
    )
    status = app_harness.client.get(f"/worktrees/{worktree['id']}/status").json()
    assert status["is_dirty"] is True
    assert status["status"] == "dirty_result"
    diff = app_harness.client.get(f"/worktrees/{worktree['id']}/diff").json()["diff"]
    assert "Local Worker Golden Path validated." in diff

    committed = app_harness.client.post(
        f"/worktrees/{worktree['id']}/commit-result",
        json={"commit_message": "chore: validate golden path result"},
    ).json()
    result_sha = committed["result_commit_sha"]
    assert committed["status"] == "committed"
    assert app_harness.client.get(f"/task-attempts/{attempt['id']}").json()["status"] == "committed"
    assert app_harness.client.get(f"/tasks/{task['id']}").json()["status"] == "waiting_for_review"
    artifacts_before_merge = app_harness.client.get(
        f"/task-attempts/{attempt['id']}/artifacts"
    ).json()
    assert {artifact["kind"] for artifact in artifacts_before_merge} >= {
        "diff_patch",
        "git_status",
        "commit_log",
    }

    released = app_harness.client.post(
        f"/workers/{worker['id']}/release", json={"task_attempt_id": attempt["id"]}
    )
    assert released.status_code == 200
    assert app_harness.client.get(f"/workers/{worker['id']}").json()["status"] == "available"

    merge_ready = app_harness.client.get("/reviews/merge-ready").json()
    assert any(item["task_attempt_id"] == attempt["id"] for item in merge_ready)
    review = app_harness.client.get(f"/task-attempts/{attempt['id']}/review").json()
    assert review["base_commit_sha"] == base_sha
    assert review["result_commit_sha"] == result_sha
    assert "Local Worker Golden Path validated." in review["diff"]
    approved = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/review/approve",
        json={"review_summary": "README diff reviewed and approved."},
    ).json()
    assert approved["review_status"] == "approved"
    prepared = app_harness.client.post(f"/task-attempts/{attempt['id']}/merge/prepare")
    assert prepared.status_code == 200 and prepared.json()["merge_possible"] is True
    merged = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/merge/squash",
        json={"commit_message": "docs: validate README Golden Path"},
    ).json()
    merge_sha = merged["merge_commit_sha"]
    assert merge_sha

    assert "Local Worker Golden Path validated." in (source / "README.md").read_text(
        encoding="utf-8"
    )
    assert git(source, "status", "--porcelain").stdout.strip() == ""
    assert int(git(source, "rev-list", "--count", "main").stdout.strip()) == 2
    assert git(source, "rev-parse", f"{merge_sha}^").stdout.strip() == base_sha
    assert (
        git(source, "merge-base", "--is-ancestor", result_sha, "main", check=False).returncode == 1
    )
    assert app_harness.client.get(f"/tasks/{task['id']}").json()["status"] == "completed"
    assert app_harness.client.get(f"/task-attempts/{attempt['id']}").json()["status"] == "merged"
    assert app_harness.client.get(f"/worktrees/{worktree['id']}").json()["status"] == "merged"
    assert app_harness.client.get(f"/task-attempts/{attempt['id']}/artifacts").json()
    audit = app_harness.client.get("/audit-events").json()
    assert {event["event_type"] for event in audit} >= {
        "worktree.created",
        "worktree.result_committed",
        "review.approved",
        "merge.squash_completed",
    }

    implementation_head_after = git(implementation_repo, "rev-parse", "HEAD").stdout.strip()
    assert implementation_head_after == implementation_head_before
