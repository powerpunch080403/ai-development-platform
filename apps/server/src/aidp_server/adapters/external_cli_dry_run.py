import json
import sys
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.adapters.external_cli_contract import (
    build_external_cli_context_package,
    create_context_package_artifact,
)
from aidp_server.artifacts import create_text_artifact
from aidp_server.config import Settings
from aidp_server.db.models import (
    ArtifactKind,
    GitWorktree,
    ProcessRunStatus,
    RecordStatus,
    Task,
    TaskAttempt,
    WorkerRun,
    utc_now,
)
from aidp_server.process_runner import execute_process_async
from aidp_server.policy import create_policy_decision, evaluate_action, PolicyDecisionResult


async def execute_external_cli_dry_run(
    session: Session,
    settings: Settings,
    attempt: TaskAttempt,
    local_user_id: str,
    worker_id: str,
) -> dict[str, Any]:
    if attempt.claimed_by_worker_id != worker_id:
        raise HTTPException(409, "Attempt is not claimed by this worker")
    task = session.get(Task, attempt.task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    worktree = session.scalar(select(GitWorktree).where(GitWorktree.task_attempt_id == attempt.id))
    if worktree is None:
        raise HTTPException(409, "Assigned git worktree is required")
        
    pd, risk = evaluate_action("external_cli.dry_run")
    if pd == PolicyDecisionResult.DENY:
        raise HTTPException(status_code=403, detail="Policy denied external_cli.dry_run")
    create_policy_decision(
        session, local_user_id, "external_cli.dry_run",
        project_id=attempt.project_id, repository_id=attempt.repository_id,
        task_id=attempt.task_id, task_attempt_id=attempt.id
    )

    worker_run = WorkerRun(
        local_user_id=local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=attempt.task_id,
        task_attempt_id=attempt.id,
        worker_id=worker_id,
        adapter_kind="external_cli_dry_run",
        status=RecordStatus.RUNNING,
        started_at=utc_now(),
    )
    session.add(worker_run)
    session.flush()

    context = build_external_cli_context_package(
        session, attempt, task, worktree, worker_run_id=worker_run.id
    )
    context_artifact_id = create_context_package_artifact(
        session, settings, context, local_user_id, worker_id
    )

    # Fixed, server-selected command. No request field can alter executable or arguments.
    process_run = await execute_process_async(
        session=session,
        settings=settings,
        executable=sys.executable,
        arguments=["-c", "print('External CLI adapter dry run completed.')"],
        working_directory=worktree.worktree_path,
        timeout_seconds=5,
        local_user_id=local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=attempt.task_id,
        task_attempt_id=attempt.id,
        worker_id=worker_id,
        worker_run_id=worker_run.id,
        worktree_id=worktree.id,
    )

    if process_run.status is ProcessRunStatus.SUCCEEDED:
        worker_run.status = RecordStatus.SUCCEEDED
        worker_run.summary = "External CLI contract dry-run succeeded without file changes."
        worker_run.completed_at = utc_now()
    else:
        worker_run.status = RecordStatus.FAILED
        worker_run.summary = "External CLI contract dry-run failed."
        worker_run.error_code = process_run.error_code or process_run.status.value
        worker_run.error_message = process_run.error_message
        worker_run.failed_at = utc_now()

    report = {
        "adapter_kind": "external_cli_dry_run",
        "worker_run_id": worker_run.id,
        "process_run_id": process_run.id,
        "task_attempt_id": attempt.id,
        "status": worker_run.status.value,
        "context_artifact_id": context_artifact_id,
        "stdout_artifact_id": process_run.stdout_artifact_id,
        "stderr_artifact_id": process_run.stderr_artifact_id,
        "files_modified": False,
        "result_commit_created": False,
    }
    report_artifact = create_text_artifact(
        session=session,
        settings=settings,
        content=json.dumps(report, indent=2),
        kind=ArtifactKind.WORKER_REPORT,
        user_id=local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id or "unknown",
        task_id=attempt.task_id,
        attempt_id=attempt.id,
        worker_id=worker_id,
    )
    session.flush()
    return {
        **report,
        "report_artifact_id": report_artifact.id,
        "error_code": worker_run.error_code,
        "error_message": worker_run.error_message,
    }
