from sqlalchemy import select

from aidp_server.db.models import AgentRun, LocalUser, TaskAttempt, TaskAttemptStatus, ToolCall, ToolCallStatus
from conftest import AppHarness
from test_conversations_and_tools import authenticate, create_project
from test_work_and_workers import task


def _agent_run(app_harness: AppHarness, project_id: str) -> AgentRun:
    with app_harness.session_factory() as session:
        local_user_id = session.scalars(select(LocalUser.id)).first()
        run = AgentRun(
            local_user_id=local_user_id,
            project_id=project_id,
            purpose="owner attempt tool test",
        )
        session.add(run)
        session.commit()
        run_id = run.id
    with app_harness.session_factory() as session:
        loaded = session.get(AgentRun, run_id)
        assert loaded is not None
        return loaded


def _reviewable_attempt(
    app_harness: AppHarness, task_id: str, status: TaskAttemptStatus = TaskAttemptStatus.COMMITTED
) -> dict[str, object]:
    created = app_harness.client.post(f"/tasks/{task_id}/attempts", json={})
    assert created.status_code == 201, created.text
    attempt = created.json()
    with app_harness.session_factory() as session:
        row = session.get(TaskAttempt, attempt["id"])
        assert row is not None
        row.status = status
        session.commit()
    return attempt


def test_owner_tool_can_accept_attempt(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)
    created_task = task(app_harness, project_id)
    attempt = _reviewable_attempt(app_harness, created_task["id"])

    response = app_harness.client.post(
        f"/agent-runs/{run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "attempt.accept",
            "arguments_json": {
                "task_attempt_id": attempt["id"],
                "review_summary": "Owner accepted this result.",
            },
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "succeeded"
    assert data["result_json"]["status"] == "accepted"
    assert data["result_json"]["task_attempt_id"] == attempt["id"]
    assert data["result_json"]["work_room_message_id"]

    with app_harness.session_factory() as session:
        call = session.get(ToolCall, data["id"])
        row = session.get(TaskAttempt, attempt["id"])
        assert call is not None
        assert row is not None
        assert call.status == ToolCallStatus.SUCCEEDED
        assert row.status == TaskAttemptStatus.ACCEPTED
        assert row.result_summary == "Owner accepted this result."


def test_owner_tool_can_create_follow_up_attempt(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    run = _agent_run(app_harness, project_id)
    created_task = task(app_harness, project_id)
    source_attempt = _reviewable_attempt(app_harness, created_task["id"])

    response = app_harness.client.post(
        f"/agent-runs/{run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "attempt.follow_up",
            "arguments_json": {
                "task_attempt_id": source_attempt["id"],
                "feedback": "Use the previous result, but make the wording shorter.",
            },
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["status"] == "succeeded"
    result = data["result_json"]
    assert result["source_task_attempt_id"] == source_attempt["id"]
    assert result["follow_up_task_attempt_id"] != source_attempt["id"]
    assert result["follow_up_attempt_number"] == 2
    assert result["status"] == "created"
    assert result["work_room_message_id"]

    with app_harness.session_factory() as session:
        source = session.get(TaskAttempt, source_attempt["id"])
        follow_up = session.get(TaskAttempt, result["follow_up_task_attempt_id"])
        assert source is not None
        assert follow_up is not None
        assert source.status == TaskAttemptStatus.REJECTED
        assert follow_up.status == TaskAttemptStatus.CREATED
        assert follow_up.task_id == created_task["id"]
