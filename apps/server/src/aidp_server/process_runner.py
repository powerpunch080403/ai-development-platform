from sqlalchemy.orm import Session

from aidp_server.db.models import ProcessRun
from aidp_server.config import Settings




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
    from aidp_server.process_runtime import get_process_runtime_provider
    provider = get_process_runtime_provider()
    
    return await provider.run(
        session=session,
        settings=settings,
        executable=executable,
        arguments=arguments,
        working_directory=working_directory,
        timeout_seconds=timeout_seconds,
        local_user_id=local_user_id,
        project_id=project_id,
        repository_id=repository_id,
        task_id=task_id,
        task_attempt_id=task_attempt_id,
        worker_id=worker_id,
        worker_run_id=worker_run_id,
        tool_call_id=tool_call_id,
        worktree_id=worktree_id,
        environment=environment,
    )
