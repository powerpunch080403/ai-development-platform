import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import func, select

from aidp_server.db.models import (
    AgentRun,
    AgentRunStep,
    AgentRunStatus,
    ApprovalRequest,
    AuditEvent,
    Task,
    TaskStatus,
    ToolCall,
    ToolCallerType,
    ToolCallStatus,
    WorkerRun,
)
from conftest import AppHarness
from test_conversations_and_tools import authenticate, create_conversation, create_project


def test_fake_scripted_owner_provider_creates_task_through_tool_loop(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_fake_owner_provider = True
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Scripted task.create",
        },
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        run.provider_metadata_json = {
            "scripted_tool_request": {
                "tool_name": "task.create",
                "provider_call_id": "fake-call-task-create",
                "arguments_json": {
                    "title": "Scripted Owner Task",
                    "instructions": "Create this through ToolCall only.",
                    "write_scope": {
                        "mode": "paths",
                        "paths": ["apps/server/"],
                        "allow_new_files": True,
                    },
                },
            }
        }
        session.commit()

    worker_runs_before = 0
    approvals_before = 0
    with app_harness.session_factory() as session:
        worker_runs_before = session.scalar(select(func.count(WorkerRun.id))) or 0
        approvals_before = session.scalar(select(func.count(ApprovalRequest.id))) or 0

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "fake"},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == AgentRunStatus.RUNNING_MODEL.value

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status is AgentRunStatus.COMPLETED
        assert run.provider_kind == "fake"
        assert run.provider_metadata_json["tool_loop_executed"] is True
        assert run.provider_metadata_json["task_side_effects_performed"] is True
        assert run.provider_metadata_json["worker_side_effects_performed"] is False
        assert run.provider_metadata_json["approval_side_effects_performed"] is False

        call = session.scalar(select(ToolCall).where(ToolCall.agent_run_id == run_id))
        assert call is not None
        assert call.tool_name == "task.create"
        assert call.caller_type is ToolCallerType.OWNER
        assert call.caller_id == "fake"
        assert call.correlation_id == "fake-call-task-create"
        assert call.status is ToolCallStatus.SUCCEEDED
        assert call.result_json is not None
        assert "task_id" in call.result_json

        task = session.get(Task, call.result_json["task_id"])
        assert task is not None
        assert task.status is TaskStatus.DRAFT
        assert task.title == "Scripted Owner Task"
        assert task.project_id == project_id
        assert task.agent_run_id == run_id
        assert task.write_scope_json == {
            "mode": "paths",
            "paths": ["apps/server/"],
            "allow_new_files": True,
            "allow_protected_paths": False,
        }

        step = session.scalar(select(AgentRunStep).where(AgentRunStep.agent_run_id == run_id))
        assert step is not None
        assert step.step_type.value == "tool_call"
        assert step.status.value == "succeeded"
        assert step.provider_kind == "fake"
        assert step.provider_metadata_json["tool_call_id"] == call.id
        assert step.provider_metadata_json["tool_status"] == "succeeded"

        audit_types = {
            event.event_type
            for event in session.scalars(
                select(AuditEvent).where(AuditEvent.agent_run_id == run_id)
            )
        }
        assert "owner_tool_call.recorded" in audit_types
        assert "owner_tool_call.authority_applied" in audit_types
        assert "owner_tool_call.completed" in audit_types
        assert "task.created" in audit_types

        assert session.scalar(select(func.count(WorkerRun.id))) == worker_runs_before
        assert session.scalar(select(func.count(ApprovalRequest.id))) == approvals_before


def test_fake_scripted_owner_provider_failed_tool_call_does_not_create_task(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_fake_owner_provider = True
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Invalid scripted task.create",
        },
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        run.provider_metadata_json = {
            "scripted_tool_request": {
                "tool_name": "task.create",
                "provider_call_id": "fake-call-invalid-scope",
                "arguments_json": {
                    "title": "Bad task",
                    "instructions": "Should not persist.",
                    "write_scope": {
                        "mode": "paths",
                        "paths": ["../outside"],
                    },
                },
            }
        }
        session.commit()

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "fake"},
    )
    assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status is AgentRunStatus.FAILED
        assert run.error_category == "tool_call_failed"
        assert run.provider_metadata_json["tool_loop_executed"] is True

        call = session.scalar(select(ToolCall).where(ToolCall.agent_run_id == run_id))
        assert call is not None
        assert call.status is ToolCallStatus.FAILED
        assert call.error_code == "WRITE_SCOPE_INVALID"

        task = session.scalar(select(Task).where(Task.agent_run_id == run_id))
        assert task is None

def test_fake_scripted_owner_provider_rejects_repository_from_another_project(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_fake_owner_provider = True

    project_id = create_project(app_harness)
    other_project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    repo_dir = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo_dir, check=True)
    (Path(repo_dir) / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)

    repo_resp = app_harness.client.post(
        f"/projects/{other_project_id}/repositories",
        json={"repository_path": repo_dir, "repository_role": "primary"},
    )
    assert repo_resp.status_code == 201, repo_resp.json()
    other_repo_id = repo_resp.json()["id"]

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Reject cross-project repository",
        },
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        run.provider_metadata_json = {
            "scripted_tool_request": {
                "tool_name": "task.create",
                "provider_call_id": "fake-call-cross-project-repo",
                "arguments_json": {
                    "title": "Cross project task",
                    "instructions": "Should be rejected.",
                    "repository_id": other_repo_id,
                },
            }
        }
        session.commit()

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "fake"},
    )
    assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status is AgentRunStatus.FAILED
        assert run.error_category == "tool_call_failed"
        assert run.provider_metadata_json["tool_loop_executed"] is True

        call = session.scalar(select(ToolCall).where(ToolCall.agent_run_id == run_id))
        assert call is not None
        assert call.status is ToolCallStatus.FAILED
        assert call.error_code == "project_mismatch"
        assert "belongs to another project" in (call.error_message or "")

        task = session.scalar(select(Task).where(Task.agent_run_id == run_id))
        assert task is None
