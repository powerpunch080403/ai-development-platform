"""add_task_work_room_messages

Revision ID: 20260624_0011
Revises: 0c1f25ef8dc8
Create Date: 2026-06-24 20:35:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260624_0011"
down_revision: str | None = "0c1f25ef8dc8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_work_room_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("local_user_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("repository_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("task_attempt_id", sa.String(length=36), nullable=True),
        sa.Column("worker_id", sa.String(length=36), nullable=True),
        sa.Column("worker_run_id", sa.String(length=36), nullable=True),
        sa.Column("process_run_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column(
            "sender",
            sa.Enum(
                "owner",
                "worker",
                "system",
                name="workroommessagesender",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "message_type",
            sa.Enum(
                "owner_instruction",
                "owner_feedback",
                "worker_report",
                "worker_question",
                "system_event",
                name="workroommessagetype",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifact_refs.id"]),
        sa.ForeignKeyConstraint(["local_user_id"], ["local_users.id"]),
        sa.ForeignKeyConstraint(["process_run_id"], ["process_runs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["project_repositories.id"]),
        sa.ForeignKeyConstraint(["task_attempt_id"], ["task_attempts.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
        sa.ForeignKeyConstraint(["worker_run_id"], ["worker_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_work_room_messages_attempt_id",
        "task_work_room_messages",
        ["task_attempt_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_work_room_messages_local_user_id",
        "task_work_room_messages",
        ["local_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_work_room_messages_task_id",
        "task_work_room_messages",
        ["task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_task_work_room_messages_task_id", table_name="task_work_room_messages")
    op.drop_index("ix_task_work_room_messages_local_user_id", table_name="task_work_room_messages")
    op.drop_index("ix_task_work_room_messages_attempt_id", table_name="task_work_room_messages")
    op.drop_table("task_work_room_messages")
