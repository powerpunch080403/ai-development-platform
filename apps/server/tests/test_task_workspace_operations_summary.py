from datetime import datetime, timedelta, timezone

from aidp_server.db.models import RecordStatus, TaskAttempt, TaskAttemptStatus, WorkerRun
from conftest import AppHarness
from test_work_and_workers import authenticate, project, task, worker


def _create_attempt(app_harness: AppHarness, task_id: str) -> dict[str, object]:
    response = app_harness.client.post(f"/tasks/{task_id}/attempts", json={})
    assert response.status_code == 201, response.text
    return response.json()


def test_task_workspace_includes_operations_summary_and_stale_worker_run(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    task_data = task(app_harness, project_id)
    attempt = _create_attempt(app_harness, str(task_data["id"]))
    worker_data = worker(app_harness, "Workspace Observer")
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)

    with app_harness.session_factory() as session:
        task_attempt = session.get(TaskAttempt, attempt["id"])
        assert task_attempt is not None
        task_attempt.status = TaskAttemptStatus.WORKER_FAILED
        task_attempt.failed_at = old_time

        worker_run = WorkerRun(
            local_user_id=task_attempt.local_user_id,
            project_id=task_attempt.project_id,
            repository_id=task_attempt.repository_id,
            task_id=task_attempt.task_id,
            task_attempt_id=task_attempt.id,
            worker_id=str(worker_data["id"]),
            adapter_kind="manual",
            status=RecordStatus.RUNNING,
            started_at=old_time,
            last_heartbeat_at=old_time,
            lease_expires_at=old_time,
            heartbeat_source="test",
        )
        session.add(worker_run)
        session.commit()
        worker_run_id = worker_run.id

    response = app_harness.client.get(f"/tasks/{task_data['id']}/workspace")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["attempts"][0]["worker_runs"][0]["id"] == worker_run_id
    assert body["attempts"][0]["worker_runs"][0]["lease_expired"] is True
    assert body["attempts"][0]["worker_runs"][0]["last_heartbeat_at"] is not None
    assert body["operations_summary"]["active_attempt_count"] == 0
    assert body["operations_summary"]["active_worker_run_count"] == 1
    assert body["operations_summary"]["stale_worker_run_count"] == 1
    assert body["operations_summary"]["attention_count"] == 2
    assert body["operations_summary"]["follow_up_available"] is True
    assert body["operations_summary"]["follow_up_source_attempt_id"] == attempt["id"]
    assert body["operations_summary"]["latest_worker_run_id"] == worker_run_id
    assert body["operations_summary"]["latest_worker_run_lease_expired"] is True


def test_task_workspace_follow_up_summary_is_blocked_by_active_attempt(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    task_data = task(app_harness, project_id)
    failed = _create_attempt(app_harness, str(task_data["id"]))
    active = _create_attempt(app_harness, str(task_data["id"]))

    with app_harness.session_factory() as session:
        failed_attempt = session.get(TaskAttempt, failed["id"])
        active_attempt = session.get(TaskAttempt, active["id"])
        assert failed_attempt is not None
        assert active_attempt is not None
        failed_attempt.status = TaskAttemptStatus.FAILED
        active_attempt.status = TaskAttemptStatus.RUNNING_WORKER
        session.commit()

    response = app_harness.client.get(f"/tasks/{task_data['id']}/workspace")

    assert response.status_code == 200, response.text
    summary = response.json()["operations_summary"]
    assert summary["follow_up_available"] is False
    assert summary["follow_up_source_attempt_id"] == failed["id"]
    assert summary["follow_up_blocked_by_attempt_id"] == active["id"]
    assert summary["follow_up_blocked_by_status"] == "running_worker"
