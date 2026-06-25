from sqlalchemy import select

from aidp_server.db.models import (
    LocalUser,
    TaskAttempt,
    TaskAttemptStatus,
    ToolCall,
    ToolCallerType,
    ToolCallStatus,
)
from aidp_server.owner_attempt_tools import execute_attempt_action_tool
from conftest import AppHarness
from test_work_and_workers import authenticate, project, task


def _create_attempt(app_harness: AppHarness, task_id: str) -> dict[str, object]:
    response = app_harness.client.post(f"/tasks/{task_id}/attempts", json={})
    assert response.status_code == 201, response.text
    return response.json()


def _set_attempt_status(
    app_harness: AppHarness,
    attempt_id: str,
    status: TaskAttemptStatus,
) -> None:
    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, attempt_id)
        assert attempt is not None
        attempt.status = status
        session.commit()


def test_rest_follow_up_from_failed_attempt_creates_explicit_retry_attempt(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    task_data = task(app_harness, project_id)
    source = _create_attempt(app_harness, str(task_data["id"]))
    _set_attempt_status(app_harness, str(source["id"]), TaskAttemptStatus.WORKER_FAILED)

    response = app_harness.client.post(
        f"/task-attempts/{source['id']}/follow-up",
        json={"feedback": "Try again with the same task constraints."},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source_attempt"]["status"] == "worker_failed"
    assert body["follow_up_attempt"]["status"] == "created"
    assert body["follow_up_attempt"]["attempt_number"] == 2
    assert body["work_room_message"]["metadata"]["explicit_retry"] is True
    assert body["work_room_message"]["metadata"]["automatic_retry"] is False


def test_rest_follow_up_blocks_when_task_has_another_active_attempt(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    task_data = task(app_harness, project_id)
    source = _create_attempt(app_harness, str(task_data["id"]))
    active = _create_attempt(app_harness, str(task_data["id"]))
    _set_attempt_status(app_harness, str(source["id"]), TaskAttemptStatus.FAILED)
    _set_attempt_status(app_harness, str(active["id"]), TaskAttemptStatus.CREATED)

    response = app_harness.client.post(
        f"/task-attempts/{source['id']}/follow-up",
        json={"feedback": "Try again after the failure."},
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "active_attempt_exists"
    assert detail["blocking_attempt_id"] == active["id"]
    assert detail["blocking_attempt_status"] == "created"


def test_owner_follow_up_tool_uses_same_retry_guard(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    task_data = task(app_harness, project_id)
    source = _create_attempt(app_harness, str(task_data["id"]))
    active = _create_attempt(app_harness, str(task_data["id"]))
    _set_attempt_status(app_harness, str(source["id"]), TaskAttemptStatus.WORKER_FAILED)
    _set_attempt_status(app_harness, str(active["id"]), TaskAttemptStatus.RUNNING_WORKER)

    with app_harness.session_factory() as session:
        user_id = session.scalars(select(LocalUser.id)).first()
        assert user_id is not None
        tool_call = ToolCall(
            tool_name="attempt.follow_up",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="test",
            user_id=user_id,
            project_id=project_id,
            task_id=str(task_data["id"]),
            task_attempt_id=str(source["id"]),
            risk_level="R1",
            arguments_json={
                "task_attempt_id": str(source["id"]),
                "feedback": "Try again explicitly.",
            },
            status=ToolCallStatus.RUNNING,
        )
        session.add(tool_call)
        session.flush()

        result = execute_attempt_action_tool(session, tool_call)

    assert result == {"error": "active_attempt_exists"}
    assert tool_call.error_code == "active_attempt_exists"
    assert tool_call.error_message == (
        "Task already has an active or adopted attempt; explicit follow-up is blocked"
    )
