from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.adapters.external_cli_contract import build_external_cli_context_package
from aidp_server.adapters.external_cli_dry_run import execute_external_cli_dry_run
from aidp_server.adapters.antigravity_cli import check_antigravity_cli_available, execute_antigravity_cli_worker
from aidp_server.auth import CurrentAuth
from aidp_server.config import Settings, get_settings
from aidp_server.db.models import GitWorktree, Task, TaskAttempt
from aidp_server.db.session import get_session

router = APIRouter(tags=["External CLI Adapters"])


class ExternalCliDryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter_kind: Literal["external_cli_dry_run"] = "external_cli_dry_run"
    worker_id: str
    dry_run: Literal[True] = True


class ExternalCliRunExperimentalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter_kind: Literal["antigravity_cli"] = "antigravity_cli"
    worker_id: str
    mode: Literal["controlled_readme_test"] = "controlled_readme_test"


class ExternalCliRunResult(BaseModel):
    worker_run_id: str
    process_run_id: str
    status: str
    context_artifact_id: str
    report_artifact_id: str
    stdout_artifact_id: str | None = None
    stderr_artifact_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def get_owned_attempt(session: Session, attempt_id: str, user_id: str) -> TaskAttempt:
    attempt = session.get(TaskAttempt, attempt_id)
    if attempt is None or attempt.local_user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task attempt not found")
    return attempt


@router.get("/task-attempts/{task_attempt_id}/external-cli/context")
def get_external_cli_context(
    task_attempt_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    attempt = get_owned_attempt(session, task_attempt_id, current.user.id)
    if attempt.claimed_by_worker_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Task attempt must be claimed")
    task = session.get(Task, attempt.task_id)
    worktree = session.scalar(select(GitWorktree).where(GitWorktree.task_attempt_id == attempt.id))
    if task is None or worktree is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Assigned worktree context is incomplete")
    return build_external_cli_context_package(session, attempt, task, worktree)


@router.post(
    "/task-attempts/{task_attempt_id}/external-cli/dry-run",
    response_model=ExternalCliRunResult,
)
async def external_cli_dry_run(
    task_attempt_id: str,
    request: ExternalCliDryRunRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    attempt = get_owned_attempt(session, task_attempt_id, current.user.id)
    result = await execute_external_cli_dry_run(
        session, settings, attempt, current.user.id, request.worker_id
    )
    session.commit()
    return result


@router.get("/external-cli/antigravity/status")
def get_antigravity_cli_status(
    current: CurrentAuth,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    return check_antigravity_cli_available(settings)


@router.post(
    "/task-attempts/{task_attempt_id}/external-cli/antigravity/run-experimental",
    response_model=ExternalCliRunResult,
)
async def run_antigravity_cli_experimental(
    task_attempt_id: str,
    request: ExternalCliRunExperimentalRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    attempt = get_owned_attempt(session, task_attempt_id, current.user.id)
    result = await execute_antigravity_cli_worker(
        session, settings, attempt, current.user.id, request.worker_id
    )
    session.commit()
    return result
