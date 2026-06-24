from sqlalchemy import select
from aidp_server.db.models import (
    Device,
    DeviceType,
    ToolCall,
    ToolCallStatus,
    ToolCallerType,
    Worker,
    WorkerRun,
)
from aidp_server.owner_tools import execute_owner_tool
from conftest import AppHarness
from test_owner_worker_start_tool import setup_test_data
from test_conversations_and_tools import authenticate, create_project


def test_worker_start_creates_device_if_missing(app_harness: AppHarness):
    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task = setup_test_data(db_session, project_id)

        # The authenticate() call creates a WEB_UI device.
        devices_before = db_session.scalars(
            select(Device).where(Device.local_user_id == user.id)
        ).all()
        assert len(devices_before) == 1
        initial_device_id = devices_before[0].id

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

        assert "task_attempt_id" in result

        # Check that no new Device was created since we fallback to the existing one
        devices_after = db_session.scalars(
            select(Device).where(Device.local_user_id == user.id)
        ).all()
        assert len(devices_after) == 1

        # Check that Worker references the existing device
        worker_run = db_session.get(WorkerRun, result["worker_run_id"])
        worker = db_session.get(Worker, worker_run.worker_id)
        assert worker.device_id == initial_device_id
        assert worker.device_id != "system"  # No longer hardcoded literal


def test_worker_start_reuses_existing_device(app_harness: AppHarness):
    authenticate(app_harness)
    project_id = create_project(app_harness)

    with app_harness.session_factory() as db_session:
        user, agent_run, task = setup_test_data(db_session, project_id)

        # Create an existing device
        existing_device = Device(
            local_user_id=user.id,
            device_type=DeviceType.LOCAL_RUNTIME,
            display_name="Existing Local Device",
        )
        db_session.add(existing_device)
        db_session.commit()

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
        db_session.commit()

        assert "task_attempt_id" in result

        # Check that no new Device was created
        devices_after = db_session.scalars(
            select(Device).where(Device.local_user_id == user.id)
        ).all()
        assert len(devices_after) == 2
        assert any(d.id == existing_device.id for d in devices_after)

        # Check that Worker references the existing device
        worker_run = db_session.get(WorkerRun, result["worker_run_id"])
        worker = db_session.get(Worker, worker_run.worker_id)
        assert worker.device_id == existing_device.id
        assert (
            worker.worker_kind.value == "mock"
        )  # currently adapter="agy" maps to kind="mock" in terms of enum
