from conftest import AppHarness
from test_work_and_workers import authenticate, project, task


def test_work_room_messages_require_auth(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/tasks/missing/work-room/messages").status_code == 401
    assert app_harness.client.post("/tasks/missing/work-room/messages", json={}).status_code == 401


def test_work_room_message_create_list_and_workspace_projection(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness, "Work Room Project")
    created_task = task(app_harness, project_id)
    task_id = created_task["id"]
    attempt = app_harness.client.post(f"/tasks/{task_id}/attempts", json={}).json()

    created = app_harness.client.post(
        f"/tasks/{task_id}/work-room/messages",
        json={
            "task_attempt_id": attempt["id"],
            "sender": "owner",
            "message_type": "owner_feedback",
            "content": "이전 결과를 바탕으로 문장을 더 짧게 고쳐.",
            "metadata": {"source": "test"},
        },
    )
    assert created.status_code == 201, created.text
    created_message = created.json()
    assert created_message["task_id"] == task_id
    assert created_message["task_attempt_id"] == attempt["id"]
    assert created_message["sender"] == "owner"
    assert created_message["message_type"] == "owner_feedback"
    assert created_message["metadata"] == {"source": "test"}

    listed = app_harness.client.get(f"/tasks/{task_id}/work-room/messages")
    assert listed.status_code == 200, listed.text
    messages = listed.json()
    assert [message["id"] for message in messages] == [created_message["id"]]

    workspace = app_harness.client.get(f"/tasks/{task_id}/workspace")
    assert workspace.status_code == 200, workspace.text
    workspace_messages = workspace.json()["work_room_messages"]
    assert [message["id"] for message in workspace_messages] == [created_message["id"]]


def test_work_room_message_rejects_attempt_from_another_task(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness, "Work Room Scope")
    task_a = task(app_harness, project_id)
    task_b = task(app_harness, project_id)
    attempt_b = app_harness.client.post(f"/tasks/{task_b['id']}/attempts", json={}).json()

    response = app_harness.client.post(
        f"/tasks/{task_a['id']}/work-room/messages",
        json={
            "task_attempt_id": attempt_b["id"],
            "sender": "owner",
            "message_type": "owner_feedback",
            "content": "잘못된 task attempt 연결",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "task_attempt_id belongs to another task"
