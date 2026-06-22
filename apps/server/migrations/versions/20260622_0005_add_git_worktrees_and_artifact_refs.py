"""Add git worktrees and artifact refs."""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20260622_0005"
down_revision: str | None = "20260622_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(name: str, *v: str) -> sa.Enum:
    return sa.Enum(*v, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "git_worktrees",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "repository_id", sa.String(36), sa.ForeignKey("project_repositories.id"), nullable=False
        ),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column(
            "task_attempt_id", sa.String(36), sa.ForeignKey("task_attempts.id"), nullable=False
        ),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("workers.id")),
        sa.Column("worktree_path", sa.Text(), nullable=False),
        sa.Column("branch_name", sa.String(300), nullable=False),
        sa.Column("base_branch", sa.String(300)),
        sa.Column("base_commit_sha", sa.String(64)),
        sa.Column("result_commit_sha", sa.String(64)),
        sa.Column(
            "status",
            enum(
                "git_worktree_status",
                "planned",
                "creating",
                "ready",
                "in_use",
                "dirty_result",
                "committed",
                "reviewing",
                "merge_ready",
                "merged",
                "abandoned",
                "cleanup_pending",
                "cleaned",
                "failed",
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("prepared_at", sa.DateTime(timezone=True)),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.Column("cleanup_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("task_attempt_id", name="uq_git_worktree_attempt"),
    )
    for n, c in (
        ("repository_id", "repository_id"),
        ("project_id", "project_id"),
        ("task_id", "task_id"),
        ("attempt_id", "task_attempt_id"),
    ):
        op.create_index(f"ix_git_worktrees_{n}", "git_worktrees", [c])
    op.create_table(
        "artifact_refs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_type", sa.String(100), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id")),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id")),
        sa.Column("repository_id", sa.String(36), sa.ForeignKey("project_repositories.id")),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id")),
        sa.Column("task_attempt_id", sa.String(36), sa.ForeignKey("task_attempts.id")),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("workers.id")),
        sa.Column("tool_call_id", sa.String(36), sa.ForeignKey("tool_calls.id")),
        sa.Column(
            "kind",
            enum(
                "artifact_kind",
                "diff_patch",
                "git_status",
                "commit_log",
                "worker_report",
                "error_log",
                "cli_transcript",
                "generated_report",
                "unknown",
            ),
            nullable=False,
        ),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("retention_policy", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_artifact_refs_attempt_id", "artifact_refs", ["task_attempt_id"])
    op.create_index("ix_artifact_refs_local_user_id", "artifact_refs", ["local_user_id"])


def downgrade() -> None:
    op.drop_table("artifact_refs")
    op.drop_table("git_worktrees")
