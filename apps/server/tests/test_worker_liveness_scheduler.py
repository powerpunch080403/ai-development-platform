from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from aidp_server.db.models import (
    AgentRun,
    AuditEvent,
    LocalUser,
    RecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    ToolCall,
    ToolCallStatus,
    WorkerRun,
)
from aidp_server.worker_liveness_scheduler import (
    WorkerLivenessScheduler,
    run_worker_liveness_tick,
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
            purpose="worker liveness scheduler test",
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


def test_scheduler_is_disabled_by_default(app_harness: AppHarness) -> None:
    scheduler = WorkerLivenessScheduler(settings=app_harness.settings)

    assert scheduler.enabled is False


def test_worker_liveness_tick_recovers_stale_running_worker_run(
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
        worker_run.last_heartbeat_at = old_time
        worker_run.lease_expires_at = old_time
        worker_run.heartbeat_source = "test"
        session.commit()

    with app_harness.session_factory() as session:
        result = run_worker_liveness_tick(
            session,
            settings=app_harness.settings,
            trigger="test_tick",
        )
        session.commit()

    assert result["status"] == "succeeded"
    assert result["running_user_count"] == 1
    assert result["recovered_count"] == 1
    assert len(result["tool_call_ids"]) == 1

    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, started["task_attempt_id"])
        worker_run = session.get(WorkerRun, started["worker_run_id"])
        assert attempt is not None
        assert worker_run is not None
        assert worker_run.status == RecordStatus.FAILED
        assert attempt.status == TaskAttemptStatus.WORKER_FAILED

        tool_call = session.get(ToolCall, result["tool_call_ids"][0])
        assert tool_call is not None
        assert tool_call.tool_name == "worker.recover_stale_runs"
        assert tool_call.caller_type.value == "system"
        assert tool_call.status == ToolCallStatus.SUCCEEDED
        assert tool_call.result_json is not None
        assert tool_call.result_json["recovered_count"] == 1

        tick_audit = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "worker_liveness.tick")
        )
        assert tick_audit is not None
        assert tick_audit.metadata_json is not None
        assert tick_audit.metadata_json["recovered_count"] == 1


def test_worker_liveness_tick_reports_idle_when_no_running_worker_runs(
    app_harness: AppHarness,
) -> None:
    with app_harness.session_factory() as session:
        result = run_worker_liveness_tick(
            session,
            settings=app_harness.settings,
            trigger="test_idle_tick",
        )
        session.commit()

    assert result["status"] == "succeeded"
    assert result["running_user_count"] == 0
    assert result["recovered_count"] == 0
    assert result["tool_call_ids"] == []

    with app_harness.session_factory() as session:
        tick_audit = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "worker_liveness.tick")
        )
        assert tick_audit is None
