from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from aidp_server.db.models import (
    AgentRun,
    AuditEvent,
    LocalUser,
    RecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    ToolCallStatus,
    WorkerRun,
)
from conftest import AppHarness
from test_conversations_and_tools import authenticate, create_project
from test_work_and_workers import task


def _agent_run(app_harness: AppHarness, project_id: str) -> AgentRun:
    with app_harness.session_factory() as session:
        local_user_id = session.scalars(select(LocalUser.id)).first()
        run = AgentRun(
            local_user_id=local_user_id,
            project_id=project_id,
            purpose="worker liveness recovery test",
        )
        session.add(run)
        session.commit()
        run_id = run.id
    with app_harness.session_factory() as session:
        loaded = session.get(AgentRun, run_id)
        assert loaded is not None
        return loaded


def _start_mock_attempt(app_harness: AppHarness, run_id: str, task_id: str) -> dict[str, object]:
    response = app_harness.client.post(
        f"/agent-runs/{run_id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "worker.start_task_attempt",
            "arguments_json": {"task_id": task_id, "worker_adapter": "mock"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == ToolCallStatus.SUCCEEDED.value
    return body["result_json"]


def _recover_stale_runs(app_harness: AppHarness, run_id: str, timeout_seconds: int = 3600):
    return app_harness.client.post(
        f"/agent-runs/{run_id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "worker.recover_stale_runs",
            "arguments_json": {"timeout_seconds": timeout_seconds, "worker_adapter": "mock"},
        },
    )


def _drain_mock_queue(app_harness: AppHarness, run_id: str):
    return app_harness.client.post(
        f"/agent-runs/{run_id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "worker.drain_queue",
            "arguments_json": {"worker_adapter": "mock"},
        },
    )


def test_stale_running_worker_run_is_failed_and_attempt_becomes_worker_failed(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)
    task_one = task(app_harness, project_id)
    started = _start_mock_attempt(app_harness, run.id, task_one["id"])
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)

    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, started["task_attempt_id"])
        worker_run = session.get(WorkerRun, started["worker_run_id"])
        assert attempt is not None
        assert worker_run is not None
        attempt.status = TaskAttemptStatus.RUNNING_WORKER
        attempt.started_at = old_time
        attempt.updated_at = old_time
        worker_run.status = RecordStatus.RUNNING
        worker_run.started_at = old_time
        worker_run.updated_at = old_time
        session.commit()

    response = _recover_stale_runs(app_harness, run.id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == ToolCallStatus.SUCCEEDED.value
    assert body["result_json"]["status"] == "succeeded"
    assert body["result_json"]["recovered_count"] == 1
    assert body["result_json"]["automatic_retry"] is False
    assert body["result_json"]["new_attempt_created"] is False
    assert body["result_json"]["worktree_preserved"] is True

    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, started["task_attempt_id"])
        worker_run = session.get(WorkerRun, started["worker_run_id"])
        assert attempt is not None
        assert worker_run is not None
        assert worker_run.status == RecordStatus.FAILED
        assert worker_run.failed_at is not None
        assert worker_run.error_code == "STALE_WORKER_RUN"
        assert attempt.status == TaskAttemptStatus.WORKER_FAILED
        assert attempt.failed_at is not None
        assert attempt.error_code == "STALE_WORKER_RUN"

        audit = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "worker_run.stale_recovered")
        )
        assert audit is not None
        assert audit.metadata_json is not None
        assert audit.metadata_json["worker_run_id"] == started["worker_run_id"]


def test_fresh_running_worker_run_is_not_recovered(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)
    task_one = task(app_harness, project_id)
    started = _start_mock_attempt(app_harness, run.id, task_one["id"])
    fresh_time = datetime.now(timezone.utc)

    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, started["task_attempt_id"])
        worker_run = session.get(WorkerRun, started["worker_run_id"])
        assert attempt is not None
        assert worker_run is not None
        attempt.status = TaskAttemptStatus.RUNNING_WORKER
        attempt.started_at = fresh_time
        attempt.updated_at = fresh_time
        worker_run.status = RecordStatus.RUNNING
        worker_run.started_at = fresh_time
        worker_run.updated_at = fresh_time
        session.commit()

    response = _recover_stale_runs(app_harness, run.id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == ToolCallStatus.SUCCEEDED.value
    assert body["result_json"]["recovered_count"] == 0

    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, started["task_attempt_id"])
        worker_run = session.get(WorkerRun, started["worker_run_id"])
        assert attempt is not None
        assert worker_run is not None
        assert worker_run.status == RecordStatus.RUNNING
        assert attempt.status == TaskAttemptStatus.RUNNING_WORKER


def test_recovery_unblocks_capacity_for_next_queued_worker_run(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)
    task_one = task(app_harness, project_id)
    task_two = task(app_harness, project_id)
    first = _start_mock_attempt(app_harness, run.id, task_one["id"])
    second = _start_mock_attempt(app_harness, run.id, task_two["id"])
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)

    with app_harness.session_factory() as session:
        first_attempt = session.get(TaskAttempt, first["task_attempt_id"])
        first_run = session.get(WorkerRun, first["worker_run_id"])
        assert first_attempt is not None
        assert first_run is not None
        first_attempt.status = TaskAttemptStatus.RUNNING_WORKER
        first_attempt.started_at = old_time
        first_attempt.updated_at = old_time
        first_run.status = RecordStatus.RUNNING
        first_run.started_at = old_time
        first_run.updated_at = old_time
        session.commit()

    response = _recover_stale_runs(app_harness, run.id)
    assert response.status_code == 201, response.text
    assert response.json()["result_json"]["recovered_count"] == 1

    drained = _drain_mock_queue(app_harness, run.id)
    assert drained.status_code == 201, drained.text
    body = drained.json()
    assert body["status"] == ToolCallStatus.SUCCEEDED.value
    assert body["result_json"]["status"] == "succeeded"
    assert body["result_json"]["worker_run_id"] == second["worker_run_id"]

    with app_harness.session_factory() as session:
        attempt_count = session.scalar(select(func.count(TaskAttempt.id)))
        worker_run_count = session.scalar(select(func.count(WorkerRun.id)))
        first_attempt = session.get(TaskAttempt, first["task_attempt_id"])
        first_run = session.get(WorkerRun, first["worker_run_id"])
        second_attempt = session.get(TaskAttempt, second["task_attempt_id"])
        second_run = session.get(WorkerRun, second["worker_run_id"])

        assert attempt_count == 2
        assert worker_run_count == 2
        assert first_attempt is not None
        assert first_run is not None
        assert second_attempt is not None
        assert second_run is not None
        assert first_attempt.status == TaskAttemptStatus.WORKER_FAILED
        assert first_run.status == RecordStatus.FAILED
        assert second_attempt.status == TaskAttemptStatus.ACCEPTED
        assert second_run.status == RecordStatus.SUCCEEDED
