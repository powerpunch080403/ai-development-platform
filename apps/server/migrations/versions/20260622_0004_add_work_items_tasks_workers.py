"""Add work items, tasks, attempts, and workers.

Revision ID: 20260622_0004
Revises: 20260622_0003
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20260622_0004"
down_revision: str | None = "20260622_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def created() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("parent_work_item_id", sa.String(36), sa.ForeignKey("work_items.id")),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column(
            "work_item_type",
            enum(
                "work_item_type",
                "goal",
                "feature",
                "bug",
                "research",
                "improvement",
                "chore",
                "unknown",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            enum(
                "work_item_status",
                "draft",
                "active",
                "blocked",
                "completed",
                "cancelled",
                "archived",
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column("priority", sa.Integer()),
        created(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_work_items_local_user_id", "work_items", ["local_user_id"])
    op.create_index("ix_work_items_project_id", "work_items", ["project_id"])
    op.create_index("ix_work_items_parent_id", "work_items", ["parent_work_item_id"])
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("repository_id", sa.String(36), sa.ForeignKey("project_repositories.id")),
        sa.Column("work_item_id", sa.String(36), sa.ForeignKey("work_items.id")),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id")),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id")),
        sa.Column("created_by_session_id", sa.String(36), sa.ForeignKey("sessions.id")),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column(
            "status",
            enum(
                "task_status",
                "draft",
                "ready",
                "queued",
                "running",
                "waiting_for_review",
                "changes_requested",
                "completed",
                "blocked",
                "cancelled",
                "failed",
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("risk_level", enum("risk_level", "R0", "R1", "R2", "R3", "R4"), nullable=False),
        sa.Column(
            "requested_worker_kind",
            enum("worker_kind", "mock", "manual", "external_cli", "system", "unknown"),
        ),
        created(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_tasks_local_user_id", "tasks", ["local_user_id"])
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_work_item_id", "tasks", ["work_item_id"])
    op.create_table(
        "workers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id")),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column(
            "worker_kind",
            enum("worker_kind_worker", "mock", "manual", "external_cli", "system", "unknown"),
            nullable=False,
        ),
        sa.Column(
            "status",
            enum(
                "worker_status",
                "available",
                "claimed",
                "running",
                "heartbeat_lost",
                "expired",
                "released",
                "completed",
                "cancelled",
                "failed",
                "revoked",
            ),
            server_default="available",
            nullable=False,
        ),
        sa.Column("capabilities_json", sa.JSON()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_workers_local_user_id", "workers", ["local_user_id"])
    op.create_table(
        "task_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("repository_id", sa.String(36), sa.ForeignKey("project_repositories.id")),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("workers.id")),
        sa.Column("claimed_by_worker_id", sa.String(36), sa.ForeignKey("workers.id")),
        sa.Column(
            "status",
            enum(
                "task_attempt_status",
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
            ),
            server_default="created",
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("result_summary", sa.Text()),
        created(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("task_id", "attempt_number", name="uq_task_attempt_number"),
    )
    op.create_index("ix_task_attempts_task_id", "task_attempts", ["task_id"])
    op.create_index("ix_task_attempts_local_user_id", "task_attempts", ["local_user_id"])


def downgrade() -> None:
    op.drop_table("task_attempts")
    op.drop_table("workers")
    op.drop_table("tasks")
    op.drop_table("work_items")
