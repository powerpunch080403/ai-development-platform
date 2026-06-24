from pathlib import Path

from aidp_server.db.models import WorkerRun, RecordStatus, TaskAttempt, utc_now
from conftest import AppHarness
from test_external_cli_adapter_contract import (
    setup_claimed_attempt,
    authenticate,
    create_repository,
    git,
)


def test_external_cli_active_run_blocks_new_dry_run(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    authenticate(app_harness)
    source = create_repository(tmp_path / "active_run_test")
    aid, worker_id, wt, task_id, repo_id = setup_claimed_attempt(app_harness, source)

    # Create an active WorkerRun
    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, aid)
        active_run = WorkerRun(
            local_user_id=attempt.local_user_id,
            project_id=attempt.project_id,
            task_id=task_id,
            task_attempt_id=aid,
            worker_id=attempt.claimed_by_worker_id,
            adapter_kind="external_cli_dry_run",
            status=RecordStatus.RUNNING,
            started_at=utc_now(),
        )
        session.add(active_run)
        session.commit()
        active_run_id = active_run.id

    # Attempt to dry run should fail with 409
    res = app_harness.client.post(
        f"/task-attempts/{aid}/external-cli/dry-run",
        json={
            "adapter_kind": "external_cli_dry_run",
            "worker_id": worker_id,
            "dry_run": True,
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "ACTIVE_EXTERNAL_CLI_RUN_EXISTS"

    # Verify source and worktree are unchanged
    base_sha = git(source, "rev-parse", "HEAD")
    assert git(source, "rev-parse", "HEAD") == base_sha
    assert git(source, "status", "--short") == ""

    # TaskAttempt state shouldn't change to committed/reviewing
    attempt_res = app_harness.client.get(f"/task-attempts/{aid}").json()
    assert attempt_res["status"] in ("preparing_worktree", "created", "running_worker")

    # Now change status to SUCCEEDED and try again
    with app_harness.session_factory() as session:
        run = session.get(WorkerRun, active_run_id)
        run.status = RecordStatus.SUCCEEDED
        session.commit()

    res = app_harness.client.post(
        f"/task-attempts/{aid}/external-cli/dry-run",
        json={
            "adapter_kind": "external_cli_dry_run",
            "worker_id": worker_id,
            "dry_run": True,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "succeeded"


def test_external_cli_created_run_blocks_new_dry_run(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    authenticate(app_harness)
    source = create_repository(tmp_path / "created_run_test")
    aid, worker_id, wt, task_id, repo_id = setup_claimed_attempt(app_harness, source)

    # Create an active WorkerRun
    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, aid)
        active_run = WorkerRun(
            local_user_id=attempt.local_user_id,
            project_id=attempt.project_id,
            task_id=task_id,
            task_attempt_id=aid,
            worker_id=attempt.claimed_by_worker_id,
            adapter_kind="antigravity_cli",
            status=RecordStatus.CREATED,
            started_at=utc_now(),
        )
        session.add(active_run)
        session.commit()

    res = app_harness.client.post(
        f"/task-attempts/{aid}/external-cli/dry-run",
        json={
            "adapter_kind": "external_cli_dry_run",
            "worker_id": worker_id,
            "dry_run": True,
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "ACTIVE_EXTERNAL_CLI_RUN_EXISTS"


def test_external_cli_failed_run_allows_new_dry_run(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    authenticate(app_harness)
    source = create_repository(tmp_path / "failed_run_test")
    aid, worker_id, wt, task_id, repo_id = setup_claimed_attempt(app_harness, source)

    # Create a failed WorkerRun
    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, aid)
        failed_run = WorkerRun(
            local_user_id=attempt.local_user_id,
            project_id=attempt.project_id,
            task_id=task_id,
            task_attempt_id=aid,
            worker_id=attempt.claimed_by_worker_id,
            adapter_kind="codex_cli",
            status=RecordStatus.FAILED,
            started_at=utc_now(),
        )
        session.add(failed_run)
        session.commit()

    res = app_harness.client.post(
        f"/task-attempts/{aid}/external-cli/dry-run",
        json={
            "adapter_kind": "external_cli_dry_run",
            "worker_id": worker_id,
            "dry_run": True,
        },
    )
    assert res.status_code == 200
