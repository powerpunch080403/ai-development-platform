import json
import shutil

from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.adapters.external_cli_contract import (
    build_external_cli_context_package,
    create_context_package_artifact,
)
from aidp_server.adapters.external_cli_runs import assert_no_active_external_cli_worker_run
from aidp_server.artifacts import create_text_artifact
from aidp_server.config import Settings
from aidp_server.db.models import (
    ArtifactKind,
    GitWorktree,
    Grant,
    ProcessRunStatus,
    RecordStatus,
    Task,
    TaskAttempt,
    TaskAttemptStatus,
    WorkerRun,
    utc_now,
)
from aidp_server.policy import PolicyDecisionResult, create_policy_decision, evaluate_action
from aidp_server.work_room import (
    TaskWorkRoomMessage,
    WorkRoomMessageSender,
    WorkRoomMessageType,
)
from aidp_server.worker_liveness import mark_worker_run_running_with_lease
from aidp_server.worktrees import apply_worktree_result


def check_antigravity_cli_available(settings: Settings) -> dict[str, str]:
    if not settings.enable_experimental_antigravity_cli:
        return {"status": "disabled"}

    if not settings.antigravity_cli_path:
        return {
            "status": "not_configured",
            "error_message": "CLI path is not set in configuration.",
        }

    path = Path(settings.antigravity_cli_path)
    if not path.exists():
        resolved = shutil.which(settings.antigravity_cli_path)
        if not resolved:
            return {
                "status": "unavailable",
                "error_message": f"CLI path {settings.antigravity_cli_path} not found or not executable.",
            }

    return {"status": "available"}


def build_agy_print_command(
    *,
    prompt: str,
    worktree_path: str,
    timeout_seconds: int,
    allow_dangerous_skip_permissions: bool,
) -> list[str]:
    args = ["--print", prompt, "--add-dir", worktree_path, "--print-timeout", f"{timeout_seconds}s"]
    if allow_dangerous_skip_permissions:
        args.append("--dangerously-skip-permissions")
    return args


def build_agy_task_prompt(session: Session, task: Task, attempt: TaskAttempt) -> str:
    owner_messages = session.scalars(
        select(TaskWorkRoomMessage)
        .where(TaskWorkRoomMessage.task_id == task.id)
        .where(TaskWorkRoomMessage.sender == WorkRoomMessageSender.OWNER)
        .where(
            TaskWorkRoomMessage.message_type.in_(
                [
                    WorkRoomMessageType.OWNER_INSTRUCTION,
                    WorkRoomMessageType.OWNER_FEEDBACK,
                ]
            )
        )
        .where(
            (TaskWorkRoomMessage.task_attempt_id == attempt.id)
            | (TaskWorkRoomMessage.task_attempt_id.is_(None))
        )
        .order_by(TaskWorkRoomMessage.created_at.asc(), TaskWorkRoomMessage.id.asc())
    ).all()
    owner_message_block = "\n\n".join(
        f"- {message.message_type.value}: {message.content}" for message in owner_messages
    )
    if not owner_message_block:
        owner_message_block = "- No attempt-specific Owner feedback. Use the Task instructions."

    write_scope = task.write_scope_json or {"mode": "repository"}

    return (
        "You are running inside an isolated git worktree.\n\n"
        "Task title:\n"
        f"{task.title}\n\n"
        "Task instructions:\n"
        f"{task.instructions}\n\n"
        "Owner Work Room messages for this attempt:\n"
        f"{owner_message_block}\n\n"
        "Declared write_scope JSON:\n"
        f"{json.dumps(write_scope, ensure_ascii=False)}\n\n"
        "Rules:\n"
        "- Follow the Task instructions and the latest Owner Work Room feedback.\n"
        "- Only operate inside the assigned git worktree.\n"
        "- Do not modify the source repository path.\n"
        "- Do not create or modify files outside the declared write_scope.\n"
        "- Do not run network commands.\n"
        "- Do not read or modify .env or secret files.\n"
        "- Do not modify git history.\n"
        "- Do not commit changes.\n"
        "- Stop after making the requested file edits.\n"
        "- Produce a concise worker report.\n"
    )


def _controlled_prompt(mode: str) -> str | None:
    if mode == "controlled_timeout_test":
        return (
            "You are running inside an isolated git worktree.\n\n"
            "Task:\nWait for a long time and do not modify any files.\n\n"
            "Rules:\n"
            "- Do not modify README.md.\n"
            "- Do not create new files.\n"
            "- Do not modify git history.\n"
            "- Do not commit changes.\n"
            "- Do not finish until instructed otherwise."
        )
    if mode == "controlled_scope_violation_test":
        return (
            "You are running inside an isolated git worktree.\n\n"
            "Task:\nCreate a new file named OUT_OF_SCOPE.txt with exactly this content:\n\n"
            '"This file should be rejected by write_scope."\n\n'
            "Rules:\n"
            "- Do not modify README.md.\n"
            "- Do not modify git history.\n"
            "- Do not commit changes.\n"
            "- Stop after creating OUT_OF_SCOPE.txt."
        )
    if mode == "controlled_readme_test":
        return (
            "You are running inside an isolated git worktree.\n\n"
            "Task:\nAppend exactly one line to README.md:\n\n"
            '"Controlled AGY worker test completed."\n\n'
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
    return None


async def run_existing_agy_worker_run(
    session: Session,
    settings: Settings,
    worker_run: WorkerRun,
    mode: str = "task_instructions",
) -> dict[str, Any]:
    availability = check_antigravity_cli_available(settings)
    status = availability["status"]
    if status == "disabled":
        raise HTTPException(status_code=403, detail="Experimental Antigravity CLI is disabled.")
    elif status != "available":
        raise HTTPException(
            status_code=503, detail=availability.get("error_message", "CLI is unavailable.")
        )

    attempt = session.get(TaskAttempt, worker_run.task_attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail="Attempt not found")

    task = session.get(Task, attempt.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    worktree = session.scalar(select(GitWorktree).where(GitWorktree.task_attempt_id == attempt.id))
    if worktree is None:
        raise HTTPException(status_code=409, detail="Assigned git worktree is required")

    pd, _risk = evaluate_action("external_cli.run_antigravity_experimental")
    if pd == PolicyDecisionResult.DENY:
        raise HTTPException(
            status_code=403, detail="Policy denied external_cli.run_antigravity_experimental"
        )

    create_policy_decision(
        session,
        worker_run.local_user_id,
        "external_cli.run_antigravity_experimental",
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=attempt.task_id,
        task_attempt_id=attempt.id,
    )

    context = build_external_cli_context_package(
        session, attempt, task, worktree, worker_run_id=worker_run.id
    )
    context_artifact_id = create_context_package_artifact(
        session, settings, context, worker_run.local_user_id, worker_run.worker_id
    )

    cli_path = settings.antigravity_cli_path
    controlled_prompt = _controlled_prompt(mode)
    prompt = controlled_prompt if controlled_prompt is not None else build_agy_task_prompt(session, task, attempt)

    grant = session.scalars(
        select(Grant).where(
            Grant.project_id == attempt.project_id, Grant.local_user_id == worker_run.local_user_id
        )
    ).first()
    allow_danger = (
        settings.antigravity_cli_allow_dangerous_skip_permissions
        and grant is not None
        and grant.allow_danger_flag
    )

    arguments = build_agy_print_command(
        prompt=prompt,
        worktree_path=worktree.worktree_path,
        timeout_seconds=settings.antigravity_cli_timeout_seconds,
        allow_dangerous_skip_permissions=allow_danger,
    )

    from aidp_server.process_runtime import get_process_runtime_provider

    mark_worker_run_running_with_lease(
        worker_run,
        timeout_seconds=settings.worker_run_stale_timeout_seconds,
        heartbeat_source="antigravity_cli",
    )
    session.flush()

    provider = get_process_runtime_provider()
    process_run = await provider.run(
        session=session,
        settings=settings,
        executable=cli_path,
        arguments=arguments,
        working_directory=worktree.worktree_path,
        timeout_seconds=settings.antigravity_cli_timeout_seconds,
        local_user_id=worker_run.local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=attempt.task_id,
        task_attempt_id=attempt.id,
        worker_id=worker_run.worker_id,
        worker_run_id=worker_run.id,
        worktree_id=worktree.id,
    )

    files_modified = False
    result_commit_created = False

    if process_run.status is ProcessRunStatus.SUCCEEDED:
        wt_path = Path(worktree.worktree_path)
        from aidp_server.git_commands import GitCommandError, get_git_command_service

        git_service = get_git_command_service()
        try:
            status_out = git_service.status_porcelain(wt_path)
            if status_out.strip():
                files_modified = True
                try:
                    apply_worktree_result(
                        session,
                        settings,
                        worktree,
                        "Antigravity CLI experimental result",
                        worker_run.local_user_id,
                        "Worker execution applied",
                    )
                    result_commit_created = True
                    worker_run.status = RecordStatus.SUCCEEDED
                    worker_run.summary = "Antigravity CLI completed and produced a result commit."
                    worker_run.completed_at = utc_now()
                except Exception as e:
                    error_code = (
                        "WRITE_SCOPE_VIOLATION" if "scope" in str(e).lower() else "APPLY_ERROR"
                    )
                    error_message = str(e)
                    failed_at = utc_now()
                    worker_run.status = RecordStatus.FAILED
                    worker_run.summary = f"Antigravity CLI completed but failed to apply result: {e}"
                    worker_run.error_code = error_code
                    worker_run.error_message = error_message
                    worker_run.failed_at = failed_at
                    attempt.status = TaskAttemptStatus.WORKER_FAILED
                    attempt.error_code = error_code
                    attempt.error_message = error_message
                    attempt.failed_at = failed_at
            else:
                worker_run.status = RecordStatus.SUCCEEDED
                worker_run.summary = "Antigravity CLI completed without file changes."
                worker_run.completed_at = utc_now()
        except GitCommandError as e:
            error_message = str(e)
            failed_at = utc_now()
            worker_run.status = RecordStatus.FAILED
            worker_run.summary = "Antigravity CLI completed but git status check failed."
            worker_run.error_code = "GIT_COMMAND_ERROR"
            worker_run.error_message = error_message
            worker_run.failed_at = failed_at
            attempt.status = TaskAttemptStatus.WORKER_FAILED
            attempt.error_code = "GIT_COMMAND_ERROR"
            attempt.error_message = error_message
            attempt.failed_at = failed_at
    else:
        error_code = process_run.error_code or process_run.status.value
        error_message = process_run.error_message or error_code
        worker_run.status = RecordStatus.FAILED
        worker_run.summary = "Antigravity CLI execution failed."
        worker_run.error_code = error_code
        worker_run.error_message = error_message
        failed_at = worker_run.failed_at
        attempt.status = TaskAttemptStatus.WORKER_FAILED
        attempt.error_code = error_code
        attempt.error_message = error_message
        attempt.failed_at = failed_at

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
        user_id=worker_run.local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id or "unknown",
        task_id=attempt.task_id,
        attempt_id=attempt.id,
        worker_id=worker_run.worker_id,
    )
    session.flush()
    return {
        **report,
        "report_artifact_id": report_artifact.id,
        "error_code": worker_run.error_code,
        "error_message": worker_run.error_message,
    }


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
        raise HTTPException(
            status_code=503, detail=availability.get("error_message", "CLI is unavailable.")
        )

    if attempt.claimed_by_worker_id != worker_id:
        raise HTTPException(status_code=409, detail="Attempt is not claimed by this worker")

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

    return await run_existing_agy_worker_run(session, settings, worker_run, mode)
