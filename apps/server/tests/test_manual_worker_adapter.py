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
        json={"code": code, "device_name": "Test Web UI", "device_type": "web_ui"},
    )
    assert response.status_code == 200


def test_manual_worker_start_fails_if_unclaimed(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    project = app_harness.client.post("/projects", json={"name": "Manual Worker Project"}).json()
    task = app_harness.client.post(
        f"/projects/{project['id']}/tasks",
        json={
            "title": "Unclaimed Task",
            "instructions": "Should fail",
            "risk_level": "R1",
        },
    ).json()
    attempt = app_harness.client.post(f"/tasks/{task['id']}/attempts", json={}).json()

    response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/manual-worker/start", json={}
    )
    assert response.status_code == 409
    assert "not claimed" in response.json()["detail"].lower()


def test_manual_worker_start_fails_if_wrong_kind(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    project = app_harness.client.post("/projects", json={"name": "Mock Project 3"}).json()
    task = app_harness.client.post(
        f"/projects/{project['id']}/tasks",
        json={
            "title": "Mock Task",
            "instructions": "Should fail",
            "risk_level": "R1",
        },
    ).json()
    attempt = app_harness.client.post(f"/tasks/{task['id']}/attempts", json={}).json()

    worker = app_harness.client.post(
        "/workers", json={"display_name": "Mock Worker", "worker_kind": "mock"}
    ).json()
    app_harness.client.post(
        f"/workers/{worker['id']}/claim", json={"task_attempt_id": attempt["id"]}
    )

    response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/manual-worker/start", json={}
    )
    assert response.status_code == 409
    assert "manual worker" in response.json()["detail"].lower()


def test_manual_worker_e2e(app_harness: AppHarness, tmp_path: Path) -> None:
    source = tmp_path / "manual-worker-repo"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "test@example.com")
    git(source, "config", "user.name", "Test User")
    (source / "README.md").write_text("# Manual Worker Test\n", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-m", "initial")
    base_sha = git(source, "rev-parse", "HEAD").stdout.strip()

    authenticate(app_harness)
    project = app_harness.client.post("/projects", json={"name": "Manual Project"}).json()
    repository = app_harness.client.post(
        f"/projects/{project['id']}/repositories",
        json={"repository_path": str(source), "repository_role": "primary"},
    ).json()

    task = app_harness.client.post(
        f"/projects/{project['id']}/tasks",
        json={
            "repository_id": repository["id"],
            "title": "Manual edit task",
            "instructions": "Edit README.md manually",
            "risk_level": "R1",
            "requested_worker_kind": "manual",
        },
    ).json()

    attempt = app_harness.client.post(f"/tasks/{task['id']}/attempts", json={}).json()
    worker = app_harness.client.post(
        "/workers", json={"display_name": "Manual Worker", "worker_kind": "manual"}
    ).json()
    app_harness.client.post(
        f"/workers/{worker['id']}/claim", json={"task_attempt_id": attempt["id"]}
    ).json()

    # Start manual worker
    start_resp = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/manual-worker/start",
        json={"notes": "Starting manual edit"},
    )
    assert start_resp.status_code == 200
    start_data = start_resp.json()
    worktree_path = Path(start_data["worktree"]["worktree_path"])

    # Ensure source repository HEAD is unchanged
    assert git(source, "rev-parse", "HEAD").stdout.strip() == base_sha

    # Submit without changes should fail
    submit_fail_resp = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/manual-worker/submit",
        json={"commit_message": "chore: try to submit without changes"},
    )
    assert submit_fail_resp.status_code == 409
    assert "no changes" in submit_fail_resp.json()["detail"].lower()

    # Make manual changes
    (worktree_path / "README.md").write_text(
        "# Manual Worker Test\nAdded manually.\n", encoding="utf-8"
    )

    # Submit changes
    submit_resp = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/manual-worker/submit",
        json={
            "commit_message": "docs: manual edit",
            "result_summary": "I edited the file manually",
        },
    )
    assert submit_resp.status_code == 200
    submit_data = submit_resp.json()
    assert submit_data["status"] == "success"

    # Verify source repository HEAD is STILL unchanged after submit
    assert git(source, "rev-parse", "HEAD").stdout.strip() == base_sha
    assert git(source, "status", "--short").stdout.strip() == ""

    # Verify worktree branch has the commit
    wt_sha = git(worktree_path, "rev-parse", "HEAD").stdout.strip()
    assert wt_sha != base_sha
    assert "docs: manual edit" in git(worktree_path, "log", "-1", "--format=%B").stdout

    # Review/Squash merge is still required
    assert app_harness.client.get(f"/task-attempts/{attempt['id']}").json()["status"] == "committed"
    assert app_harness.client.get(f"/tasks/{task['id']}").json()["status"] == "waiting_for_review"

    app_harness.client.post(
        f"/task-attempts/{attempt['id']}/review/approve", json={"review_comment": "Looks good"}
    )
    app_harness.client.post(f"/task-attempts/{attempt['id']}/merge/prepare")
    app_harness.client.post(f"/task-attempts/{attempt['id']}/merge/squash", json={}).json()

    # Now source HEAD is updated
    merged_sha = git(source, "rev-parse", "HEAD").stdout.strip()
    assert merged_sha != base_sha
    assert "Added manually" in (source / "README.md").read_text(encoding="utf-8")
