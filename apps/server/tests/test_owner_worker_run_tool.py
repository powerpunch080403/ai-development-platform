from sqlalchemy import func, select
from aidp_server.db.models import (
    AgentRun,
    Conversation,
    LocalUser,
    Task,
    TaskAttempt,
    TaskAttemptStatus,
    ToolCall,
    ToolCallStatus,
    ToolCallerType,
    WorkerRun,
    RecordStatus,
    AuditEvent,
    Worker,
    WorkerStatus,
)
from aidp_server.owner_tools import execute_owner_tool
from conftest import AppHarness


def setup_test_data(db_session, project_id, adapter_kind="mock"):
    user = db_session.scalar(select(LocalUser).limit(1))
    conversation = Conversation(
        title="Run Tool Test",
        local_user_id=user.id,
        project_id=project_id,
    )
    db_session.add(conversation)
    db_session.flush()

    agent_run = AgentRun(
        conversation_id=conversation.id,
        local_user_id=user.id,
        project_id=project_id,
        purpose="Test worker.run_task_attempt",
    )
    db_session.add(agent_run)
    db_session.flush()

    task = Task(
        local_user_id=user.id,
        project_id=project_id,
        title="Test Task",
        instructions="Do something",
        write_scope_json={"paths": ["."]},
        risk_level="R1",
    )
    db_session.add(task)
    db_session.flush()

    worker = Worker(
        local_user_id=user.id,
        device_id="system",
        display_name=f"System {adapter_kind} Worker",
        worker_kind=adapter_kind,
        status=WorkerStatus.AVAILABLE,
        capabilities_json={},
    )
    db_session.add(worker)
    db_session.flush()

    attempt = TaskAttempt(
        task_id=task.id,
        local_user_id=user.id,
        project_id=project_id,
        repository_id=task.repository_id,
        worker_id=worker.id,
        claimed_by_worker_id=worker.id,
        status=TaskAttemptStatus.CREATED,
        attempt_number=1,
    )
    db_session.add(attempt)
    db_session.flush()

    worker_run = WorkerRun(
        local_user_id=user.id,
        project_id=project_id,
        repository_id=task.repository_id,
        task_id=task.id,
        task_attempt_id=attempt.id,
        worker_id=worker.id,
        adapter_kind=adapter_kind,
        status=RecordStatus.CREATED,
    )
    db_session.add(worker_run)
    db_session.flush()

    return user, agent_run, task, attempt, worker_run


def test_worker_run_task_attempt_success(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task, attempt, worker_run = setup_test_data(db_session, project_id)

        # Baseline counts
        tasks_before = db_session.scalar(select(func.count(Task.id)))
        attempts_before = db_session.scalar(select(func.count(TaskAttempt.id)))
        worker_runs_before = db_session.scalar(select(func.count(WorkerRun.id)))

        tool_call = ToolCall(
            tool_name="worker.run_task_attempt",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="codex_cli",
            user_id=user.id,
            agent_run_id=agent_run.id,
            project_id=project_id,
            risk_level="R1",
            arguments_json={"worker_run_id": worker_run.id},
            status=ToolCallStatus.CREATED,
        )
        db_session.add(tool_call)
        db_session.flush()

        result = execute_owner_tool(db_session, tool_call)
        db_session.commit()

        assert "status" in result
        assert result["status"] == "succeeded"
        assert result["task_attempt_id"] == attempt.id
        assert result["worker_run_id"] == worker_run.id
        assert result.get("fresh_worker_context") is True

        # Verify DB changes
        # No new records created
        assert db_session.scalar(select(func.count(Task.id))) == tasks_before
        assert db_session.scalar(select(func.count(TaskAttempt.id))) == attempts_before
        assert db_session.scalar(select(func.count(WorkerRun.id))) == worker_runs_before

        db_session.refresh(attempt)
        db_session.refresh(worker_run)

        # Verify statuses
        assert attempt.status == TaskAttemptStatus.ACCEPTED
        assert attempt.result_summary == "Mock execution completed by owner tool"

        assert worker_run.status == RecordStatus.SUCCEEDED
        assert worker_run.summary == "Mock execution completed by owner tool"

        # Verify audit event
        audit_event = db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type == "owner_tool_call.completed")
            .where(AuditEvent.tool_call_id == tool_call.id)
            .order_by(AuditEvent.created_at.desc())
        ).first()

        assert audit_event is not None
        assert audit_event.metadata_json is not None
        assert audit_event.metadata_json.get("fresh_worker_context") is True
        assert audit_event.metadata_json.get("previous_worker_context_reused") is False
        assert audit_event.metadata_json.get("continuity_source") == "owner_authored_task_packet"


def test_worker_run_unsupported_adapter(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        # Use mock for the worker to satisfy DB constraints, but 'manual' for the run
        user, agent_run, task, attempt, worker_run = setup_test_data(db_session, project_id, adapter_kind="mock")
        worker_run.adapter_kind = "manual"
        db_session.flush()

        tool_call = ToolCall(
            tool_name="worker.run_task_attempt",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="codex_cli",
            user_id=user.id,
            agent_run_id=agent_run.id,
            project_id=project_id,
            risk_level="R1",
            arguments_json={"worker_run_id": worker_run.id},
            status=ToolCallStatus.CREATED,
        )
        db_session.add(tool_call)
        db_session.flush()

        result = execute_owner_tool(db_session, tool_call)

        assert "error" in result
        assert result["error"] == "unsupported_worker_adapter"
        assert tool_call.status == ToolCallStatus.FAILED


def test_worker_run_missing_ids(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, _, _, _ = setup_test_data(db_session, project_id)

        tool_call = ToolCall(
            tool_name="worker.run_task_attempt",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="codex_cli",
            user_id=user.id,
            agent_run_id=agent_run.id,
            project_id=project_id,
            risk_level="R1",
            arguments_json={},  # Missing ids
            status=ToolCallStatus.CREATED,
        )
        db_session.add(tool_call)
        db_session.flush()

        result = execute_owner_tool(db_session, tool_call)

        assert "error" in result
        assert result["error"] == "invalid_arguments"
        assert tool_call.status == ToolCallStatus.FAILED


def test_worker_run_nonexistent_worker_run(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, _, _, _ = setup_test_data(db_session, project_id)

        tool_call = ToolCall(
            tool_name="worker.run_task_attempt",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="codex_cli",
            user_id=user.id,
            agent_run_id=agent_run.id,
            project_id=project_id,
            risk_level="R1",
            arguments_json={"worker_run_id": "fake-id"},
            status=ToolCallStatus.CREATED,
        )
        db_session.add(tool_call)
        db_session.flush()

        result = execute_owner_tool(db_session, tool_call)

        assert "error" in result
        assert result["error"] == "worker_run_not_found"
        assert tool_call.status == ToolCallStatus.FAILED
