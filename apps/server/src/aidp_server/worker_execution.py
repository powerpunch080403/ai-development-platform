from typing import Any, Protocol

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from aidp_server.adapters.antigravity_cli import run_existing_agy_worker_run
from aidp_server.config import Settings, get_settings
from aidp_server.db.models import (
    RecordStatus,
    Task,
    TaskAttempt,
    TaskAttemptStatus,
    ToolCall,
    ToolCallerType,
    ToolCallStatus,
    Worker,
    WorkerRun,
    utc_now,
)
from aidp_server.db.session import get_session_factory


class WorkerExecutionService(Protocol):
    def run_task_attempt(
        self,
        session: Session,
        *,
        worker_run: WorkerRun,
        task_attempt: TaskAttempt,
        task: Task,
        tool_call: ToolCall,
        settings: Settings,
    ) -> dict[str, Any]:
        """Orchestrates the execution of a worker run."""
        ...


class LocalBackgroundWorkerExecutionService:
    def __init__(self, background_tasks: BackgroundTasks | None):
        self._background_tasks = background_tasks

    def run_task_attempt(
        self,
        session: Session,
        *,
        worker_run: WorkerRun,
        task_attempt: TaskAttempt,
        task: Task,
        tool_call: ToolCall,
        settings: Settings,
    ) -> dict[str, Any]:
        """Hands off an owner-created WorkerRun to the AGY execution boundary."""
        if not settings.allow_owner_agy_worker_run:
            raise ValueError("AGY worker run is disabled")

        from aidp_server.audit import record_audit_event

        worker_run.status = RecordStatus.RUNNING
        task_attempt.status = TaskAttemptStatus.RUNNING_WORKER
        session.flush()

        record_audit_event(
            session,
            event_type="owner_tool_call.completed",
            message="worker.run_task_attempt completed (AGY handoff)",
            local_user_id=tool_call.user_id,
            project_id=task_attempt.project_id,
            agent_run_id=tool_call.agent_run_id,
            tool_call_id=tool_call.id,
            metadata={
                "tool_name": "worker.run_task_attempt",
                "mode": "personal",
                "authority_applied": True,
                "owner_judgment_replaced": False,
                "side_effect": True,
                "fresh_worker_context": True,
                "implicit_worker_memory": False,
                "previous_worker_context_reused": False,
                "continuity_source": "owner_authored_task_packet",
                "task_attempt_id": task_attempt.id,
                "worker_run_id": worker_run.id,
                "adapter": "agy",
                "agy_prompt_mode": "task_instructions",
            },
        )

        if not self._background_tasks:
            raise RuntimeError("background_tasks is required for AGY handoff in local background execution")

        self._background_tasks.add_task(background_agy_runner, worker_run_id=worker_run.id)

        return {
            "task_attempt_id": task_attempt.id,
            "worker_run_id": worker_run.id,
            "status": "handoff_started",
            "adapter": "agy",
            "fresh_worker_context": True,
            "previous_worker_context_reused": False,
            "execution_boundary": "existing_agy_process_boundary",
            "process_run_id": None,
        }


class _InlineBackgroundTasks:
    """Capture scheduled background AGY runs so this runner can execute them serially."""

    def __init__(self) -> None:
        self.worker_run_ids: list[str] = []

    def add_task(self, func: Any, *args: Any, **kwargs: Any) -> None:
        if func is not background_agy_runner:
            return
        if "worker_run_id" in kwargs:
            self.worker_run_ids.append(str(kwargs["worker_run_id"]))
        elif args:
            self.worker_run_ids.append(str(args[0]))


def _create_auto_drain_tool_call(session: Session, source_worker_run: WorkerRun) -> ToolCall:
    now = utc_now()
    tool_call = ToolCall(
        tool_name="worker.drain_queue",
        tool_version="1.0",
        tool_category="worker",
        caller_type=ToolCallerType.SYSTEM,
        caller_id="worker_queue.auto_drain",
        user_id=source_worker_run.local_user_id,
        project_id=source_worker_run.project_id,
        repository_id=source_worker_run.repository_id,
        task_id=source_worker_run.task_id,
        task_attempt_id=source_worker_run.task_attempt_id,
        worker_run_id=source_worker_run.id,
        risk_level="R1",
        arguments_json={
            "worker_id": source_worker_run.worker_id,
            "source_worker_run_id": source_worker_run.id,
            "trigger": "worker_run_terminal",
        },
        status=ToolCallStatus.RUNNING,
        started_at=now,
    )
    session.add(tool_call)
    session.flush()
    return tool_call


def _auto_drain_next_worker_run(session: Session, source_worker_run: WorkerRun) -> str | None:
    from aidp_server.owner_tools import drain_next_worker_run

    worker = session.get(Worker, source_worker_run.worker_id)
    if worker is None:
        return None

    tool_call = _create_auto_drain_tool_call(session, source_worker_run)
    inline_background_tasks = _InlineBackgroundTasks()
    result = drain_next_worker_run(
        session,
        tool_call,
        worker=worker,
        background_tasks=inline_background_tasks,
    )
    if tool_call.status is not ToolCallStatus.FAILED:
        tool_call.status = ToolCallStatus.SUCCEEDED
    tool_call.result_json = result
    tool_call.completed_at = utc_now()
    session.flush()

    return inline_background_tasks.worker_run_ids[0] if inline_background_tasks.worker_run_ids else None


def _mark_worker_run_failed(session: Session, worker_run_id: str, error_message: str) -> WorkerRun | None:
    worker_run = session.get(WorkerRun, worker_run_id)
    if not worker_run:
        return None

    worker_run.status = RecordStatus.FAILED
    worker_run.error_message = error_message
    worker_run.failed_at = utc_now()

    attempt = session.get(TaskAttempt, worker_run.task_attempt_id)
    if attempt:
        attempt.status = TaskAttemptStatus.WORKER_FAILED
        attempt.error_message = error_message
        attempt.failed_at = utc_now()

    session.flush()
    return worker_run


async def background_agy_runner(worker_run_id: str) -> None:
    settings = get_settings()
    factory = get_session_factory()
    next_worker_run_id: str | None = worker_run_id

    while next_worker_run_id:
        current_worker_run_id = next_worker_run_id
        with factory() as session:
            worker_run = session.get(WorkerRun, current_worker_run_id)
            if not worker_run:
                return

            try:
                await run_existing_agy_worker_run(session, settings, worker_run)
                session.commit()
            except Exception as e:
                print(f"Exception in background_agy_runner: {e}")
                session.rollback()
                error_message = str(e) or repr(e) or type(e).__name__
                failed_worker_run = _mark_worker_run_failed(session, current_worker_run_id, error_message)
                session.commit()
                if failed_worker_run is None:
                    return

        with factory() as session:
            completed_worker_run = session.get(WorkerRun, current_worker_run_id)
            if not completed_worker_run:
                return
            try:
                next_worker_run_id = _auto_drain_next_worker_run(session, completed_worker_run)
                session.commit()
            except Exception as e:
                print(f"Exception in background_agy_runner auto-drain: {e}")
                session.rollback()
                return


def get_worker_execution_service(background_tasks: BackgroundTasks | None = None) -> WorkerExecutionService:
    return LocalBackgroundWorkerExecutionService(background_tasks)
