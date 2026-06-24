"""add_explicit_queued_worker_states

Revision ID: 20260624_0013
Revises: 20260624_0012
Create Date: 2026-06-24 23:45:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260624_0013"
down_revision: str | None = "20260624_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_RECORD_STATUSES = ("created", "running", "succeeded", "failed", "cancelled", "skipped")
NEW_RECORD_STATUSES = ("created", "queued", "running", "succeeded", "failed", "cancelled", "skipped")

OLD_TASK_ATTEMPT_STATUSES = (
    "created",
    "preparing_worktree",
    "running_worker",
    "waiting_for_commit",
    "committed",
    "worker_failed",
    "reviewing",
    "accepted",
    "rejected",
    "retry_requested",
    "merge_ready",
    "merged",
    "abandoned",
    "cancelled",
    "failed",
)
NEW_TASK_ATTEMPT_STATUSES = (
    "created",
    "queued_worker",
    "preparing_worktree",
    "running_worker",
    "waiting_for_commit",
    "committed",
    "worker_failed",
    "reviewing",
    "accepted",
    "rejected",
    "retry_requested",
    "merge_ready",
    "merged",
    "abandoned",
    "cancelled",
    "failed",
)


def _record_status(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="recordstatus", native_enum=False, create_constraint=True)


def _task_attempt_status(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="task_attempt_status", native_enum=False, create_constraint=True)


def upgrade() -> None:
    with op.batch_alter_table("worker_runs") as batch:
        batch.alter_column(
            "status",
            existing_type=_record_status(OLD_RECORD_STATUSES),
            type_=_record_status(NEW_RECORD_STATUSES),
            existing_nullable=False,
        )

    with op.batch_alter_table("task_attempts") as batch:
        batch.alter_column(
            "status",
            existing_type=_task_attempt_status(OLD_TASK_ATTEMPT_STATUSES),
            type_=_task_attempt_status(NEW_TASK_ATTEMPT_STATUSES),
            existing_nullable=False,
        )

    op.execute("UPDATE worker_runs SET status = 'queued' WHERE status = 'created'")
    op.execute(
        """
        UPDATE task_attempts
        SET status = 'queued_worker'
        WHERE status = 'created'
          AND id IN (
              SELECT task_attempt_id
              FROM worker_runs
              WHERE status = 'queued'
          )
        """
    )


def downgrade() -> None:
    op.execute("UPDATE task_attempts SET status = 'created' WHERE status = 'queued_worker'")
    op.execute("UPDATE worker_runs SET status = 'created' WHERE status = 'queued'")

    with op.batch_alter_table("task_attempts") as batch:
        batch.alter_column(
            "status",
            existing_type=_task_attempt_status(NEW_TASK_ATTEMPT_STATUSES),
            type_=_task_attempt_status(OLD_TASK_ATTEMPT_STATUSES),
            existing_nullable=False,
        )

    with op.batch_alter_table("worker_runs") as batch:
        batch.alter_column(
            "status",
            existing_type=_record_status(NEW_RECORD_STATUSES),
            type_=_record_status(OLD_RECORD_STATUSES),
            existing_nullable=False,
        )
