from sqlalchemy import select

from aidp_server.db.models import (
    AgentRun,
    ProjectRepository,
    RepositoryRole,
    ToolCall,
    ToolCallStatus,
    VcsType,
)
from aidp_server.owner.context_builder import build_owner_context, summarize_owner_context
from conftest import AppHarness
from test_conversations_and_tools import authenticate, create_conversation, create_project


def _create_run(app_harness: AppHarness, project_id: str, conversation_id: str) -> str:
    message = app_harness.client.post(
        f"/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "Please inspect the project", "content_type": "text"},
    )
    assert message.status_code == 201

    run = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "owner_context",
            "input_message_id": message.json()["id"],
        },
    )
    assert run.status_code == 201
    return str(run.json()["id"])


def test_owner_context_builder_returns_provider_agnostic_context(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])
    run_id = _create_run(app_harness, project_id, conversation_id)

    task_resp = app_harness.client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Context task",
            "instructions": "Use this task in context.",
            "write_scope": {
                "mode": "paths",
                "paths": ["apps/server/"],
                "allow_new_files": True,
            },
        },
    )
    assert task_resp.status_code == 201, task_resp.json()

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        repository = ProjectRepository(
            project_id=project_id,
            local_user_id=run.local_user_id,
            repository_path="C:/tmp/context-repo",
            repository_name="context-repo",
            repository_role=RepositoryRole.PRIMARY,
            vcs_type=VcsType.GIT,
            default_branch="main",
            current_branch="main",
            last_commit_sha="abc123",
            is_dirty=False,
        )
        session.add(repository)
        session.commit()

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        context = build_owner_context(session, run)
        summary = summarize_owner_context(context)

    assert context["context_version"] == "owner_context.v1"
    assert context["provider_agnostic"] is True
    assert context["agent_run"]["id"] == run_id
    assert context["project"]["id"] == project_id
    assert context["conversation"]["id"] == conversation_id
    assert context["conversation"]["latest_messages"][-1]["content"] == "Please inspect the project"
    assert context["repositories"][0]["repository_name"] == "context-repo"
    assert context["repositories"][0]["repository_path"] == "C:/tmp/context-repo"
    assert context["tasks"][0]["title"] == "Context task"
    assert context["authority"]["mode"] == "personal"
    assert context["authority"]["owner_judgment_replaced"] is False

    tool_names = {tool["tool_name"] for tool in context["tool_definitions"]}
    assert {"project.list", "repository.list", "task.list", "task.create"} <= tool_names
    assert summary["context_version"] == "owner_context.v1"
    assert summary["project_id"] == project_id
    assert summary["repository_count"] == 1
    assert summary["task_count"] == 1
    assert summary["authority_mode"] == "personal"


def test_repository_list_owner_tool_creates_durable_read_only_tool_call(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    run_id = _create_run(app_harness, project_id, str(conversation["id"]))

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        repository = ProjectRepository(
            project_id=project_id,
            local_user_id=run.local_user_id,
            repository_path="C:/tmp/read-tool-repo",
            repository_name="read-tool-repo",
            repository_role=RepositoryRole.PRIMARY,
            vcs_type=VcsType.GIT,
            default_branch="main",
            current_branch="feature",
            last_commit_sha="def456",
            is_dirty=True,
        )
        session.add(repository)
        session.commit()

    response = app_harness.client.post(
        f"/agent-runs/{run_id}/tool-calls",
        json={
            "provider_kind": "fake",
            "tool_name": "repository.list",
            "arguments_json": {},
            "provider_call_id": "fake-repository-list",
        },
    )
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["tool_name"] == "repository.list"
    assert data["status"] == "succeeded"
    assert data["risk_level"] == "R0"
    assert data["result_json"]["repositories"][0]["repository_name"] == "read-tool-repo"
    assert data["result_json"]["repositories"][0]["current_branch"] == "feature"

    with app_harness.session_factory() as session:
        call = session.get(ToolCall, data["id"])
        assert call is not None
        assert call.status is ToolCallStatus.SUCCEEDED
        assert call.caller_id == "fake"
        assert call.correlation_id == "fake-repository-list"
        assert call.result_json["repositories"][0]["repository_path"] == "C:/tmp/read-tool-repo"


def test_fake_provider_receives_owner_context_summary_without_side_effects(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_fake_owner_provider = True
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    run_id = _create_run(app_harness, project_id, str(conversation["id"]))

    response = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "fake"},
    )
    assert response.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        context_summary = run.provider_metadata_json["owner_context"]
        assert context_summary["context_version"] == "owner_context.v1"
        assert context_summary["provider_agnostic"] is True
        assert context_summary["project_id"] == project_id
        assert context_summary["conversation_id"] == str(conversation["id"])
        assert context_summary["authority_mode"] == "personal"
