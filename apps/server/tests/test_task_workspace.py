import subprocess

from aidp_server.db.models import (
    ArtifactKind,
    ArtifactRef,
    GitWorktree,
    GitWorktreeStatus,
    ProcessRun,
    ProcessRunStatus,
    RecordStatus,
    Worker,
    WorkerKind,
    WorkerRun,
    WorkerStatus,
    utc_now,
)
from conftest import AppHarness
from test_work_and_workers import authenticate, project


def test_task_workspace_requires_auth(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/tasks/missing/workspace").status_code == 401


def test_task_workspace_aggregates_attempt_execution_records(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness, "Workspace Project")

    repo_dir = app_harness.settings.app_data_dir / "workspace_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)

    repository = app_harness.client.post(
        f"/projects/{project_id}/repositories",
        json={"repository_path": str(repo_dir), "repository_role": "primary"},
    )
    assert repository.status_code == 201, repository.json()
    repository_id = repository.json()["id"]

    task = app_harness.client.post(
        f"/projects/{project_id}/tasks",
        json={
            "repository_id": repository_id,
            "title": "Review workspace task",
            "instructions": "Collect task workspace records.",
            "risk_level": "R1",
            "requested_worker_kind": "manual",
        },
    )
    assert task.status_code == 201, task.json()
    task_id = task.json()["id"]

    attempt = app_harness.client.post(f"/tasks/{task_id}/attempts", json={})
    assert attempt.status_code == 201, attempt.json()
    attempt_id = attempt.json()["id"]

    now = utc_now()
    with app_harness.session_factory() as session:
        created_attempt = session.get(__import__("aidp_server.db.models").db.models.TaskAttempt, attempt_id)
        assert created_attempt is not None
        user_id = created_attempt.local_user_id

        worker = Worker(
            local_user_id=user_id,
            device_id=None,
            display_name="Workspace Worker",
            worker_kind=WorkerKind.MANUAL,
            status=WorkerStatus.AVAILABLE,
            capabilities_json={"manual": True},
            registered_at=now,
        )
        session.add(worker)
        session.flush()

        created_attempt.worker_id = worker.id
        created_attempt.claimed_by_worker_id = worker.id

        worker_run = WorkerRun(
            local_user_id=user_id,
            project_id=project_id,
            repository_id=repository_id,
            task_id=task_id,
            task_attempt_id=attempt_id,
            worker_id=worker.id,
            adapter_kind="manual",
            status=RecordStatus.SUCCEEDED,
            started_at=now,
            completed_at=now,
            summary="Workspace aggregation succeeded.",
        )
        session.add(worker_run)
        session.flush()

        process_run = ProcessRun(
            local_user_id=user_id,
            project_id=project_id,
            repository_id=repository_id,
            task_id=task_id,
            task_attempt_id=attempt_id,
            worker_id=worker.id,
            worker_run_id=worker_run.id,
            command_display="python -c print",
            executable="python",
            arguments_json={"args": ["-c", "print('ok')"]},
            working_directory=str(repo_dir),
            status=ProcessRunStatus.SUCCEEDED,
            exit_code=0,
            timeout_seconds=5,
            started_at=now,
            completed_at=now,
            duration_ms=10,
        )
        session.add(process_run)

        artifact = ArtifactRef(
            owner_type="task_attempt",
            owner_id=attempt_id,
            local_user_id=user_id,
            project_id=project_id,
            repository_id=repository_id,
            task_id=task_id,
            task_attempt_id=attempt_id,
            worker_id=worker.id,
            kind=ArtifactKind.DIFF_PATCH,
            storage_path=f"{attempt_id}/diff.txt",
            content_type="text/plain; charset=utf-8",
            size_bytes=12,
            checksum="0" * 64,
        )
        session.add(artifact)

        worktree = GitWorktree(
            local_user_id=user_id,
            project_id=project_id,
            repository_id=repository_id,
            task_id=task_id,
            task_attempt_id=attempt_id,
            worker_id=worker.id,
            worktree_path=str(repo_dir / "worktree"),
            branch_name="aidp/task-workspace-test",
            base_branch="main",
            base_commit_sha="1" * 40,
            result_commit_sha="2" * 40,
            status=GitWorktreeStatus.COMMITTED,
            prepared_at=now,
            committed_at=now,
        )
        session.add(worktree)
        session.commit()

    response = app_harness.client.get(f"/tasks/{task_id}/workspace")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["task"]["id"] == task_id
    assert data["task"]["repository_id"] == repository_id
    assert len(data["attempts"]) == 1

    bundle = data["attempts"][0]
    assert bundle["attempt"]["id"] == attempt_id
    assert len(bundle["worker_runs"]) == 1
    assert bundle["worker_runs"][0]["summary"] == "Workspace aggregation succeeded."
    assert len(bundle["process_runs"]) == 1
    assert bundle["process_runs"][0]["status"] == "succeeded"
    assert bundle["process_runs"][0]["exit_code"] == 0
    assert len(bundle["artifacts"]) == 1
    assert bundle["artifacts"][0]["kind"] == "diff_patch"
    assert bundle["worktree"]["status"] == "committed"
    assert bundle["worktree"]["result_commit_sha"] == "2" * 40
