from sqlalchemy import select
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
from fastapi import BackgroundTasks


class MockBackgroundTasks(BackgroundTasks):
    def __init__(self):
        super().__init__()
        self.tasks_added = []

    def add_task(self, func, *args, **kwargs):
        self.tasks_added.append((func, args, kwargs))


def setup_test_data(db_session, project_id, adapter_kind="agy"):
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
        purpose="Test worker.run_task_attempt AGY gate",
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
        display_name="System worker",
        worker_kind="mock",  # use mock to avoid DB constraint on worker_kind, but the run adapter will be agy
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


def test_agy_worker_run_gate_disabled(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task, attempt, worker_run = setup_test_data(
            db_session, project_id, adapter_kind="agy"
        )

        # default settings has allow_owner_agy_worker_run = False
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
        db_session.flush()

        assert "error" in result
        assert result["error"] == "agy_worker_disabled"
        assert result["adapter"] == "agy"
        assert result["gate"] == "disabled"
        assert result.get("fresh_worker_context") is True
        assert result.get("previous_worker_context_reused") is False

        assert tool_call.status == ToolCallStatus.FAILED
        assert tool_call.error_code == "agy_worker_disabled"

        db_session.refresh(attempt)
        db_session.refresh(worker_run)

        assert worker_run.status == RecordStatus.CREATED
        assert attempt.status == TaskAttemptStatus.CREATED

        audit_event = db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type == "owner_tool_call.rejected")
            .where(AuditEvent.tool_call_id == tool_call.id)
            .order_by(AuditEvent.created_at.desc())
        ).first()

        assert audit_event is not None
        assert audit_event.metadata_json is not None
        assert audit_event.metadata_json.get("gate") == "disabled"
        assert audit_event.metadata_json.get("fresh_worker_context") is True
        assert audit_event.metadata_json.get("previous_worker_context_reused") is False


def test_agy_worker_run_gate_cannot_be_enabled_by_payload(app_harness: AppHarness):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task, attempt, worker_run = setup_test_data(
            db_session, project_id, adapter_kind="agy"
        )

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
            arguments_json={
                "worker_run_id": worker_run.id,
                "allow_owner_agy_worker_run": True,
            },  # payload override attempt
            status=ToolCallStatus.CREATED,
        )
        db_session.add(tool_call)
        db_session.flush()

        result = execute_owner_tool(db_session, tool_call)

        assert "error" in result
        assert result["error"] == "agy_worker_disabled"
        assert tool_call.status == ToolCallStatus.FAILED


def test_agy_worker_run_gate_enabled_without_helper(app_harness: AppHarness, monkeypatch):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    from aidp_server.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "allow_owner_agy_worker_run", True)

    with app_harness.session_factory() as db_session:
        user, agent_run, task, attempt, worker_run = setup_test_data(
            db_session, project_id, adapter_kind="agy"
        )

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

        import aidp_server.worker_execution

        class MockWorkerExecutionService:
            def run_task_attempt(self, *args, **kwargs):
                raise NotImplementedError(
                    "Owner-triggered AGY worker handoff is not implemented yet."
                )

        def mock_get_worker_execution_service(*args, **kwargs):
            return MockWorkerExecutionService()

        monkeypatch.setattr(
            aidp_server.worker_execution,
            "get_worker_execution_service",
            mock_get_worker_execution_service,
        )

        bg_tasks = MockBackgroundTasks()
        result = execute_owner_tool(db_session, tool_call, background_tasks=bg_tasks)
        db_session.commit()

        assert "error" in result
        assert result["error"] == "agy_handoff_not_implemented"
        assert result["adapter"] == "agy"
        assert result.get("fresh_worker_context") is True
        assert result.get("previous_worker_context_reused") is False

        assert tool_call.status == ToolCallStatus.FAILED
        assert tool_call.error_code == "agy_handoff_not_implemented"

        db_session.refresh(attempt)
        db_session.refresh(worker_run)

        # states remain CREATED
        assert worker_run.status == RecordStatus.CREATED
        assert attempt.status == TaskAttemptStatus.CREATED

        audit_event = db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type == "owner_tool_call.rejected")
            .where(AuditEvent.tool_call_id == tool_call.id)
            .order_by(AuditEvent.created_at.desc())
        ).first()

        assert audit_event is not None
        assert audit_event.metadata_json is not None
        assert audit_event.metadata_json.get("error") == "agy_handoff_not_implemented"
        assert audit_event.metadata_json.get("adapter") == "agy"


def test_agy_worker_run_gate_enabled_with_helper(app_harness: AppHarness, monkeypatch):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    from aidp_server.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "allow_owner_agy_worker_run", True)

    import aidp_server.worker_execution

    class MockWorkerExecutionService:
        def run_task_attempt(self, session, worker_run, task_attempt, task, tool_call, settings):
            from aidp_server.db.models import RecordStatus, TaskAttemptStatus

            worker_run.status = RecordStatus.RUNNING
            task_attempt.status = TaskAttemptStatus.RUNNING_WORKER
            session.flush()
            return {
                "task_attempt_id": task_attempt.id,
                "worker_run_id": worker_run.id,
                "status": "handoff_started",
                "adapter": "agy",
                "fresh_worker_context": True,
                "previous_worker_context_reused": False,
            }

    def mock_get_worker_execution_service(*args, **kwargs):
        return MockWorkerExecutionService()

    monkeypatch.setattr(
        aidp_server.worker_execution,
        "get_worker_execution_service",
        mock_get_worker_execution_service,
    )

    with app_harness.session_factory() as db_session:
        user, agent_run, task, attempt, worker_run = setup_test_data(
            db_session, project_id, adapter_kind="agy"
        )

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

        bg_tasks = MockBackgroundTasks()
        result = execute_owner_tool(db_session, tool_call, background_tasks=bg_tasks)
        db_session.commit()

        assert "status" in result
        assert result["status"] == "handoff_started"
        assert result["adapter"] == "agy"
        assert result["task_attempt_id"] == attempt.id
        assert result["worker_run_id"] == worker_run.id
        assert result.get("fresh_worker_context") is True
        assert result.get("previous_worker_context_reused") is False

        db_session.refresh(attempt)
        db_session.refresh(worker_run)

        assert worker_run.status == RecordStatus.RUNNING
        assert attempt.status == TaskAttemptStatus.RUNNING_WORKER

        audit_event = db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type == "owner_tool_call.completed")
            .where(AuditEvent.tool_call_id == tool_call.id)
            .order_by(AuditEvent.created_at.desc())
        ).first()

        assert audit_event is not None
        assert audit_event.metadata_json is not None
        assert audit_event.metadata_json.get("adapter") == "agy"
        assert audit_event.metadata_json.get("fresh_worker_context") is True
        assert audit_event.metadata_json.get("previous_worker_context_reused") is False
