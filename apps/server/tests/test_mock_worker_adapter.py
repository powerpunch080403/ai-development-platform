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


def test_mock_worker_adapter_e2e(app_harness: AppHarness, tmp_path: Path) -> None:
    implementation_repo = Path(__file__).resolve().parents[3]
    implementation_head_before = git(implementation_repo, "rev-parse", "HEAD").stdout.strip()

    source = tmp_path / "mock-worker-repo"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "test@example.com")
    git(source, "config", "user.name", "Test User")
    (source / "README.md").write_text("# Mock Worker Test\n", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-m", "initial")
    base_sha = git(source, "rev-parse", "HEAD").stdout.strip()

    authenticate(app_harness)
    project = app_harness.client.post("/projects", json={"name": "Mock Project"}).json()
    repository = app_harness.client.post(
        f"/projects/{project['id']}/repositories",
        json={"repository_path": str(source), "repository_role": "primary"},
    ).json()
    work_item = app_harness.client.post(
        f"/projects/{project['id']}/work-items",
        json={"title": "README mock test", "work_item_type": "improvement"},
    ).json()
    task = app_harness.client.post(
        f"/projects/{project['id']}/tasks",
        json={
            "repository_id": repository["id"],
            "work_item_id": work_item["id"],
            "title": "Run mock worker",
            "instructions": "MOCK_APPEND README.md: This line was added by the mock worker.",
            "risk_level": "R1",
            "requested_worker_kind": "mock",
        },
    ).json()

    attempt = app_harness.client.post(f"/tasks/{task['id']}/attempts", json={}).json()
    worker = app_harness.client.post(
        "/workers", json={"display_name": "Mock Worker", "worker_kind": "mock"}
    ).json()
    claimed = app_harness.client.post(
        f"/workers/{worker['id']}/claim", json={"task_attempt_id": attempt["id"]}
    ).json()
    
    # Create worktree first
    worktree = app_harness.client.post(f"/task-attempts/{attempt['id']}/worktree").json()
    
    # Run mock worker
    mock_run_response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/run-mock-worker",
        json={"commit_message": "chore: mock worker append"}
    ).json()
    
    assert mock_run_response["status"] == "success", f"{mock_run_response['status']} - {mock_run_response.get('worker_run', {}).get('error_message')}"
    worker_run = mock_run_response["worker_run"]
    assert worker_run["status"] == "succeeded"
    assert worker_run["adapter_kind"] == "mock"
    assert mock_run_response["artifact_id"] is not None

    # 1. Confirm source repository HEAD is unchanged after run-mock-worker.
    # 2. Confirm source repository default branch remains clean after run-mock-worker.
    assert git(source, "rev-parse", "HEAD").stdout.strip() == base_sha
    assert git(source, "status", "--short").stdout.strip() == ""

    # 3. Confirm run-mock-worker only commits inside the generated worktree branch.
    worktree_path = Path(worktree["worktree_path"])
    wt_sha = git(worktree_path, "rev-parse", "HEAD").stdout.strip()
    assert wt_sha != base_sha
    assert "chore: mock worker append" in git(worktree_path, "log", "-1", "--format=%B").stdout

    # 4. Confirm review-ready flow is still required after mock worker execution.
    assert app_harness.client.get(f"/task-attempts/{attempt['id']}").json()["status"] == "committed"
    assert app_harness.client.get(f"/tasks/{task['id']}").json()["status"] == "waiting_for_review"

    artifacts = app_harness.client.get(f"/task-attempts/{attempt['id']}/artifacts").json()
    assert any(a["kind"] == "worker_report" for a in artifacts)

    # Clean up and merge review
    review = app_harness.client.get(f"/task-attempts/{attempt['id']}/review").json()
    assert "This line was added by the mock worker." in review["diff"]

    # 5. Confirm squash merge only happens through existing review/merge API.
    # This is the only place the source repository default branch should be modified.
    app_harness.client.post(
        f"/task-attempts/{attempt['id']}/review/approve",
        json={"review_comment": "LGTM"},
    )
    app_harness.client.post(f"/task-attempts/{attempt['id']}/merge/prepare")
    app_harness.client.post(
        f"/task-attempts/{attempt['id']}/merge/squash",
        json={}
    ).json()
    # Verify source repository HEAD is now updated
    merged_sha = git(source, "rev-parse", "HEAD").stdout.strip()
    assert merged_sha != base_sha
    
    # 6. Verify run-mock-worker does not change the implementation repository either
    implementation_head_after = git(implementation_repo, "rev-parse", "HEAD").stdout.strip()
    assert implementation_head_before == implementation_head_after

    assert "This line was added by the mock worker." in (source / "README.md").read_text(encoding="utf-8")
    
    implementation_head_after = git(implementation_repo, "rev-parse", "HEAD").stdout.strip()
    assert implementation_head_after == implementation_head_before

def test_mock_worker_path_traversal(app_harness: AppHarness, tmp_path: Path) -> None:
    source = tmp_path / "mock-worker-repo-2"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.email", "test@example.com")
    git(source, "config", "user.name", "Test User")
    (source / "README.md").write_text("# Mock Worker Test\n", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-m", "initial")

    authenticate(app_harness)
    project = app_harness.client.post("/projects", json={"name": "Mock Project 2"}).json()
    repository = app_harness.client.post(
        f"/projects/{project['id']}/repositories",
        json={"repository_path": str(source), "repository_role": "primary"},
    ).json()
    task = app_harness.client.post(
        f"/projects/{project['id']}/tasks",
        json={
            "repository_id": repository["id"],
            "title": "Run mock worker traversal",
            "instructions": "MOCK_APPEND ../outside.txt: Exploit.",
            "risk_level": "R1",
            "requested_worker_kind": "mock",
        },
    ).json()

    attempt = app_harness.client.post(f"/tasks/{task['id']}/attempts", json={}).json()
    worker = app_harness.client.post(
        "/workers", json={"display_name": "Mock Worker", "worker_kind": "mock"}
    ).json()
    app_harness.client.post(
        f"/workers/{worker['id']}/claim", json={"task_attempt_id": attempt["id"]}
    )
    app_harness.client.post(f"/task-attempts/{attempt['id']}/worktree").json()
    
    mock_run_response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/run-mock-worker",
        json={}
    ).json()
    
    assert mock_run_response["status"] == "failed"
    assert app_harness.client.get(f"/task-attempts/{attempt['id']}").json()["status"] == "worker_failed"
    artifacts = app_harness.client.get(f"/task-attempts/{attempt['id']}/artifacts").json()
    assert any(a["kind"] == "error_log" for a in artifacts)
