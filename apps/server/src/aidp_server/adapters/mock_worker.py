from pathlib import Path
from sqlalchemy.orm import Session
from aidp_server.db.models import TaskAttempt, Task, Worker, WorkerRun, RecordStatus, ArtifactKind, ArtifactRef, new_uuid, GitWorktree
from aidp_server.worktrees import apply_worktree_result
from aidp_server.artifacts import create_text_artifact
from aidp_server.config import get_settings
from aidp_server.db.models import GitWorktreeStatus, TaskAttemptStatus, TaskStatus
from aidp_server.db.models import utc_now
from aidp_server.write_scope import (
    ChangedPath,
    normalize_write_scope,
    validate_changed_paths,
)

def run_mock_worker(session: Session, attempt: TaskAttempt, commit_message: str | None = None) -> tuple[WorkerRun, ArtifactRef | None]:
    task = session.get(Task, attempt.task_id)
    if not task:
        raise ValueError("Task not found")

    worker = session.get(Worker, attempt.claimed_by_worker_id)
    if not worker or worker.worker_kind != "mock":
        raise ValueError("Attempt is not claimed by a mock worker")

    worktree = session.query(GitWorktree).filter_by(task_attempt_id=attempt.id).first()
    if not worktree:
        raise ValueError("Worktree not found for attempt")
    
    if worktree.status not in (GitWorktreeStatus.READY, GitWorktreeStatus.IN_USE, GitWorktreeStatus.DIRTY_RESULT):
        raise ValueError(f"Worktree in invalid status for mock worker: {worktree.status}")
    
    worker_run = WorkerRun(
        local_user_id=attempt.local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=task.id,
        task_attempt_id=attempt.id,
        worker_id=worker.id,
        adapter_kind="mock",
        status=RecordStatus.RUNNING,
        started_at=utc_now()
    )
    session.add(worker_run)
    session.flush()

    instructions = task.instructions
    prefix = "MOCK_APPEND "
    
    log_lines = []
    log_lines.append(f"Mock Worker run {worker_run.id}")
    log_lines.append(f"Task: {task.id}")
    log_lines.append(f"Attempt: {attempt.id}")
    log_lines.append(f"Worktree: {worktree.worktree_path}")
    
    try:
        if prefix not in instructions:
            raise ValueError(f"Instructions must contain '{prefix}<relative-path>: <text>'")
        
        # Extract the first line containing MOCK_APPEND
        instruction_line = next(line for line in instructions.splitlines() if line.startswith(prefix))
        rest = instruction_line[len(prefix):]
        if ": " not in rest:
            raise ValueError("Invalid format. Expected 'MOCK_APPEND <relative-path>: <text>'")
        
        rel_path, text = rest.split(": ", 1)
        rel_path = rel_path.strip()
        
        # Safety checks
        if ".." in rel_path or Path(rel_path).is_absolute():
            raise ValueError("Path traversal or absolute paths are forbidden")
        
        wt_path = Path(worktree.worktree_path)
        target_path = wt_path / rel_path
        
        # Resolve to check if it's within the worktree
        resolved_target = target_path.resolve()
        resolved_wt = wt_path.resolve()
        
        if not str(resolved_target).startswith(str(resolved_wt)):
            raise ValueError("Target path resolves outside the worktree")

        validate_changed_paths(
            [ChangedPath(path=rel_path, status="??" if not resolved_target.exists() else " M", is_new_file=not resolved_target.exists())],
            normalize_write_scope(task.write_scope_json),
        )

        log_lines.append(f"Action: append_to_file")
        log_lines.append(f"Path: {rel_path}")

        # Ensure parent exists
        resolved_target.parent.mkdir(parents=True, exist_ok=True)
        
        with open(resolved_target, "a", encoding="utf-8") as f:
            f.write(f"{text}\n")
            
        log_lines.append("Result: succeeded")
        
        # commit result
        commit_msg = commit_message or "chore: apply mock worker result"
        apply_worktree_result(session, get_settings(), worktree, commit_msg, attempt.local_user_id, "Mock worker result committed")
        
        worker_run.status = RecordStatus.SUCCEEDED
        worker_run.completed_at = utc_now()
        worker_run.summary = "Mock worker successfully applied changes"
        
        artifact = create_text_artifact(
            session=session,
            settings=get_settings(),
            content="\n".join(log_lines),
            kind=ArtifactKind.WORKER_REPORT,
            user_id=attempt.local_user_id,
            project_id=attempt.project_id,
            repository_id=attempt.repository_id or "",
            task_id=task.id,
            attempt_id=attempt.id,
            worker_id=worker.id,
        )
        return worker_run, artifact
        
    except Exception as e:
        log_lines.append(f"Result: failed")
        log_lines.append(f"Error: {str(e)}")
        
        worker_run.status = RecordStatus.FAILED
        worker_run.failed_at = utc_now()
        worker_run.error_code = "MOCK_ERROR"
        worker_run.error_message = str(e)
        
        attempt.status = TaskAttemptStatus.WORKER_FAILED
        attempt.error_code = "MOCK_ERROR"
        attempt.error_message = str(e)
        
        artifact = create_text_artifact(
            session=session,
            settings=get_settings(),
            content="\n".join(log_lines),
            kind=ArtifactKind.ERROR_LOG,
            user_id=attempt.local_user_id,
            project_id=attempt.project_id,
            repository_id=attempt.repository_id or "",
            task_id=task.id,
            attempt_id=attempt.id,
            worker_id=worker.id,
        )
        return worker_run, artifact
