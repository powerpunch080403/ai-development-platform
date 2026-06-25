from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.audit import record_audit_event
from aidp_server.db.models import (
    RecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    ToolCall,
    WorkerRun,
)

STALE_WORKER_RUN_ERROR_CODE = "STALE_WORKER_RUN"

RECOVERABLE_ATTEMPT_STATUSES = {
    TaskAttemptStatus.CREATED,
    TaskAttemptStatus.QUEUED_WORKER,
    TaskAttemptStatus.PREPARING_WORKTREE,
    TaskAttemptStatus.RUNNING_WORKER,
    TaskAttemptStatus.WAITING_FOR_COMMIT,
    TaskAttemptStatus.RETRY_REQUESTED,
}


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def worker_run_liveness_at(worker_run: WorkerRun) -> datetime:
    return (
        worker_run.last_heartbeat_at
        or worker_run.updated_at
        or worker_run.started_at
        or worker_run.created_at
    )


def mark_worker_run_running_with_lease(
    worker_run: WorkerRun,
    *,
    timeout_seconds: int,
    heartbeat_source: str,
    now: datetime | None = None,
) -> datetime:
    current_time = as_utc(now or datetime.now(timezone.utc))
    worker_run.status = RecordStatus.RUNNING
    worker_run.started_at = worker_run.started_at or current_time
    worker_run.last_heartbeat_at = current_time
    worker_run.lease_expires_at = current_time + timedelta(seconds=timeout_seconds)
    worker_run.heartbeat_source = heartbeat_source
    return current_time


def recover_stale_worker_runs(
    session: Session,
    *,
    tool_call: ToolCall,
    now: datetime | None = None,
    timeout_seconds: int,
    worker_id: str | None = None,
    worker_adapter: str | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        tool_call.status = tool_call.status.FAILED
        tool_call.error_code = "invalid_arguments"
        tool_call.error_message = "timeout_seconds must be positive"
        return {"error": "invalid_arguments"}

    current_time = as_utc(now or datetime.now(timezone.utc))
    cutoff = current_time - timedelta(seconds=timeout_seconds)

    query = (
        select(WorkerRun)
        .where(WorkerRun.local_user_id == tool_call.user_id)
        .where(WorkerRun.status == RecordStatus.RUNNING)
        .order_by(WorkerRun.updated_at.asc(), WorkerRun.created_at.asc())
    )
    if tool_call.project_id:
        query = query.where(WorkerRun.project_id == tool_call.project_id)
    if worker_id:
        query = query.where(WorkerRun.worker_id == worker_id)
    if worker_adapter:
        query = query.where(WorkerRun.adapter_kind == worker_adapter)

    candidates = session.scalars(query).all()
    recovered: list[dict[str, Any]] = []

    for worker_run in candidates:
        last_liveness_at = as_utc(worker_run_liveness_at(worker_run))
        lease_expires_at = (
            as_utc(worker_run.lease_expires_at) if worker_run.lease_expires_at is not None else None
        )
        if lease_expires_at is not None:
            if lease_expires_at > current_time:
                continue
        elif last_liveness_at > cutoff:
            continue

        worker_run.status = RecordStatus.FAILED
        worker_run.failed_at = current_time
        worker_run.error_code = STALE_WORKER_RUN_ERROR_CODE
        worker_run.error_message = "WorkerRun stale timeout exceeded"

        attempt = session.get(TaskAttempt, worker_run.task_attempt_id)
        if attempt and attempt.status in RECOVERABLE_ATTEMPT_STATUSES:
            attempt.status = TaskAttemptStatus.WORKER_FAILED
            attempt.failed_at = current_time
            attempt.error_code = STALE_WORKER_RUN_ERROR_CODE
            attempt.error_message = "WorkerRun stale timeout exceeded"

        record_audit_event(
            session,
            event_type="worker_run.stale_recovered",
            message="Stale WorkerRun recovered",
            local_user_id=tool_call.user_id,
            project_id=worker_run.project_id,
            repository_id=worker_run.repository_id,
            agent_run_id=tool_call.agent_run_id,
            tool_call_id=tool_call.id,
            metadata={
                "worker_run_id": worker_run.id,
                "task_attempt_id": worker_run.task_attempt_id,
                "task_id": worker_run.task_id,
                "worker_id": worker_run.worker_id,
                "timeout_seconds": timeout_seconds,
                "last_liveness_at": last_liveness_at.isoformat(),
                "lease_expires_at": lease_expires_at.isoformat() if lease_expires_at else None,
                "recovery_trigger": "owner_tool_call",
                "worktree_preserved": True,
                "automatic_retry": False,
                "new_attempt_created": False,
            },
        )

        recovered.append(
            {
                "worker_run_id": worker_run.id,
                "task_attempt_id": worker_run.task_attempt_id,
                "worker_id": worker_run.worker_id,
                "last_liveness_at": last_liveness_at.isoformat(),
            }
        )

    session.flush()
    return {
        "status": "succeeded",
        "recovered_count": len(recovered),
        "timeout_seconds": timeout_seconds,
        "recovered": recovered,
        "automatic_retry": False,
        "new_attempt_created": False,
        "worktree_preserved": True,
    }
