from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime
import sys

from aidp_server.db.session import get_session
from aidp_server.db.models import ProcessRun, TaskAttempt
from aidp_server.auth import CurrentAuth
from aidp_server.config import get_settings, Settings
from aidp_server.process_runner import execute_process_async
from aidp_server.policy import create_policy_decision, evaluate_action, PolicyDecisionResult

router = APIRouter(tags=["Process Runs"])


class ProcessRunView(BaseModel):
    id: str
    local_user_id: str | None
    project_id: str | None
    repository_id: str | None
    task_id: str | None
    task_attempt_id: str | None
    worker_id: str | None
    worker_run_id: str | None
    tool_call_id: str | None
    command_display: str
    executable: str
    arguments_json: dict[str, object]
    working_directory: str
    status: str
    exit_code: int | None
    timeout_seconds: int
    started_at: datetime | None
    completed_at: datetime | None
    timed_out_at: datetime | None
    cancelled_at: datetime | None
    failed_at: datetime | None
    duration_ms: int | None
    stdout_artifact_id: str | None
    stderr_artifact_id: str | None
    combined_log_artifact_id: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/process-runs/{process_run_id}", response_model=ProcessRunView)
def get_process_run(
    process_run_id: str,
    current: CurrentAuth,
    session: Session = Depends(get_session),
):
    run_record = session.get(ProcessRun, process_run_id)
    if not run_record or run_record.local_user_id != current.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Process run not found")
    return run_record


@router.get("/task-attempts/{task_attempt_id}/process-runs", response_model=list[ProcessRunView])
def list_process_runs_for_attempt(
    task_attempt_id: str,
    current: CurrentAuth,
    session: Session = Depends(get_session),
):
    attempt = session.get(TaskAttempt, task_attempt_id)
    if not attempt or attempt.local_user_id != current.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task attempt not found")

    runs = session.scalars(
        select(ProcessRun)
        .where(ProcessRun.task_attempt_id == task_attempt_id)
        .order_by(ProcessRun.created_at.desc())
    ).all()
    return runs


class TestCommandRequest(BaseModel):
    # We purposefully do not accept arbitrary commands here for the MVP baseline.
    pass


@router.post(
    "/task-attempts/{task_attempt_id}/process-runs/test-command", response_model=ProcessRunView
)
async def run_test_command(
    task_attempt_id: str,
    request: TestCommandRequest,
    current: CurrentAuth,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    """
    Test endpoint for the Process Runner baseline.
    Runs a safe platform-specific test command.
    """
    attempt = session.get(TaskAttempt, task_attempt_id)
    if not attempt or attempt.local_user_id != current.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task attempt not found")

    # Determine safe working directory context
    # Use the repository path for baseline validation test
    from aidp_server.db.models import ProjectRepository

    repo = None
    if attempt.repository_id:
        repo = session.get(ProjectRepository, attempt.repository_id)

    if not repo or not repo.repository_path:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "No repository associated with this attempt"
        )

    wd = repo.repository_path
    executable = sys.executable
    arguments = ["-c", "print('Baseline process runner test successful.')"]

    pd, risk = evaluate_action("process_run.create")
    if pd == PolicyDecisionResult.DENY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Policy denied process_run.create")
    create_policy_decision(
        session,
        current.user.id,
        "process_run.create",
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=attempt.task_id,
        task_attempt_id=attempt.id,
    )

    run_record = await execute_process_async(
        session=session,
        settings=settings,
        executable=executable,
        arguments=arguments,
        working_directory=wd,
        timeout_seconds=5,
        local_user_id=current.user.id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=attempt.task_id,
        task_attempt_id=attempt.id,
        worker_id=attempt.worker_id,
    )

    session.commit()
    session.refresh(run_record)

    return run_record
