from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from aidp_server.db.models import RecordStatus, WorkerRun

EXTERNAL_CLI_ADAPTER_KINDS = {
    "external_cli_dry_run",
    "codex_cli",
    "antigravity_cli",
    "custom_cli",
}

ACTIVE_WORKER_RUN_STATUSES = {
    RecordStatus.CREATED,
    RecordStatus.RUNNING,
}

def find_active_external_cli_worker_run(session: Session, task_attempt_id: str) -> WorkerRun | None:
    return session.scalar(
        select(WorkerRun).where(
            WorkerRun.task_attempt_id == task_attempt_id,
            WorkerRun.adapter_kind.in_(EXTERNAL_CLI_ADAPTER_KINDS),
            WorkerRun.status.in_(ACTIVE_WORKER_RUN_STATUSES),
        )
    )

def assert_no_active_external_cli_worker_run(session: Session, task_attempt_id: str) -> None:
    active_run = find_active_external_cli_worker_run(session, task_attempt_id)
    if active_run:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ACTIVE_EXTERNAL_CLI_RUN_EXISTS",
                "worker_run_id": active_run.id,
                "task_attempt_id": task_attempt_id,
            }
        )
