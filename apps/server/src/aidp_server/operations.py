from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidp_server.auth import CurrentAuth
from aidp_server.db.models import (
    Project,
    RecordStatus,
    Task,
    TaskAttempt,
    TaskAttemptStatus,
    WorkerRun,
)
from aidp_server.db.session import get_session


router = APIRouter(tags=["operations"])

ACTIVE_ATTEMPT_STATUSES = {
    TaskAttemptStatus.CREATED,
    TaskAttemptStatus.QUEUED_WORKER,
    TaskAttemptStatus.PREPARING_WORKTREE,
    TaskAttemptStatus.RUNNING_WORKER,
    TaskAttemptStatus.WAITING_FOR_COMMIT,
    TaskAttemptStatus.RETRY_REQUESTED,
}

ATTENTION_ATTEMPT_STATUSES = {
    TaskAttemptStatus.WORKER_FAILED,
    TaskAttemptStatus.FAILED,
}

ACTIVE_WORKER_RUN_STATUSES = {
    RecordStatus.QUEUED,
    RecordStatus.RUNNING,
}



def as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )

class WorkerRunOperationsView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    task_attempt_id: str
    worker_id: str
    adapter_kind: str
    status: str
    last_heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    lease_expired: bool
    updated_at: datetime
    error_code: str | None
    error_message: str | None


class ProjectOperationsStatusView(BaseModel):
    project_id: str
    generated_at: datetime
    task_counts: dict[str, int]
    attempt_counts: dict[str, int]
    worker_run_counts: dict[str, int]
    active_attempt_count: int
    active_worker_run_count: int
    stale_worker_run_count: int
    attention_count: int
    recent_worker_runs: list[WorkerRunOperationsView]


def _owned_project(session: Session, project_id: str, user_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.local_user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _status_counts(
    session: Session,
    *,
    model: type,
    project_id: str,
    user_id: str,
) -> dict[str, int]:
    rows = session.execute(
        select(model.status, func.count())
        .where(model.project_id == project_id)
        .where(model.local_user_id == user_id)
        .group_by(model.status)
    ).all()
    return {status.value: int(count) for status, count in rows}


def _count(
    session: Session,
    statement,
) -> int:
    return int(session.scalar(statement) or 0)


def _worker_run_view(worker_run: WorkerRun, *, now: datetime) -> WorkerRunOperationsView:
    lease_expired = (
        worker_run.status == RecordStatus.RUNNING
        and worker_run.lease_expires_at is not None
        and as_utc(worker_run.lease_expires_at) <= now
    )
    return WorkerRunOperationsView(
        id=worker_run.id,
        task_id=worker_run.task_id,
        task_attempt_id=worker_run.task_attempt_id,
        worker_id=worker_run.worker_id,
        adapter_kind=worker_run.adapter_kind,
        status=worker_run.status.value,
        last_heartbeat_at=worker_run.last_heartbeat_at,
        lease_expires_at=worker_run.lease_expires_at,
        lease_expired=lease_expired,
        updated_at=worker_run.updated_at,
        error_code=worker_run.error_code,
        error_message=worker_run.error_message,
    )


@router.get(
    "/projects/{project_id}/operations/status",
    response_model=ProjectOperationsStatusView,
)
def get_project_operations_status(
    project_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ProjectOperationsStatusView:
    _owned_project(session, project_id, current.user.id)
    now = datetime.now(timezone.utc)

    task_counts = _status_counts(
        session,
        model=Task,
        project_id=project_id,
        user_id=current.user.id,
    )
    attempt_counts = _status_counts(
        session,
        model=TaskAttempt,
        project_id=project_id,
        user_id=current.user.id,
    )
    worker_run_counts = _status_counts(
        session,
        model=WorkerRun,
        project_id=project_id,
        user_id=current.user.id,
    )

    active_attempt_count = _count(
        session,
        select(func.count())
        .select_from(TaskAttempt)
        .where(TaskAttempt.project_id == project_id)
        .where(TaskAttempt.local_user_id == current.user.id)
        .where(TaskAttempt.status.in_(ACTIVE_ATTEMPT_STATUSES)),
    )
    active_worker_run_count = _count(
        session,
        select(func.count())
        .select_from(WorkerRun)
        .where(WorkerRun.project_id == project_id)
        .where(WorkerRun.local_user_id == current.user.id)
        .where(WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES)),
    )
    stale_worker_run_count = _count(
        session,
        select(func.count())
        .select_from(WorkerRun)
        .where(WorkerRun.project_id == project_id)
        .where(WorkerRun.local_user_id == current.user.id)
        .where(WorkerRun.status == RecordStatus.RUNNING)
        .where(WorkerRun.lease_expires_at.is_not(None))
        .where(WorkerRun.lease_expires_at <= now),
    )
    failed_attempt_count = _count(
        session,
        select(func.count())
        .select_from(TaskAttempt)
        .where(TaskAttempt.project_id == project_id)
        .where(TaskAttempt.local_user_id == current.user.id)
        .where(TaskAttempt.status.in_(ATTENTION_ATTEMPT_STATUSES)),
    )

    recent_worker_runs = session.scalars(
        select(WorkerRun)
        .where(WorkerRun.project_id == project_id)
        .where(WorkerRun.local_user_id == current.user.id)
        .order_by(WorkerRun.updated_at.desc())
        .limit(10)
    ).all()

    return ProjectOperationsStatusView(
        project_id=project_id,
        generated_at=now,
        task_counts=task_counts,
        attempt_counts=attempt_counts,
        worker_run_counts=worker_run_counts,
        active_attempt_count=active_attempt_count,
        active_worker_run_count=active_worker_run_count,
        stale_worker_run_count=stale_worker_run_count,
        attention_count=failed_attempt_count + stale_worker_run_count,
        recent_worker_runs=[
            _worker_run_view(worker_run, now=now) for worker_run in recent_worker_runs
        ],
    )

