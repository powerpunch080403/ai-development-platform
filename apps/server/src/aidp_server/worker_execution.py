from typing import Any, Protocol

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from aidp_server.adapters.antigravity_cli import run_existing_agy_worker_run
from aidp_server.config import Settings, get_settings
from aidp_server.db.models import Task, TaskAttempt, ToolCall, WorkerRun
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
        """
        Orchestrates the execution of a worker run.
        """
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
        """
        Hands off an owner-created WorkerRun to the AGY execution boundary.
        """
        # Defensive check: gate should have been verified in owner_tools.py
        if not settings.allow_owner_agy_worker_run:
            raise ValueError("AGY worker run is disabled")

        from aidp_server.db.models import RecordStatus, TaskAttemptStatus
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
            },
        )

        # The background task needs its own session to avoid sharing the request's connection
        if not self._background_tasks:
            raise RuntimeError("background_tasks is required for AGY handoff in local background execution")

        self._background_tasks.add_task(
            background_agy_runner,
            worker_run_id=worker_run.id,
        )

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


async def background_agy_runner(worker_run_id: str) -> None:
    settings = get_settings()
    factory = get_session_factory()
    with factory() as session:
        worker_run = session.get(WorkerRun, worker_run_id)
        if not worker_run:
            return

        try:
            # We default to controlled_readme_test for MVP testing
            await run_existing_agy_worker_run(
                session, settings, worker_run, mode="controlled_readme_test"
            )
            session.commit()
        except Exception as e:
            print(f"Exception in background_agy_runner: {e}")
            session.rollback()
            # Mark as failed if an unhandled exception occurred
            # In a full implementation we would capture the error in worker_run
            pass

def get_worker_execution_service(background_tasks: BackgroundTasks | None = None) -> WorkerExecutionService:
    return LocalBackgroundWorkerExecutionService(background_tasks)
