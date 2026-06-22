from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import select

from aidp_server.db.models import TaskAttempt, Task, Worker, WorkerRun, RecordStatus, ArtifactKind, ArtifactRef, GitWorktree
from aidp_server.worktrees import apply_worktree_result, create_worktree
from aidp_server.artifacts import create_text_artifact
from aidp_server.config import get_settings, Settings
from aidp_server.db.models import GitWorktreeStatus, TaskAttemptStatus, TaskStatus
from aidp_server.db.models import utc_now
from aidp_server.auth import CurrentAuth

def start_manual_worker(
    session: Session, 
    settings: Settings, 
    current: CurrentAuth, 
    attempt: TaskAttempt, 
    notes: str | None = None
) -> tuple[WorkerRun, GitWorktree]:
    task = session.get(Task, attempt.task_id)
    if not task:
        raise ValueError("Task not found")

    worker = session.get(Worker, attempt.claimed_by_worker_id)
    if not worker or worker.worker_kind != "manual":
        raise ValueError("Attempt is not claimed by a manual worker")

    if not task.repository_id:
        raise ValueError("Task repository is required")

    worktree = session.scalar(select(GitWorktree).where(GitWorktree.task_attempt_id == attempt.id))
    if not worktree:
        # Create worktree using the router function which handles all the validation and git clone
        from aidp_server.worktrees import create_worktree
        try:
            wt_view = create_worktree(attempt.id, current, session, settings)
            worktree = session.get(GitWorktree, wt_view.id)
        except Exception as e:
            raise ValueError(f"Failed to create worktree: {e}")
    else:
        # Worktree exists, check safe state
        if worktree.status not in (GitWorktreeStatus.READY, GitWorktreeStatus.IN_USE, GitWorktreeStatus.DIRTY_RESULT):
            raise ValueError(f"Worktree in invalid status for manual worker: {worktree.status}")

    # Create WorkerRun
    worker_run = WorkerRun(
        local_user_id=attempt.local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=task.id,
        task_attempt_id=attempt.id,
        worker_id=worker.id,
        adapter_kind="manual",
        status=RecordStatus.RUNNING,
        started_at=utc_now()
    )
    session.add(worker_run)
    session.flush()

    # Create an artifact for the report
    log_lines = [
        f"Manual Worker run {worker_run.id} started",
        f"Task: {task.id}",
        f"Attempt: {attempt.id}",
        f"Worktree: {worktree.worktree_path}",
        f"Branch: {worktree.branch_name}",
        f"Instructions: {task.instructions}"
    ]
    if notes:
        log_lines.append(f"Notes: {notes}")

    create_text_artifact(
        session=session,
        settings=settings,
        content="\n".join(log_lines),
        kind=ArtifactKind.WORKER_REPORT,
        user_id=attempt.local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id or "",
        task_id=task.id,
        attempt_id=attempt.id,
        worker_id=worker.id,
    )
    
    worktree.status = GitWorktreeStatus.IN_USE

    return worker_run, worktree


def submit_manual_worker(
    session: Session, 
    settings: Settings, 
    attempt: TaskAttempt, 
    commit_message: str | None = None, 
    result_summary: str | None = None
) -> tuple[WorkerRun, ArtifactRef | None, str | None]:
    worker = session.get(Worker, attempt.claimed_by_worker_id)
    if not worker or worker.worker_kind != "manual":
        raise ValueError("Attempt is not claimed by a manual worker")

    # Find the running manual WorkerRun
    worker_run = session.scalar(
        select(WorkerRun)
        .where(WorkerRun.task_attempt_id == attempt.id)
        .where(WorkerRun.adapter_kind == "manual")
        .where(WorkerRun.status == RecordStatus.RUNNING)
        .order_by(WorkerRun.created_at.desc())
    )
    if not worker_run:
        raise ValueError("No running manual worker run found for this attempt")

    worktree = session.scalar(select(GitWorktree).where(GitWorktree.task_attempt_id == attempt.id))
    if not worktree:
        raise ValueError("Worktree not found for attempt")
    
    if worktree.status not in (GitWorktreeStatus.READY, GitWorktreeStatus.IN_USE, GitWorktreeStatus.DIRTY_RESULT):
        raise ValueError(f"Worktree in invalid status for submission: {worktree.status}")

    commit_msg = commit_message or "chore: apply manual worker result"
    
    try:
        # Commit result inside worktree (this ensures changes are isolated in worktree branch)
        apply_worktree_result(
            session, settings, worktree, commit_msg, attempt.local_user_id, "Manual worker result submitted"
        )
        
        worker_run.status = RecordStatus.SUCCEEDED
        worker_run.completed_at = utc_now()
        worker_run.summary = result_summary or "Manual worker successfully submitted changes"
        
        log_lines = [
            f"Manual Worker run {worker_run.id} submitted",
            f"Result summary: {worker_run.summary}",
            f"Result commit SHA: {worktree.result_commit_sha}"
        ]
        
        artifact = create_text_artifact(
            session=session,
            settings=settings,
            content="\n".join(log_lines),
            kind=ArtifactKind.WORKER_REPORT,
            user_id=attempt.local_user_id,
            project_id=attempt.project_id,
            repository_id=attempt.repository_id or "",
            task_id=attempt.task_id,
            attempt_id=attempt.id,
            worker_id=worker.id,
        )
        
        return worker_run, artifact, worktree.result_commit_sha

    except ValueError as e:
        # e.g., "Worktree has no changes"
        raise ValueError(str(e))
    except Exception as e:
        raise ValueError(f"Failed to submit manual result: {e}")


def fail_worker_run(session: Session, settings: Settings, worker_run: WorkerRun, error_message: str, error_code: str | None = None):
    if worker_run.status != RecordStatus.RUNNING:
        raise ValueError("Worker run is not running")
        
    worker_run.status = RecordStatus.FAILED
    worker_run.failed_at = utc_now()
    worker_run.error_code = error_code or "MANUAL_ERROR"
    worker_run.error_message = error_message
    
    attempt = session.get(TaskAttempt, worker_run.task_attempt_id)
    if attempt:
        attempt.status = TaskAttemptStatus.WORKER_FAILED
        attempt.error_code = worker_run.error_code
        attempt.error_message = error_message
        
        worker = session.get(Worker, attempt.claimed_by_worker_id)
        
        create_text_artifact(
            session=session,
            settings=settings,
            content=f"Manual Worker run {worker_run.id} failed\nError: {error_message}",
            kind=ArtifactKind.ERROR_LOG,
            user_id=attempt.local_user_id,
            project_id=attempt.project_id,
            repository_id=attempt.repository_id or "",
            task_id=attempt.task_id,
            attempt_id=attempt.id,
            worker_id=worker.id if worker else "",
        )

def cancel_worker_run(session: Session, settings: Settings, worker_run: WorkerRun, reason: str | None = None):
    if worker_run.status != RecordStatus.RUNNING:
        raise ValueError("Worker run is not running")
        
    worker_run.status = RecordStatus.CANCELLED
    worker_run.cancelled_at = utc_now()
    worker_run.summary = reason or "Cancelled by user"
    
    attempt = session.get(TaskAttempt, worker_run.task_attempt_id)
    if attempt:
        attempt.status = TaskAttemptStatus.CANCELLED
        attempt.error_message = worker_run.summary
        
        worker = session.get(Worker, attempt.claimed_by_worker_id)
        
        create_text_artifact(
            session=session,
            settings=settings,
            content=f"Manual Worker run {worker_run.id} cancelled\nReason: {worker_run.summary}",
            kind=ArtifactKind.WORKER_REPORT,
            user_id=attempt.local_user_id,
            project_id=attempt.project_id,
            repository_id=attempt.repository_id or "",
            task_id=attempt.task_id,
            attempt_id=attempt.id,
            worker_id=worker.id if worker else "",
        )
