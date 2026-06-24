import subprocess
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from aidp_server.db.models import AgentRun, AuditEvent, LocalUser, Task, TaskAttempt, ToolCall, ToolCallStatus
from conftest import AppHarness


@pytest.fixture
def db_agent_run(app_harness: AppHarness) -> AgentRun:
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as session:
        local_user_id = session.scalars(select(LocalUser.id)).first()
        run = AgentRun(
            local_user_id=local_user_id,
            project_id=project_id,
            purpose="test",
        )
        session.add(run)
        session.commit()
        run_id = run.id

    with app_harness.session_factory() as session:
        return session.get(AgentRun, run_id)


def test_project_list_creates_durable_record(app_harness: AppHarness, db_agent_run: AgentRun):
    response = app_harness.client.post(
        f"/agent-runs/{db_agent_run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "project.list",
            "arguments_json": {},
            "provider_call_id": "call_123",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["tool_name"] == "project.list"
    assert data["status"] == "succeeded"
    assert data["caller_type"] == "owner"

    with app_harness.session_factory() as session:
        call = session.get(ToolCall, data["id"])
        assert call is not None
        assert call.tool_name == "project.list"
        assert call.status == ToolCallStatus.SUCCEEDED
        assert call.caller_id == "codex_cli"
        assert call.correlation_id == "call_123"
        # 3. DB 조회하여 result JSON이 저장되어 있는지 확인
        assert call.result_json is not None
        assert "projects" in call.result_json


def test_task_list_returns_completed_result(app_harness: AppHarness, db_agent_run: AgentRun):
    response = app_harness.client.post(
        f"/agent-runs/{db_agent_run.id}/tool-calls",
        json={"provider_kind": "codex_cli", "tool_name": "task.list", "arguments_json": {}},
    )
    assert response.status_code == 201
    call_id = response.json()["id"]

    with app_harness.session_factory() as session:
        call = session.get(ToolCall, call_id)
        # 2. 조회한 ToolCall의 status가 succeeded 확인
        assert call.status == ToolCallStatus.SUCCEEDED
        # 3. 조회한 ToolCall에 result JSON이 저장되어 있는지 확인
        assert call.result_json is not None
        assert "tasks" in call.result_json


def test_task_create_creates_durable_record(app_harness: AppHarness, db_agent_run: AgentRun):
    response = app_harness.client.post(
        f"/agent-runs/{db_agent_run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "task.create",
            "arguments_json": {"title": "Fix something", "instructions": "Do it"},
        },
    )
    assert response.status_code == 201
    call_id = response.json()["id"]

    with app_harness.session_factory() as session:
        call = session.get(ToolCall, call_id)
        assert call.status == ToolCallStatus.SUCCEEDED
        assert call.result_json is not None
        assert "task_id" in call.result_json

        task = session.get(Task, call.result_json["task_id"])
        assert task is not None
        assert task.title == "Fix something"
        assert task.instructions == "Do it"
        assert task.project_id == db_agent_run.project_id


def test_task_create_stores_repository_id(app_harness: AppHarness, db_agent_run: AgentRun):
    """repository_id in arguments_json must be stored on Task and flow to TaskAttempt."""
    repo_dir = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo_dir, check=True)
    (Path(repo_dir) / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)

    project_id = db_agent_run.project_id
    r = app_harness.client.post(
        f"/projects/{project_id}/repositories",
        json={"repository_path": repo_dir, "repository_role": "primary"},
    )
    assert r.status_code == 201, r.json()
    repo_id = r.json()["id"]

    r = app_harness.client.post(
        f"/agent-runs/{db_agent_run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "task.create",
            "arguments_json": {
                "title": "Repo task",
                "instructions": "With repo",
                "repository_id": repo_id,
            },
        },
    )
    assert r.status_code == 201, r.json()
    task_id = r.json()["result_json"]["task_id"]

    with app_harness.session_factory() as session:
        task = session.get(Task, task_id)
        assert task is not None
        assert task.repository_id == repo_id, "repository_id must be stored on Task"

    r = app_harness.client.post(
        f"/agent-runs/{db_agent_run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "worker.start_task_attempt",
            "arguments_json": {"task_id": task_id, "worker_adapter": "mock"},
        },
    )
    assert r.status_code == 201, r.json()
    attempt_id = r.json()["result_json"]["task_attempt_id"]

    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, attempt_id)
        assert attempt is not None
        assert attempt.repository_id == repo_id, "repository_id must propagate to TaskAttempt"


def test_unknown_tool_is_rejected(app_harness: AppHarness, db_agent_run: AgentRun):
    response = app_harness.client.post(
        f"/agent-runs/{db_agent_run.id}/tool-calls",
        json={"provider_kind": "codex_cli", "tool_name": "some.unknown.tool", "arguments_json": {}},
    )
    assert response.status_code == 201
    data = response.json()

    with app_harness.session_factory() as session:
        call = session.get(ToolCall, data["id"])
        # 4. unknown tool 시 error/rejection reason이 DB에 저장되는지 확인
        assert call.status == ToolCallStatus.REJECTED
        assert call.error_code == "UNKNOWN_TOOL"
        assert call.error_message is not None


def test_side_effect_tool_is_rejected_in_slice(app_harness: AppHarness, db_agent_run: AgentRun):
    response = app_harness.client.post(
        f"/agent-runs/{db_agent_run.id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "work_item.create",
            "arguments_json": {"title": "Fix something"},
        },
    )
    assert response.status_code == 201
    data = response.json()

    with app_harness.session_factory() as session:
        call = session.get(ToolCall, data["id"])
        # 4. side-effect tool rejected 시 error/rejection reason이 DB에 저장되는지 확인
        assert call.status == ToolCallStatus.REJECTED
        assert call.error_code == "NOT_IMPLEMENTED_IN_SLICE"
        assert call.error_message is not None


def test_authority_applied_audit_metadata(app_harness: AppHarness, db_agent_run: AgentRun):
    response = app_harness.client.post(
        f"/agent-runs/{db_agent_run.id}/tool-calls",
        json={"provider_kind": "codex_cli", "tool_name": "project.list", "arguments_json": {}},
    )
    assert response.status_code == 201
    call_id = response.json()["id"]

    with app_harness.session_factory() as session:
        events = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.tool_call_id == call_id)
            .order_by(AuditEvent.created_at.asc())
        ).all()

        types = [e.event_type for e in events]
        assert "owner_tool_call.recorded" in types
        assert "owner_tool_call.authority_applied" in types
        assert "owner_tool_call.completed" in types

        auth_event = next(e for e in events if e.event_type == "owner_tool_call.authority_applied")
        meta = auth_event.metadata_json
        assert meta["mode"] == "personal"
        assert meta["authority_applied"] is True
        assert meta["owner_judgment_replaced"] is False
        assert meta["side_effect"] is False
