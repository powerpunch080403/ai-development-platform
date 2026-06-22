import json
import shutil
import subprocess
from pathlib import Path
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
from aidp_server.worktrees import apply_worktree_result
from aidp_server.adapters.external_cli_runs import assert_no_active_external_cli_worker_run


def check_antigravity_cli_available(settings: Settings) -> dict[str, str]:
    if not settings.enable_experimental_antigravity_cli:
        return {"status": "disabled"}
    
    if not settings.antigravity_cli_path:
        return {"status": "not_configured", "error_message": "CLI path is not set in configuration."}
        
    path = Path(settings.antigravity_cli_path)
    if not path.exists():
        # Maybe it's in PATH
        resolved = shutil.which(settings.antigravity_cli_path)
        if not resolved:
            return {"status": "unavailable", "error_message": f"CLI path {settings.antigravity_cli_path} not found or not executable."}
            
    return {"status": "available"}


def build_agy_print_command(
    *,
    prompt: str,
    worktree_path: str,
    timeout_seconds: int,
    allow_dangerous_skip_permissions: bool,
) -> list[str]:
    args = [
        "--print", prompt,
        "--add-dir", worktree_path,
        "--print-timeout", f"{timeout_seconds}s"
    ]
    if allow_dangerous_skip_permissions:
        args.append("--dangerously-skip-permissions")
    return args


async def execute_antigravity_cli_worker(
    session: Session,
    settings: Settings,
    attempt: TaskAttempt,
    local_user_id: str,
    worker_id: str,
    mode: str,
) -> dict[str, Any]:
    availability = check_antigravity_cli_available(settings)
    status = availability["status"]
    if status == "disabled":
        raise HTTPException(status_code=403, detail="Experimental Antigravity CLI is disabled.")
    elif status != "available":
        raise HTTPException(status_code=503, detail=availability.get("error_message", "CLI is unavailable."))
        
    if attempt.claimed_by_worker_id != worker_id:
        raise HTTPException(status_code=409, detail="Attempt is not claimed by this worker")
        
    task = session.get(Task, attempt.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
        
    worktree = session.scalar(select(GitWorktree).where(GitWorktree.task_attempt_id == attempt.id))
    if worktree is None:
        raise HTTPException(status_code=409, detail="Assigned git worktree is required")
        
    pd, risk = evaluate_action("external_cli.run_antigravity_experimental")
    if pd == PolicyDecisionResult.DENY:
        raise HTTPException(status_code=403, detail="Policy denied external_cli.run_antigravity_experimental")
        
    create_policy_decision(
        session, local_user_id, "external_cli.run_antigravity_experimental",
        project_id=attempt.project_id, repository_id=attempt.repository_id,
        task_id=attempt.task_id, task_attempt_id=attempt.id
    )

    assert_no_active_external_cli_worker_run(session, attempt.id)

    worker_run = WorkerRun(
        local_user_id=local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=attempt.task_id,
        task_attempt_id=attempt.id,
        worker_id=worker_id,
        adapter_kind="antigravity_cli",
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

    # We do NOT pass executable or args from the HTTP request body.
    cli_path = settings.antigravity_cli_path
    
    if mode == "controlled_scope_violation_test":
        controlled_prompt = (
            "You are running inside an isolated git worktree.\n\n"
            "Task:\nCreate a new file named OUT_OF_SCOPE.txt with exactly this content:\n\n"
            "\"This file should be rejected by write_scope.\"\n\n"
            "Rules:\n"
            "- Do not modify README.md.\n"
            "- Do not modify git history.\n"
            "- Do not commit changes.\n"
            "- Stop after creating OUT_OF_SCOPE.txt."
        )
    else:
        controlled_prompt = (
            "You are running inside an isolated git worktree.\n\n"
            "Task:\nAppend exactly one line to README.md:\n\n"
            "\"Controlled AGY worker test completed.\"\n\n"
            "Rules:\n"
            "- Modify README.md only.\n"
            "- Do not create new files.\n"
            "- Do not modify any other file.\n"
            "- Do not run network commands.\n"
            "- Do not read or modify .env files.\n"
            "- Do not modify git history.\n"
            "- Do not commit changes.\n"
            "- Stop after editing README.md."
        )

    arguments = build_agy_print_command(
        prompt=controlled_prompt,
        worktree_path=worktree.worktree_path,
        timeout_seconds=settings.antigravity_cli_timeout_seconds,
        allow_dangerous_skip_permissions=settings.antigravity_cli_allow_dangerous_skip_permissions,
    )

    process_run = await execute_process_async(
        session=session,
        settings=settings,
        executable=cli_path,
        arguments=arguments,
        working_directory=worktree.worktree_path,
        timeout_seconds=settings.antigravity_cli_timeout_seconds,
        local_user_id=local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=attempt.task_id,
        task_attempt_id=attempt.id,
        worker_id=worker_id,
        worker_run_id=worker_run.id,
        worktree_id=worktree.id,
    )

    files_modified = False
    result_commit_created = False

    if process_run.status is ProcessRunStatus.SUCCEEDED:
        # Check if the worktree is dirty
        wt_path = Path(worktree.worktree_path)
        status_res = subprocess.run(
            ["git", "-C", str(wt_path), "status", "--porcelain"],
            check=False, capture_output=True, text=True
        )
        if status_res.returncode == 0 and status_res.stdout.strip():
            files_modified = True
            try:
                apply_worktree_result(
                    session, settings, worktree,
                    "Antigravity CLI experimental result",
                    local_user_id, "Worker execution applied"
                )
                result_commit_created = True
                worker_run.status = RecordStatus.SUCCEEDED
                worker_run.summary = "Antigravity CLI completed and produced a result commit."
                worker_run.completed_at = utc_now()
            except Exception as e:
                # E.g. write scope violation
                worker_run.status = RecordStatus.FAILED
                worker_run.summary = f"Antigravity CLI completed but failed to apply result: {e}"
                worker_run.error_code = "WRITE_SCOPE_VIOLATION" if "scope" in str(e).lower() else "APPLY_ERROR"
                worker_run.error_message = str(e)
                worker_run.failed_at = utc_now()
        else:
            # No files modified
            worker_run.status = RecordStatus.SUCCEEDED
            worker_run.summary = "Antigravity CLI completed without file changes."
            worker_run.completed_at = utc_now()
    else:
        worker_run.status = RecordStatus.FAILED
        worker_run.summary = "Antigravity CLI execution failed."
        worker_run.error_code = process_run.error_code or process_run.status.value
        worker_run.error_message = process_run.error_message
        worker_run.failed_at = utc_now()

    report = {
        "adapter_kind": "antigravity_cli",
        "worker_run_id": worker_run.id,
        "process_run_id": process_run.id,
        "task_attempt_id": attempt.id,
        "status": worker_run.status.value,
        "context_artifact_id": context_artifact_id,
        "stdout_artifact_id": process_run.stdout_artifact_id,
        "stderr_artifact_id": process_run.stderr_artifact_id,
        "files_modified": files_modified,
        "result_commit_created": result_commit_created,
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
