from sqlalchemy import select

from aidp_server.db.models import (
    AgentRun,
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
            purpose="worker drain queue test",
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


def _drain_mock_queue(app_harness: AppHarness, run_id: str):
    return app_harness.client.post(
        f"/agent-runs/{run_id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "worker.drain_queue",
            "arguments_json": {"worker_adapter": "mock"},
        },
    )


def test_worker_drain_queue_runs_oldest_queued_worker_run(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)
    task_one = task(app_harness, project_id)
    task_two = task(app_harness, project_id)

    first = _start_mock_attempt(app_harness, run.id, task_one["id"])
    second = _start_mock_attempt(app_harness, run.id, task_two["id"])

    drained = _drain_mock_queue(app_harness, run.id)

    assert drained.status_code == 201, drained.text
    body = drained.json()
    assert body["status"] == ToolCallStatus.SUCCEEDED.value
    assert body["result_json"]["status"] == "succeeded"
    assert body["result_json"]["worker_run_id"] == first["worker_run_id"]

    with app_harness.session_factory() as session:
        first_attempt = session.get(TaskAttempt, first["task_attempt_id"])
        first_run = session.get(WorkerRun, first["worker_run_id"])
        second_attempt = session.get(TaskAttempt, second["task_attempt_id"])
        second_run = session.get(WorkerRun, second["worker_run_id"])
        assert first_attempt is not None
        assert first_run is not None
        assert second_attempt is not None
        assert second_run is not None
        assert first_attempt.status == TaskAttemptStatus.ACCEPTED
        assert first_run.status == RecordStatus.SUCCEEDED
        assert second_attempt.status == TaskAttemptStatus.QUEUED_WORKER
        assert second_run.status == RecordStatus.QUEUED


def test_worker_drain_queue_respects_capacity_guard(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)
    task_one = task(app_harness, project_id)
    task_two = task(app_harness, project_id)

    first = _start_mock_attempt(app_harness, run.id, task_one["id"])
    second = _start_mock_attempt(app_harness, run.id, task_two["id"])

    with app_harness.session_factory() as session:
        first_attempt = session.get(TaskAttempt, first["task_attempt_id"])
        first_run = session.get(WorkerRun, first["worker_run_id"])
        assert first_attempt is not None
        assert first_run is not None
        first_attempt.status = TaskAttemptStatus.RUNNING_WORKER
        first_run.status = RecordStatus.RUNNING
        session.commit()

    drained = _drain_mock_queue(app_harness, run.id)

    assert drained.status_code == 201, drained.text
    body = drained.json()
    assert body["status"] == ToolCallStatus.SUCCEEDED.value
    assert body["result_json"]["status"] == "queued"
    assert body["result_json"]["reason"] == "worker_capacity_full"
    assert body["result_json"]["active_worker_run_id"] == first["worker_run_id"]

    with app_harness.session_factory() as session:
        second_attempt = session.get(TaskAttempt, second["task_attempt_id"])
        second_run = session.get(WorkerRun, second["worker_run_id"])
        assert second_attempt is not None
        assert second_run is not None
        assert second_attempt.status == TaskAttemptStatus.QUEUED_WORKER
        assert second_run.status == RecordStatus.QUEUED


def test_worker_drain_queue_reports_idle_when_no_queued_runs(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)

    drained = _drain_mock_queue(app_harness, run.id)

    assert drained.status_code == 201, drained.text
    body = drained.json()
    assert body["status"] == ToolCallStatus.SUCCEEDED.value
    assert body["result_json"]["status"] == "idle"
    assert body["result_json"]["reason"] == "no_queued_worker_runs"
