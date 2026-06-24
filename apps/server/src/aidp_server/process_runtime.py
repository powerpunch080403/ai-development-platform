import asyncio
import subprocess
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from aidp_server.artifacts import create_text_artifact
from aidp_server.config import Settings
from aidp_server.db.models import ProcessRun, ProcessRunStatus, utc_now
from aidp_server.process_scope import validate_scope
from aidp_server.redaction import redact_args, redact_text


@dataclass(frozen=True)
class ProcessExecutionResult:
    stdout: bytes
    stderr: bytes
    exit_code: int | None
    timed_out: bool


class ProcessRuntimeProvider(Protocol):
    async def run(
        self,
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
        ...


async def _run_asyncio_subprocess(
    *,
    executable: str,
    arguments: list[str],
    working_directory: str,
    safe_env: dict[str, str],
    timeout_seconds: int,
) -> ProcessExecutionResult:
    process = await asyncio.create_subprocess_exec(
        executable,
        *arguments,
        cwd=working_directory,
        env=safe_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL,
    )

    try:
        stdout_data, stderr_data = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
        return ProcessExecutionResult(
            stdout=stdout_data,
            stderr=stderr_data,
            exit_code=process.returncode,
            timed_out=False,
        )
    except asyncio.TimeoutError:
        process.kill()
        stdout_data, stderr_data = await process.communicate()
        return ProcessExecutionResult(
            stdout=stdout_data,
            stderr=stderr_data,
            exit_code=process.returncode,
            timed_out=True,
        )


def _run_blocking_subprocess(
    *,
    executable: str,
    arguments: list[str],
    working_directory: str,
    safe_env: dict[str, str],
    timeout_seconds: int,
) -> ProcessExecutionResult:
    try:
        completed = subprocess.run(
            [executable, *arguments],
            cwd=working_directory,
            env=safe_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        return ProcessExecutionResult(
            stdout=e.stdout or b"",
            stderr=e.stderr or b"",
            exit_code=None,
            timed_out=True,
        )

    return ProcessExecutionResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
        timed_out=False,
    )


async def _run_subprocess_with_safe_fallback(
    *,
    executable: str,
    arguments: list[str],
    working_directory: str,
    safe_env: dict[str, str],
    timeout_seconds: int,
) -> ProcessExecutionResult:
    try:
        return await _run_asyncio_subprocess(
            executable=executable,
            arguments=arguments,
            working_directory=working_directory,
            safe_env=safe_env,
            timeout_seconds=timeout_seconds,
        )
    except NotImplementedError:
        return await asyncio.to_thread(
            _run_blocking_subprocess,
            executable=executable,
            arguments=arguments,
            working_directory=working_directory,
            safe_env=safe_env,
            timeout_seconds=timeout_seconds,
        )


class NonInteractiveSubprocessRuntimeProvider:
    async def run(
        self,
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
        from aidp_server.db.models import ArtifactKind

        # 1. Scope Validation
        try:
            validate_scope(session, working_directory, repository_id, worktree_id)
            scope_error = None
        except Exception as e:
            # Capture scope validation errors before starting the process.
            scope_error = str(e) or repr(e) or type(e).__name__

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
            error_message=scope_error,
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

            result = await _run_subprocess_with_safe_fallback(
                executable=executable,
                arguments=arguments,
                working_directory=working_directory,
                safe_env=safe_env,
                timeout_seconds=timeout_seconds,
            )

            end_time = asyncio.get_running_loop().time()
            duration_ms = int((end_time - start_time) * 1000)

            # 4. Handle output
            stdout_text = redact_text(result.stdout.decode("utf-8", errors="replace"))
            stderr_text = redact_text(result.stderr.decode("utf-8", errors="replace"))

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
            run_record.exit_code = result.exit_code
            run_record.duration_ms = duration_ms
            if stdout_art:
                run_record.stdout_artifact_id = stdout_art.id
            if stderr_art:
                run_record.stderr_artifact_id = stderr_art.id

            if result.timed_out:
                run_record.status = ProcessRunStatus.TIMED_OUT
                run_record.timed_out_at = utc_now()
                run_record.error_message = f"Process timed out after {timeout_seconds} seconds"
                run_record.error_code = "TIMED_OUT"
            elif result.exit_code == 0:
                run_record.status = ProcessRunStatus.SUCCEEDED
                run_record.completed_at = utc_now()
            else:
                run_record.status = ProcessRunStatus.FAILED
                run_record.failed_at = utc_now()
                run_record.error_code = f"EXIT_CODE_{result.exit_code}"

        except Exception as e:
            end_time = asyncio.get_running_loop().time()
            run_record.status = ProcessRunStatus.FAILED
            run_record.failed_at = utc_now()
            run_record.duration_ms = int((end_time - start_time) * 1000)
            run_record.error_message = str(e) or repr(e) or type(e).__name__
            run_record.error_code = "EXECUTION_ERROR"

        return run_record


def get_process_runtime_provider() -> ProcessRuntimeProvider:
    return NonInteractiveSubprocessRuntimeProvider()
