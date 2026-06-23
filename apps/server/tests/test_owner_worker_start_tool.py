from sqlalchemy import func, select
from aidp_server.db.models import (
    AgentRun,
    ApprovalRequest,
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
)
from aidp_server.owner_tools import execute_owner_tool
from conftest import AppHarness


def setup_test_data(db_session, project_id):
    user = db_session.scalar(select(LocalUser).limit(1))
    conversation = Conversation(
        title="Start Tool Test",
        local_user_id=user.id,
        project_id=project_id,
    )
    db_session.add(conversation)
    db_session.flush()

    agent_run = AgentRun(
        conversation_id=conversation.id,
        local_user_id=user.id,
        project_id=project_id,
        purpose="Test worker.start_task_attempt",
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

    return user, agent_run, task


def test_worker_start_task_attempt_success(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task = setup_test_data(db_session, project_id)

        # Baseline counts
        attempts_before = db_session.scalar(select(func.count(TaskAttempt.id)))
        worker_runs_before = db_session.scalar(select(func.count(WorkerRun.id)))
        approvals_before = db_session.scalar(select(func.count(ApprovalRequest.id)))

        tool_call = ToolCall(
            tool_name="worker.start_task_attempt",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="codex_cli",
            user_id=user.id,
            agent_run_id=agent_run.id,
            project_id=project_id,
            risk_level="R1",
            arguments_json={"task_id": task.id, "worker_adapter": "mock"},
            status=ToolCallStatus.CREATED,
        )
        db_session.add(tool_call)
        db_session.flush()

        result = execute_owner_tool(db_session, tool_call)
        db_session.commit()

        # 3. ToolCall result_json contains task_attempt_id and worker_run_id.
        assert "task_attempt_id" in result
        assert "worker_run_id" in result

        task_attempt_id = result["task_attempt_id"]
        worker_run_id = result["worker_run_id"]

        # Verify DB changes
        # 1. worker.start_task_attempt ToolCall creates TaskAttempt durable record.
        # 2. worker.start_task_attempt ToolCall creates WorkerRun durable record.
        assert db_session.scalar(select(func.count(TaskAttempt.id))) == attempts_before + 1
        assert db_session.scalar(select(func.count(WorkerRun.id))) == worker_runs_before + 1

        # 11. worker.start_task_attempt does not create Review/Merge/Cleanup side effects.
        assert db_session.scalar(select(func.count(ApprovalRequest.id))) == approvals_before

        attempt = db_session.get(TaskAttempt, task_attempt_id)
        assert attempt is not None
        assert attempt.task_id == task.id

        # 6. WorkerRun/TaskAttempt status is queued/created, not completed.
        assert attempt.status == TaskAttemptStatus.CREATED

        worker_run = db_session.get(WorkerRun, worker_run_id)
        assert worker_run is not None
        assert worker_run.task_attempt_id == task_attempt_id
        assert worker_run.status == RecordStatus.CREATED
        assert worker_run.adapter_kind == "mock"

        # Audit event checks
        # 4. AuditEvent includes fresh_worker_context=true.
        # 5. AuditEvent includes previous_worker_context_reused=false.
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


def test_worker_start_unsupported_adapter(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task = setup_test_data(db_session, project_id)

        tool_call = ToolCall(
            tool_name="worker.start_task_attempt",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="codex_cli",
            user_id=user.id,
            agent_run_id=agent_run.id,
            project_id=project_id,
            risk_level="R1",
            arguments_json={"task_id": task.id, "worker_adapter": "agy"},
            status=ToolCallStatus.CREATED,
        )
        db_session.add(tool_call)
        db_session.flush()

        result = execute_owner_tool(db_session, tool_call)

        # 8. unsupported adapter "agy" is rejected.
        assert "error" in result
        assert result["error"] == "unsupported_worker_adapter"
        assert tool_call.status == ToolCallStatus.FAILED
        assert tool_call.error_code == "unsupported_worker_adapter"


def test_worker_start_missing_task_id(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task = setup_test_data(db_session, project_id)

        tool_call = ToolCall(
            tool_name="worker.start_task_attempt",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="codex_cli",
            user_id=user.id,
            agent_run_id=agent_run.id,
            project_id=project_id,
            risk_level="R1",
            arguments_json={"worker_adapter": "mock"},  # Missing task_id
            status=ToolCallStatus.CREATED,
        )
        db_session.add(tool_call)
        db_session.flush()

        result = execute_owner_tool(db_session, tool_call)

        # 9. missing task_id is rejected with invalid_arguments.
        assert "error" in result
        assert result["error"] == "task_id is required"
        assert tool_call.status == ToolCallStatus.FAILED
        assert tool_call.error_code == "invalid_arguments"


def test_worker_start_nonexistent_task(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, _ = setup_test_data(db_session, project_id)

        tool_call = ToolCall(
            tool_name="worker.start_task_attempt",
            tool_version="1.0",
            tool_category="owner",
            caller_type=ToolCallerType.OWNER,
            caller_id="codex_cli",
            user_id=user.id,
            agent_run_id=agent_run.id,
            project_id=project_id,
            risk_level="R1",
            arguments_json={"task_id": "non-existent-task-id", "worker_adapter": "mock"},
            status=ToolCallStatus.CREATED,
        )
        db_session.add(tool_call)
        db_session.flush()

        result = execute_owner_tool(db_session, tool_call)

        # 10. nonexistent task_id is rejected with task_not_found.
        assert "error" in result
        assert result["error"] == "task_not_found"
        assert tool_call.status == ToolCallStatus.FAILED
        assert tool_call.error_code == "task_not_found"
