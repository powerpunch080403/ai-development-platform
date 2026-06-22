from sqlalchemy import func, select

from aidp_server.cli import create_pairing_code
from aidp_server.db.models import (
    AccountLinkStatus,
    Conversation,
    ConversationStatus,
    LocalUser,
    Project,
    ProjectStatus,
    ToolRegistryEntry,
)
from aidp_server.tool_registry import TOOL_DEFINITIONS, seed_tool_registry
from conftest import AppHarness


def authenticate(harness: AppHarness) -> None:
    with harness.session_factory() as session:
        code, _ = create_pairing_code(session)
    response = harness.client.post(
        "/auth/pair",
        json={"code": code, "device_name": "Records tests", "device_type": "web_ui"},
    )
    assert response.status_code == 200


def create_project(harness: AppHarness) -> str:
    response = harness.client.post("/projects", json={"name": "Records Project"})
    assert response.status_code == 201
    return str(response.json()["id"])


def create_conversation(harness: AppHarness, project_id: str | None = None) -> dict[str, object]:
    response = harness.client.post(
        "/conversations", json={"project_id": project_id, "title": "README discussion"}
    )
    assert response.status_code == 201
    return response.json()  # type: ignore[no-any-return]


def test_conversation_api_requires_authentication(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/conversations").status_code == 401
    assert app_harness.client.post("/conversations", json={}).status_code == 401


def test_project_and_general_conversations_are_created_and_user_scoped(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    linked = create_conversation(app_harness, project_id)
    general = create_conversation(app_harness)

    assert linked["project_id"] == project_id
    assert general["project_id"] is None
    assert len(app_harness.client.get("/conversations").json()) == 2

    with app_harness.session_factory() as session:
        other = LocalUser(
            display_name="Other",
            account_id=None,
            account_link_status=AccountLinkStatus.LOCAL_ONLY,
        )
        session.add(other)
        session.flush()
        other_project = Project(local_user_id=other.id, name="Other", status=ProjectStatus.ACTIVE)
        session.add(other_project)
        session.flush()
        other_conversation = Conversation(
            local_user_id=other.id,
            project_id=other_project.id,
            title="Private",
            status=ConversationStatus.ACTIVE,
        )
        session.add(other_conversation)
        session.commit()
        other_project_id = other_project.id
        other_conversation_id = other_conversation.id

    assert app_harness.client.get(f"/conversations/{other_conversation_id}").status_code == 404
    assert (
        app_harness.client.post(
            "/conversations", json={"project_id": other_project_id, "title": "Nope"}
        ).status_code
        == 404
    )


def test_message_agent_run_status_and_step_records(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])
    message = app_harness.client.post(
        f"/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "Update README", "content_type": "text"},
    )
    assert message.status_code == 201
    messages = app_harness.client.get(f"/conversations/{conversation_id}/messages")
    assert messages.status_code == 200 and messages.json()[0]["content"] == "Update README"

    run = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "owner_request",
            "input_message_id": message.json()["id"],
        },
    )
    assert run.status_code == 201 and run.json()["status"] == "queued"
    run_id = run.json()["id"]
    changed = app_harness.client.post(
        f"/agent-runs/{run_id}/status", json={"status": "running_model"}
    )
    assert changed.status_code == 200 and changed.json()["started_at"] is not None
    completed = app_harness.client.post(
        f"/agent-runs/{run_id}/status", json={"status": "completed"}
    )
    assert completed.json()["completed_at"] is not None
    step = app_harness.client.post(
        f"/agent-runs/{run_id}/steps",
        json={"step_type": "model", "status": "succeeded", "summary": "Recorded only"},
    )
    assert step.status_code == 201 and step.json()["step_index"] == 0
    assert len(app_harness.client.get(f"/conversations/{conversation_id}/agent-runs").json()) == 1


def test_tool_registry_seed_is_idempotent(app_harness: AppHarness) -> None:
    with app_harness.session_factory() as session:
        seed_tool_registry(session)
        seed_tool_registry(session)
        count = session.scalar(select(func.count()).select_from(ToolRegistryEntry))
    assert count == len(TOOL_DEFINITIONS)


def test_tool_call_validation_status_and_audit(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    registry = app_harness.client.get("/tool-registry")
    assert registry.status_code == 200 and len(registry.json()) == len(TOOL_DEFINITIONS)

    missing_key = app_harness.client.post(
        "/tool-calls", json={"tool_name": "project.create", "arguments_json": {}}
    )
    assert missing_key.status_code == 400
    unknown = app_harness.client.post(
        "/tool-calls", json={"tool_name": "unknown.tool", "arguments_json": {}}
    )
    assert unknown.status_code == 400

    with app_harness.session_factory() as session:
        disabled = session.scalar(
            select(ToolRegistryEntry).where(ToolRegistryEntry.tool_name == "repository.check_dirty")
        )
        assert disabled is not None
        disabled.enabled = False
        session.commit()
    assert (
        app_harness.client.post(
            "/tool-calls",
            json={"tool_name": "repository.check_dirty", "arguments_json": {}},
        ).status_code
        == 400
    )

    created = app_harness.client.post(
        "/tool-calls",
        json={"tool_name": "repository.get_status", "arguments_json": {"repository_id": "x"}},
    )
    assert created.status_code == 201 and created.json()["status"] == "created"
    call_id = created.json()["id"]
    running = app_harness.client.post(f"/tool-calls/{call_id}/status", json={"status": "running"})
    assert running.status_code == 200 and running.json()["started_at"] is not None
    succeeded = app_harness.client.post(
        f"/tool-calls/{call_id}/status",
        json={"status": "succeeded", "result_ref": "record://result"},
    )
    assert succeeded.json()["completed_at"] is not None
    audit = app_harness.client.get("/audit-events")
    assert audit.status_code == 200
    assert {event["event_type"] for event in audit.json()} >= {
        "tool_call.created",
        "tool_call.status_changed",
    }
