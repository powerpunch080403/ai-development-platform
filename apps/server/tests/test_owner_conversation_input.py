from sqlalchemy import select

from aidp_server.db.models import Task, WorkerRun
from conftest import AppHarness
from test_conversations_and_tools import authenticate, create_conversation, create_project


def test_owner_conversation_input_rejects_empty_payload(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    # Invalid payload (empty)
    response = app_harness.client.post(
        f"/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "", "content_type": "text"},
    )
    assert response.status_code == 422  # validation error

    # Invalid payload (no role)
    response2 = app_harness.client.post(
        f"/conversations/{conversation_id}/messages",
        json={"content": "Hello", "content_type": "text"},
    )
    assert response2.status_code == 422


def test_keyword_routing_is_prohibited_and_does_not_create_task_or_worker_run(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    # Send a keyword-like message
    keyword_message = "이어서 해줘"
    message_resp = app_harness.client.post(
        f"/conversations/{conversation_id}/messages",
        json={"role": "user", "content": keyword_message, "content_type": "text"},
    )
    assert message_resp.status_code == 201
    message_id = message_resp.json()["id"]

    # Create an AgentRun
    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": keyword_message,
            "input_message_id": message_id,
        },
    )
    assert run_resp.status_code == 201
    assert run_resp.json()["status"] == "queued"

    # Verify that no Tasks or WorkerRuns were magically created by keyword routing
    with app_harness.session_factory() as session:
        tasks = session.scalars(select(Task).where(Task.project_id == project_id)).all()
        assert len(tasks) == 0, "Tasks should not be created automatically by keyword messages"

        worker_runs = session.scalars(select(WorkerRun).where(WorkerRun.project_id == project_id)).all()
        assert len(worker_runs) == 0, "WorkerRuns should not be created automatically by keyword messages"
