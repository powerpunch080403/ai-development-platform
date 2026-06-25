from aidp_server.db.models import TaskAttempt, TaskAttemptStatus
from conftest import AppHarness
from test_work_and_workers import authenticate, project, task


def _attempt(app_harness: AppHarness, task_id: str, status: TaskAttemptStatus) -> dict[str, object]:
    created = app_harness.client.post(f"/tasks/{task_id}/attempts", json={})
    assert created.status_code == 201, created.text
    attempt = created.json()
    with app_harness.session_factory() as session:
        row = session.get(TaskAttempt, attempt["id"])
        assert row is not None
        row.status = status
        session.commit()
    return attempt


def test_attempt_actions_require_auth(app_harness: AppHarness) -> None:
    assert app_harness.client.post("/task-attempts/missing/accept", json={}).status_code == 401
    assert app_harness.client.post("/task-attempts/missing/reject", json={}).status_code == 401
    assert app_harness.client.post("/task-attempts/missing/follow-up", json={}).status_code == 401


def test_accept_attempt_records_work_room_message(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness, "Accept Attempt")
    created_task = task(app_harness, project_id)
    attempt = _attempt(app_harness, created_task["id"], TaskAttemptStatus.COMMITTED)

    response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/accept",
        json={"review_summary": "결과를 채택한다."},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["attempt"]["status"] == "accepted"
    assert data["attempt"]["result_summary"] == "결과를 채택한다."
    assert data["work_room_message"]["message_type"] == "system_event"
    assert data["work_room_message"]["metadata"] == {"action": "accept"}

    workspace = app_harness.client.get(f"/tasks/{created_task['id']}/workspace")
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["work_room_messages"][0]["id"] == data["work_room_message"]["id"]


def test_reject_attempt_records_owner_feedback(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness, "Reject Attempt")
    created_task = task(app_harness, project_id)
    attempt = _attempt(app_harness, created_task["id"], TaskAttemptStatus.REVIEWING)

    response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/reject",
        json={"reason": "오너 의도와 다르므로 폐기한다."},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["attempt"]["status"] == "rejected"
    assert data["attempt"]["result_summary"] == "오너 의도와 다르므로 폐기한다."
    assert data["work_room_message"]["sender"] == "owner"
    assert data["work_room_message"]["message_type"] == "owner_feedback"
    assert data["work_room_message"]["content"] == "오너 의도와 다르므로 폐기한다."


def test_follow_up_creates_new_attempt_under_same_task(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness, "Follow Up Attempt")
    created_task = task(app_harness, project_id)
    source_attempt = _attempt(app_harness, created_task["id"], TaskAttemptStatus.COMMITTED)

    response = app_harness.client.post(
        f"/task-attempts/{source_attempt['id']}/follow-up",
        json={"feedback": "기존 결과를 참고해서 표현을 더 짧게 고쳐."},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source_attempt"]["status"] == "rejected"
    assert data["follow_up_attempt"]["task_id"] == created_task["id"]
    assert data["follow_up_attempt"]["attempt_number"] == 2
    assert data["follow_up_attempt"]["status"] == "created"
    assert data["work_room_message"]["task_attempt_id"] == data["follow_up_attempt"]["id"]
    metadata = data["work_room_message"]["metadata"]
    assert metadata["action"] == "follow_up"
    assert metadata["source_attempt_id"] == source_attempt["id"]
    assert metadata["explicit_retry"] is True
    assert metadata["automatic_retry"] is False
    
    attempts = app_harness.client.get(f"/tasks/{created_task['id']}/attempts")
    assert [attempt["attempt_number"] for attempt in attempts.json()] == [1, 2]


def test_attempt_action_rejects_non_reviewable_attempt(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness, "Non Reviewable Attempt")
    created_task = task(app_harness, project_id)
    attempt = _attempt(app_harness, created_task["id"], TaskAttemptStatus.CREATED)

    response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/accept",
        json={"review_summary": "아직 채택할 수 없다."},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Attempt is not reviewable"
