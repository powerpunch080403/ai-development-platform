from datetime import datetime, timedelta, timezone

from aidp_server.db.models import RecordStatus, TaskAttempt, TaskAttemptStatus, WorkerRun
from conftest import AppHarness
from test_work_and_workers import authenticate, project, task, worker


def _create_attempt(app_harness: AppHarness, task_id: str) -> dict[str, object]:
    response = app_harness.client.post(f"/tasks/{task_id}/attempts", json={})
    assert response.status_code == 201, response.text
    return response.json()


def test_operations_status_requires_auth(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/projects/not-real/operations/status").status_code == 401


def test_project_operations_status_summarizes_runtime_state(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    task_data = task(app_harness, project_id)
    attempt = _create_attempt(app_harness, str(task_data["id"]))
    worker_data = worker(app_harness, "Observer")
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)

    with app_harness.session_factory() as session:
        task_attempt = session.get(TaskAttempt, attempt["id"])
        assert task_attempt is not None
        task_attempt.status = TaskAttemptStatus.RUNNING_WORKER
        task_attempt.started_at = old_time
        task_attempt.updated_at = old_time

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

    response = app_harness.client.get(f"/projects/{project_id}/operations/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_id"] == project_id
    assert body["task_counts"] == {"draft": 1}
    assert body["attempt_counts"]["running_worker"] == 1
    assert body["worker_run_counts"]["running"] == 1
    assert body["active_attempt_count"] == 1
    assert body["active_worker_run_count"] == 1
    assert body["stale_worker_run_count"] == 1
    assert body["attention_count"] == 1
    assert len(body["recent_worker_runs"]) == 1
    assert body["recent_worker_runs"][0]["id"] == worker_run_id
    assert body["recent_worker_runs"][0]["lease_expired"] is True


def test_project_operations_status_is_project_scoped(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_one = project(app_harness, "One")
    project_two = project(app_harness, "Two")
    task_one = task(app_harness, project_one)
    task_two = task(app_harness, project_two)
    _create_attempt(app_harness, str(task_one["id"]))
    attempt_two = _create_attempt(app_harness, str(task_two["id"]))

    with app_harness.session_factory() as session:
        other_attempt = session.get(TaskAttempt, attempt_two["id"])
        assert other_attempt is not None
        other_attempt.status = TaskAttemptStatus.WORKER_FAILED
        session.commit()

    response = app_harness.client.get(f"/projects/{project_one}/operations/status")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["task_counts"] == {"draft": 1}
    assert body["attempt_counts"] == {"created": 1}
    assert body["attention_count"] == 0
