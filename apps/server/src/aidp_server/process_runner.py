import asyncio
from pathlib import Path
from sqlalchemy.orm import Session
import json

from aidp_server.db.models import ProcessRun, ProcessRunStatus, utc_now, ProjectRepository, GitWorktree, TaskAttempt, ArtifactKind
from aidp_server.config import Settings
from aidp_server.redaction import redact_args, redact_text
from aidp_server.artifacts import create_text_artifact


class ScopeValidationError(Exception):
    pass


def validate_scope(session: Session, working_directory: str, repository_id: str | None = None, worktree_id: str | None = None) -> None:
    # Resolve the requested working directory
    try:
        wd_path = Path(working_directory).resolve(strict=False)
    except Exception:
        raise ScopeValidationError("Invalid working directory format")

    allowed_paths = []
    
    if repository_id:
        repo = session.get(ProjectRepository, repository_id)
        if repo and repo.repository_path:
            allowed_paths.append(Path(repo.repository_path).resolve(strict=False))
            
    if worktree_id:
        worktree = session.get(GitWorktree, worktree_id)
        if worktree and worktree.worktree_path:
            # We don't resolve against the absolute system root if worktree_path is relative to app data,
            # but in this MVP worktree_path is typically absolute or relative to run dir. 
            # We just resolve it.
            allowed_paths.append(Path(worktree.worktree_path).resolve(strict=False))

    if not allowed_paths:
        raise ScopeValidationError("No allowed scopes found for execution")

    for allowed in allowed_paths:
        if wd_path.is_relative_to(allowed):
            return

    raise ScopeValidationError("Working directory is outside allowed repository/worktree scope")


async def execute_process_async(
    session: Session,
    settings: Settings,
    executable: str,
    arguments: list[str],
    working_directory: str,
    timeout_seconds: int,
    local_user_id: str | None = None,
    project_id: str | None = None,
    repository_id: str | None = None,
    task_id: str | None = None,
    task_attempt_id: str | None = None,
    worker_id: str | None = None,
    worker_run_id: str | None = None,
    tool_call_id: str | None = None,
    worktree_id: str | None = None,
    environment: dict[str, str] | None = None,
) -> ProcessRun:
    
    # 1. Scope Validation
    try:
        validate_scope(session, working_directory, repository_id, worktree_id)
        scope_error = None
    except ScopeValidationError as e:
        scope_error = str(e)

    # Prepare command display
    redacted_args = redact_args(arguments)
    command_display = f"{executable} " + " ".join(redacted_args)

    # 2. Create ProcessRun Record
    run_record = ProcessRun(
        local_user_id=local_user_id,
        project_id=project_id,
        repository_id=repository_id,
        task_id=task_id,
        task_attempt_id=task_attempt_id,
        worker_id=worker_id,
        worker_run_id=worker_run_id,
        tool_call_id=tool_call_id,
        command_display=command_display,
        executable=executable,
        arguments_json={"args": redacted_args},
        working_directory=working_directory,
        status=ProcessRunStatus.BLOCKED if scope_error else ProcessRunStatus.RUNNING,
        timeout_seconds=timeout_seconds,
        started_at=utc_now() if not scope_error else None,
        error_message=scope_error
    )
    session.add(run_record)
    session.flush()

    if scope_error:
        run_record.failed_at = utc_now()
        run_record.error_code = "SCOPE_VALIDATION_FAILED"
        return run_record

    # 3. Execute
    start_time = asyncio.get_running_loop().time()
    try:
        from aidp_server.process_environment import build_process_environment
        safe_env = build_process_environment(environment)
        
        process = await asyncio.create_subprocess_exec(
            executable,
            *arguments,
            cwd=working_directory,
            env=safe_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            exit_code = process.returncode
            timed_out = False
        except asyncio.TimeoutError:
            process.kill()
            stdout_data, stderr_data = await process.communicate()
            exit_code = process.returncode
            timed_out = True

        end_time = asyncio.get_running_loop().time()
        duration_ms = int((end_time - start_time) * 1000)

        # 4. Handle output
        stdout_text = redact_text(stdout_data.decode("utf-8", errors="replace"))
        stderr_text = redact_text(stderr_data.decode("utf-8", errors="replace"))
        
        stdout_art = None
        stderr_art = None

        if stdout_text:
            stdout_art = create_text_artifact(
                session=session,
                settings=settings,
                content=stdout_text,
                kind=ArtifactKind.CLI_TRANSCRIPT,
                user_id=local_user_id or "system",
                project_id=project_id or "unknown",
                repository_id=repository_id or "unknown",
                task_id=task_id or "unknown",
                attempt_id=task_attempt_id or "unknown",
                worker_id=worker_id,
            )
            
        if stderr_text:
            stderr_art = create_text_artifact(
                session=session,
                settings=settings,
                content=stderr_text,
                kind=ArtifactKind.ERROR_LOG,
                user_id=local_user_id or "system",
                project_id=project_id or "unknown",
                repository_id=repository_id or "unknown",
                task_id=task_id or "unknown",
                attempt_id=task_attempt_id or "unknown",
                worker_id=worker_id,
            )

        # Update record
        run_record.exit_code = exit_code
        run_record.duration_ms = duration_ms
        if stdout_art:
            run_record.stdout_artifact_id = stdout_art.id
        if stderr_art:
            run_record.stderr_artifact_id = stderr_art.id

        if timed_out:
            run_record.status = ProcessRunStatus.TIMED_OUT
            run_record.timed_out_at = utc_now()
            run_record.error_message = f"Process timed out after {timeout_seconds} seconds"
        elif exit_code == 0:
            run_record.status = ProcessRunStatus.SUCCEEDED
            run_record.completed_at = utc_now()
        else:
            run_record.status = ProcessRunStatus.FAILED
            run_record.failed_at = utc_now()
            run_record.error_code = f"EXIT_CODE_{exit_code}"

    except Exception as e:
        end_time = asyncio.get_running_loop().time()
        run_record.status = ProcessRunStatus.FAILED
        run_record.failed_at = utc_now()
        run_record.duration_ms = int((end_time - start_time) * 1000)
        run_record.error_message = str(e)
        run_record.error_code = "EXECUTION_ERROR"

    return run_record
