from sqlalchemy import select

from aidp_server.db.models import (
    AgentRun,
    LocalUser,
    RecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    ToolCall,
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
            purpose="start existing attempt test",
        )
        session.add(run)
        session.commit()
        run_id = run.id
    with app_harness.session_factory() as session:
        loaded = session.get(AgentRun, run_id)
        assert loaded is not None
        return loaded


def _committed_attempt(app_harness: AppHarness, task_id: str) -> dict[str, object]:
    created = app_harness.client.post(f"/tasks/{task_id}/attempts", json={})
    assert created.status_code == 201, created.text
    attempt = created.json()
    with app_harness.session_factory() as session:
        row = session.get(TaskAttempt, attempt["id"])
        assert row is not None
        row.status = TaskAttemptStatus.COMMITTED
        session.commit()
    return attempt


def test_owner_can_start_existing_follow_up_attempt(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)
    created_task = task(app_harness, project_id)
    source_attempt = _committed_attempt(app_harness, created_task["id"])

    follow_up = app_harness.client.post(
        f"/agent-runs/{run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "attempt.follow_up",
            "arguments_json": {
                "task_attempt_id": source_attempt["id"],
                "feedback": "Use the existing result and shorten the wording.",
            },
        },
    )
    assert follow_up.status_code == 201, follow_up.text
    follow_up_attempt_id = follow_up.json()["result_json"]["follow_up_task_attempt_id"]

    started = app_harness.client.post(
        f"/agent-runs/{run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "worker.start_task_attempt",
            "arguments_json": {
                "task_attempt_id": follow_up_attempt_id,
                "worker_adapter": "mock",
            },
        },
    )
    assert started.status_code == 201, started.text
    result = started.json()["result_json"]
    assert result["task_attempt_id"] == follow_up_attempt_id
    assert result["status"] == "queued"
    assert result["existing_attempt"] is True
    assert result["worker_run_id"]

    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, follow_up_attempt_id)
        worker_run = session.get(WorkerRun, result["worker_run_id"])
        assert attempt is not None
        assert worker_run is not None
        assert attempt.status == TaskAttemptStatus.QUEUED_WORKER
        assert attempt.worker_id == worker_run.worker_id
        assert attempt.claimed_by_worker_id == worker_run.worker_id
        assert worker_run.task_attempt_id == follow_up_attempt_id
        assert worker_run.status == RecordStatus.QUEUED


def test_owner_cannot_start_same_attempt_twice(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)
    created_task = task(app_harness, project_id)
    attempt = app_harness.client.post(f"/tasks/{created_task['id']}/attempts", json={}).json()

    first = app_harness.client.post(
        f"/agent-runs/{run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "worker.start_task_attempt",
            "arguments_json": {"task_attempt_id": attempt["id"], "worker_adapter": "mock"},
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "succeeded"

    second = app_harness.client.post(
        f"/agent-runs/{run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "worker.start_task_attempt",
            "arguments_json": {"task_attempt_id": attempt["id"], "worker_adapter": "mock"},
        },
    )
    assert second.status_code == 201, second.text
    second_body = second.json()
    assert second_body["status"] == "failed"
    assert second_body["error_code"] == "worker_run_exists"

    with app_harness.session_factory() as session:
        calls = session.scalars(
            select(ToolCall).where(ToolCall.tool_name == "worker.start_task_attempt")
        ).all()
        assert [call.status for call in calls] == [ToolCallStatus.SUCCEEDED, ToolCallStatus.FAILED]
