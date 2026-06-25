from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.db.models import Task, TaskAttempt, TaskAttemptStatus


EXPLICIT_RETRY_SOURCE_STATUSES = {
    TaskAttemptStatus.COMMITTED,
    TaskAttemptStatus.REVIEWING,
    TaskAttemptStatus.REJECTED,
    TaskAttemptStatus.WORKER_FAILED,
    TaskAttemptStatus.FAILED,
}

# These statuses represent an already-active or already-adopted line of work.
# A follow-up must not create another Attempt while one of these exists for the same Task.
RETRY_BLOCKING_ATTEMPT_STATUSES = {
    TaskAttemptStatus.CREATED,
    TaskAttemptStatus.QUEUED_WORKER,
    TaskAttemptStatus.PREPARING_WORKTREE,
    TaskAttemptStatus.RUNNING_WORKER,
    TaskAttemptStatus.WAITING_FOR_COMMIT,
    TaskAttemptStatus.COMMITTED,
    TaskAttemptStatus.REVIEWING,
    TaskAttemptStatus.ACCEPTED,
    TaskAttemptStatus.RETRY_REQUESTED,
    TaskAttemptStatus.MERGE_READY,
    TaskAttemptStatus.MERGED,
}


@dataclass(frozen=True)
class ExplicitRetryPolicyError(ValueError):
    code: str
    message: str
    blocking_attempt_id: str | None = None
    blocking_attempt_status: str | None = None

    def detail(self) -> dict[str, str]:
        detail = {"code": self.code, "message": self.message}
        if self.blocking_attempt_id:
            detail["blocking_attempt_id"] = self.blocking_attempt_id
        if self.blocking_attempt_status:
            detail["blocking_attempt_status"] = self.blocking_attempt_status
        return detail


def find_retry_blocking_attempt(
    session: Session,
    *,
    task: Task,
    source_attempt: TaskAttempt,
) -> TaskAttempt | None:
    return session.scalar(
        select(TaskAttempt)
        .where(TaskAttempt.task_id == task.id)
        .where(TaskAttempt.id != source_attempt.id)
        .where(TaskAttempt.status.in_(RETRY_BLOCKING_ATTEMPT_STATUSES))
        .order_by(TaskAttempt.attempt_number.asc(), TaskAttempt.created_at.asc())
    )


def ensure_explicit_retry_allowed(
    session: Session,
    *,
    task: Task,
    source_attempt: TaskAttempt,
) -> None:
    if source_attempt.task_id != task.id:
        raise ExplicitRetryPolicyError(
            code="source_attempt_task_mismatch",
            message="Source attempt does not belong to the task",
        )

    if source_attempt.status not in EXPLICIT_RETRY_SOURCE_STATUSES:
        raise ExplicitRetryPolicyError(
            code="attempt_not_follow_up_source",
            message="Attempt cannot be used for follow-up",
        )

    blocking_attempt = find_retry_blocking_attempt(
        session,
        task=task,
        source_attempt=source_attempt,
    )
    if blocking_attempt is not None:
        raise ExplicitRetryPolicyError(
            code="active_attempt_exists",
            message="Task already has an active or adopted attempt; explicit follow-up is blocked",
            blocking_attempt_id=blocking_attempt.id,
            blocking_attempt_status=blocking_attempt.status.value,
        )
