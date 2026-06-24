import pytest
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
    Worker,
    WorkerStatus,
)
from aidp_server.worker_execution import get_worker_execution_service, background_agy_runner
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
        purpose="Test worker.run_task_attempt AGY handoff boundary",
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
        worker_kind="mock",  # using mock to satisfy DB constraint
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
        status=TaskAttemptStatus.QUEUED_WORKER,
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
        status=RecordStatus.QUEUED,
    )
    db_session.add(worker_run)
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

    return user, agent_run, task, attempt, worker_run, tool_call


def test_handoff_agy_worker_run_schedules_background_task(app_harness: AppHarness, monkeypatch):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    from aidp_server.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "allow_owner_agy_worker_run", True)

    with app_harness.session_factory() as db_session:
        user, agent_run, task, attempt, worker_run, tool_call = setup_test_data(db_session, project_id, adapter_kind="agy")

        bg_tasks = MockBackgroundTasks()

        exec_service = get_worker_execution_service(bg_tasks)
        result = exec_service.run_task_attempt(
            session=db_session,
            worker_run=worker_run,
            task_attempt=attempt,
            task=task,
            tool_call=tool_call,
            settings=settings,
        )

        assert result["status"] == "handoff_started"
        assert result["adapter"] == "agy"
        assert result["fresh_worker_context"] is True
        assert result["task_attempt_id"] == attempt.id
        assert result["worker_run_id"] == worker_run.id

        # State updates
        assert worker_run.status == RecordStatus.RUNNING
        assert attempt.status == TaskAttemptStatus.RUNNING_WORKER

        # Ensure background task was scheduled
        assert len(bg_tasks.tasks_added) == 1
        scheduled_func, scheduled_args, scheduled_kwargs = bg_tasks.tasks_added[0]
        assert scheduled_func == background_agy_runner
        assert scheduled_kwargs.get("worker_run_id") == worker_run.id


@pytest.mark.anyio
async def test_background_agy_runner_calls_existing_boundary(app_harness: AppHarness, monkeypatch):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    from aidp_server.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "allow_owner_agy_worker_run", True)

    with app_harness.session_factory() as db_session:
        user, agent_run, task, attempt, worker_run, tool_call = setup_test_data(db_session, project_id, adapter_kind="agy")
        worker_run_id = worker_run.id
        db_session.commit()

    # Mock run_existing_agy_worker_run
    called_with = {}
    async def mock_run_existing(session, settings, worker_run_arg):
        called_with["worker_run_id"] = worker_run_arg.id
        return {"status": "handoff_started"}

    import aidp_server.worker_execution
    monkeypatch.setattr(aidp_server.worker_execution, "run_existing_agy_worker_run", mock_run_existing)
    monkeypatch.setattr(aidp_server.worker_execution, "get_session_factory", lambda: app_harness.session_factory)

    # Call the background task directly
    await background_agy_runner(worker_run_id=worker_run_id)

    # Verify that the mocked helper was called
    assert "worker_run_id" in called_with
    assert called_with["worker_run_id"] == worker_run_id


@pytest.mark.anyio
async def test_background_agy_runner_handles_exception(app_harness: AppHarness, monkeypatch):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task, attempt, worker_run, tool_call = setup_test_data(db_session, project_id, adapter_kind="agy")
        worker_run_id = worker_run.id
        db_session.commit()

    # Mock run_existing_agy_worker_run to raise an exception
    async def mock_run_existing(session, settings, worker_run_arg):
        raise RuntimeError("Mock failure in agy handoff")

    import aidp_server.worker_execution
    monkeypatch.setattr(aidp_server.worker_execution, "run_existing_agy_worker_run", mock_run_existing)
    monkeypatch.setattr(aidp_server.worker_execution, "get_session_factory", lambda: app_harness.session_factory)

    # Call the background task directly
    await background_agy_runner(worker_run_id=worker_run_id)

    # Verify that the DB state was updated to FAILED
    with app_harness.session_factory() as db_session:
        worker_run = db_session.get(WorkerRun, worker_run_id)
        assert worker_run.status == RecordStatus.FAILED
        assert worker_run.error_message == "Mock failure in agy handoff"

        attempt = db_session.get(TaskAttempt, worker_run.task_attempt_id)
        assert attempt.status == TaskAttemptStatus.WORKER_FAILED


@pytest.mark.anyio
async def test_background_agy_runner_handles_empty_exception_message(app_harness: AppHarness, monkeypatch):
    from test_conversations_and_tools import authenticate, create_project

    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task, attempt, worker_run, tool_call = setup_test_data(db_session, project_id, adapter_kind="agy")
        worker_run_id = worker_run.id
        db_session.commit()

    async def mock_run_existing(session, settings, worker_run_arg):
        raise RuntimeError("")

    import aidp_server.worker_execution
    monkeypatch.setattr(aidp_server.worker_execution, "run_existing_agy_worker_run", mock_run_existing)
    monkeypatch.setattr(aidp_server.worker_execution, "get_session_factory", lambda: app_harness.session_factory)

    await background_agy_runner(worker_run_id=worker_run_id)

    with app_harness.session_factory() as db_session:
        worker_run = db_session.get(WorkerRun, worker_run_id)
        assert worker_run.status == RecordStatus.FAILED
        assert worker_run.error_message == repr(RuntimeError(""))
        assert worker_run.error_message

        attempt = db_session.get(TaskAttempt, worker_run.task_attempt_id)
        assert attempt.status == TaskAttemptStatus.WORKER_FAILED
