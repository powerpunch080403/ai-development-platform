from sqlalchemy import func, select
from aidp_server.db.models import (
    AgentRun,
    ApprovalRequest,
    Conversation,
    LocalUser,
    Task,
    TaskAttempt,
    ToolCall,
    ToolCallStatus,
    ToolCallerType,
    WorkerRun,
)
from conftest import AppHarness


def test_owner_task_traceability(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user = db_session.scalar(select(LocalUser).limit(1))

        conversation = Conversation(
            title="Trace Test",
            local_user_id=user.id,
            project_id=project_id,
        )
        db_session.add(conversation)
        db_session.flush()

        agent_run = AgentRun(
            conversation_id=conversation.id,
            local_user_id=user.id,
            project_id=project_id,
            purpose="Trace Task Create",
        )
        db_session.add(agent_run)
        db_session.flush()

        task = Task(
            local_user_id=user.id,
            project_id=project_id,
            title="Traced Task",
            instructions="Do something",
            write_scope_json={"paths": ["."]},
            risk_level="R1",
        )
        db_session.add(task)
        db_session.flush()

        tool_call = ToolCall(
            tool_name="task.create",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="codex_cli",
            user_id=user.id,
            agent_run_id=agent_run.id,
            project_id=project_id,
            risk_level="R1",
            arguments_json={
                "title": "Traced Task",
                "instructions": "Do something",
                "write_scope": ["."],
            },
            status=ToolCallStatus.SUCCEEDED,
            result_json={"task_id": task.id},
        )
        db_session.add(tool_call)
        db_session.commit()

        task_id = task.id
        agent_run_id = agent_run.id
        tool_call_id = tool_call.id

        worker_runs_before = db_session.scalar(select(func.count(WorkerRun.id)))
        attempts_before = db_session.scalar(select(func.count(TaskAttempt.id)))
        approvals_before = db_session.scalar(select(func.count(ApprovalRequest.id)))

    response = app_harness.client.get(f"/tasks/{task_id}/trace")
    assert response.status_code == 200
    data = response.json()

    assert data["task_id"] == task_id
    assert data["project_id"] == project_id
    source = data["source"]
    assert source is not None
    assert source["type"] == "owner_tool_call"
    assert source["tool_call_id"] == tool_call_id
    assert source["agent_run_id"] == agent_run_id
    assert source["tool_name"] == "task.create"
    assert source["provider_kind"] == "codex_cli"

    with app_harness.session_factory() as db_session:
        assert db_session.scalar(select(func.count(WorkerRun.id))) == worker_runs_before
        assert db_session.scalar(select(func.count(TaskAttempt.id))) == attempts_before
        assert db_session.scalar(select(func.count(ApprovalRequest.id))) == approvals_before


def test_owner_task_traceability_no_source(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user = db_session.scalar(select(LocalUser).limit(1))
        task = Task(
            local_user_id=user.id,
            project_id=project_id,
            title="Manual Task",
            instructions="Do something",
            write_scope_json={"paths": ["."]},
            risk_level="R1",
        )
        db_session.add(task)
        db_session.commit()
        task_id = task.id

    response = app_harness.client.get(f"/tasks/{task_id}/trace")
    assert response.status_code == 200
    data = response.json()

    assert data["task_id"] == task_id
    assert data["source"] is None


def test_owner_task_traceability_not_found(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate

    authenticate(app_harness)

    response = app_harness.client.get("/tasks/non-existent-task-id/trace")
    assert response.status_code == 404
