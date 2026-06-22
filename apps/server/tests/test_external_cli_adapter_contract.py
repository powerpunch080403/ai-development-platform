import hashlib
import json
import subprocess
from pathlib import Path

from aidp_server.artifacts import read_text_artifact
from aidp_server.cli import create_pairing_code
from aidp_server.db.models import (
    ArtifactKind,
    ArtifactRef,
    GitWorktree,
    ProcessRun,
    Task,
    TaskAttempt,
    WorkerRun,
)
from conftest import AppHarness


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()


def create_repository(path: Path) -> Path:
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("# External CLI baseline\n", encoding="utf-8")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "initial")
    return path


def authenticate(harness: AppHarness) -> None:
    with harness.session_factory() as session:
        code, _ = create_pairing_code(session)
    response = harness.client.post(
        "/auth/pair",
        json={"code": code, "device_name": "CLI Test", "device_type": "web_ui"},
    )
    assert response.status_code == 200, response.text


def file_snapshot(path: Path) -> dict[str, str]:
    return {
        item.relative_to(path).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest()
        for item in path.rglob("*")
        if item.is_file() and ".git" not in item.relative_to(path).parts
    }


def setup_claimed_attempt(
    harness: AppHarness, source: Path
) -> tuple[str, str, dict[str, object], str, str]:
    project = harness.client.post("/projects", json={"name": "CLI Project"})
    assert project.status_code == 201, project.text
    project_id = str(project.json()["id"])
    repository = harness.client.post(
        f"/projects/{project_id}/repositories",
        json={"repository_path": str(source), "repository_role": "primary"},
    )
    assert repository.status_code == 201, repository.text
    repository_id = str(repository.json()["id"])
    task = harness.client.post(
        f"/projects/{project_id}/tasks",
        json={
            "repository_id": repository_id,
            "title": "Validate external CLI contract",
            "instructions": "Run only the fixed contract dry-run.",
            "risk_level": "R1",
            "requested_worker_kind": "external_cli",
        },
    )
    assert task.status_code == 201, task.text
    task_id = str(task.json()["id"])
    attempt = harness.client.post(f"/tasks/{task_id}/attempts", json={})
    assert attempt.status_code == 201, attempt.text
    attempt_id = str(attempt.json()["id"])
    worker = harness.client.post(
        "/workers",
        json={"display_name": "External CLI Dry Run", "worker_kind": "external_cli"},
    )
    assert worker.status_code == 201, worker.text
    worker_id = str(worker.json()["id"])
    claim = harness.client.post(f"/workers/{worker_id}/claim", json={"task_attempt_id": attempt_id})
    assert claim.status_code == 200, claim.text
    worktree = harness.client.post(f"/task-attempts/{attempt_id}/worktree", json={})
    assert worktree.status_code == 201, worktree.text
    return attempt_id, worker_id, worktree.json(), task_id, repository_id


def test_external_cli_endpoints_require_auth(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/task-attempts/missing/external-cli/context").status_code == 401
    response = app_harness.client.post(
        "/task-attempts/missing/external-cli/dry-run",
        json={"worker_id": "missing"},
    )
    assert response.status_code == 401


def test_external_cli_context_package(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    source = create_repository(tmp_path / "external-cli-context-source")
    attempt_id, _, worktree, task_id, repository_id = setup_claimed_attempt(app_harness, source)

    response = app_harness.client.get(f"/task-attempts/{attempt_id}/external-cli/context")
    assert response.status_code == 200, response.text
    context = response.json()
    assert context["task_attempt_id"] == attempt_id
    assert context["task_id"] == task_id
    assert context["repository_id"] == repository_id
    assert context["git_worktree_id"] == worktree["id"]
    assert context["worktree_path"] == worktree["worktree_path"]
    assert context["allowed_working_directory"] == worktree["worktree_path"]
    assert context["branch_name"] == worktree["branch_name"]
    assert context["base_branch"] == worktree["base_branch"]
    assert context["base_commit_sha"] == worktree["base_commit_sha"]
    assert context["task_title"] == "Validate external CLI contract"
    assert context["task_instructions"] == "Run only the fixed contract dry-run."
    assert context["artifact_ids"] == []
    assert context["worker_run_id"] is None
    assert context["created_at"].endswith("+00:00")
    assert "remote push" in context["forbidden_actions"]
    assert "Owner" in context["approval_review_boundary"]
    assert context["constraints"] == [
        "Only operate inside the assigned worktree path.",
        "Do not modify the source repository path.",
        "Do not push to remotes.",
        "Do not merge into main/default.",
        "Do not edit files outside the worktree.",
        "Do not read or write .env or secret files unless explicitly allowed later.",
        "Produce a concise worker report.",
        "Leave review, approval, and squash merge to Owner.",
    ]


def test_external_cli_dry_run_rejects_arbitrary_command_fields(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    authenticate(app_harness)
    source = create_repository(tmp_path / "external-cli-rejection-source")
    attempt_id, worker_id, _, _, _ = setup_claimed_attempt(app_harness, source)
    with app_harness.session_factory() as session:
        process_count_before = session.query(ProcessRun).count()

    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/dry-run",
        json={
            "adapter_kind": "external_cli_dry_run",
            "worker_id": worker_id,
            "dry_run": True,
            "command": "git push",
        },
    )
    assert response.status_code == 422, response.text
    with app_harness.session_factory() as session:
        assert session.query(ProcessRun).count() == process_count_before


def test_external_cli_dry_run_is_linked_and_non_mutating(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    authenticate(app_harness)
    source = create_repository(tmp_path / "external-cli-dry-run-source")
    source_head_before = git(source, "rev-parse", "HEAD")
    attempt_id, worker_id, worktree_data, task_id, _ = setup_claimed_attempt(app_harness, source)
    worktree_path = Path(str(worktree_data["worktree_path"]))
    source_snapshot_before = file_snapshot(source)
    worktree_snapshot_before = file_snapshot(worktree_path)
    worktree_status_before = git(worktree_path, "status", "--porcelain")

    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/dry-run",
        json={
            "adapter_kind": "external_cli_dry_run",
            "worker_id": worker_id,
            "dry_run": True,
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "succeeded"
    assert result["error_code"] is None
    assert result["error_message"] is None

    with app_harness.session_factory() as session:
        worker_run = session.get(WorkerRun, result["worker_run_id"])
        process_run = session.get(ProcessRun, result["process_run_id"])
        context_ref = session.get(ArtifactRef, result["context_artifact_id"])
        report_ref = session.get(ArtifactRef, result["report_artifact_id"])
        stdout_ref = session.get(ArtifactRef, result["stdout_artifact_id"])
        attempt = session.get(TaskAttempt, attempt_id)
        task = session.get(Task, task_id)
        worktree = session.get(GitWorktree, str(worktree_data["id"]))

        assert worker_run is not None
        assert worker_run.status.value == "succeeded"
        assert worker_run.task_attempt_id == attempt_id
        assert worker_run.worker_id == worker_id
        assert worker_run.adapter_kind == "external_cli_dry_run"
        assert worker_run.started_at is not None
        assert worker_run.completed_at is not None
        assert process_run is not None
        assert process_run.status.value == "succeeded"
        assert process_run.worker_run_id == worker_run.id
        assert process_run.task_attempt_id == attempt_id
        assert process_run.worker_id == worker_id
        assert process_run.working_directory == str(worktree_path)
        assert context_ref is not None and context_ref.kind is ArtifactKind.GENERATED_REPORT
        assert report_ref is not None and report_ref.kind is ArtifactKind.WORKER_REPORT
        assert stdout_ref is not None and stdout_ref.kind is ArtifactKind.CLI_TRANSCRIPT
        context_text = read_text_artifact(context_ref, app_harness.settings)
        report_text = read_text_artifact(report_ref, app_harness.settings)
        stdout_text = read_text_artifact(stdout_ref, app_harness.settings)
        assert attempt is not None and attempt.status.value == "running_worker"
        assert task is not None and task.status.value == "running"
        assert worktree is not None and worktree.status.value == "ready"
        assert worktree.result_commit_sha is None

    context = json.loads(context_text)
    report = json.loads(report_text)
    assert context["worker_run_id"] == result["worker_run_id"]
    assert report["files_modified"] is False
    assert report["result_commit_created"] is False
    assert report["context_artifact_id"] == result["context_artifact_id"]
    assert "External CLI adapter dry run completed." in stdout_text
    assert git(source, "rev-parse", "HEAD") == source_head_before
    assert git(source, "status", "--porcelain") == ""
    assert git(worktree_path, "status", "--porcelain") == worktree_status_before == ""
    assert file_snapshot(source) == source_snapshot_before
    assert file_snapshot(worktree_path) == worktree_snapshot_before
