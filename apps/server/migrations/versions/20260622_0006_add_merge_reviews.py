"""Add merge reviews."""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20260622_0006"
down_revision: str | None = "20260622_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "merge_reviews",
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
        sa.Column(
            "git_worktree_id", sa.String(36), sa.ForeignKey("git_worktrees.id"), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "created",
                "reviewing",
                "approved",
                "merge_prepared",
                "merged",
                "rejected",
                "failed",
                "cancelled",
                name="merge_review_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("review_summary", sa.Text()),
        sa.Column("base_branch", sa.String(300), nullable=False),
        sa.Column("base_commit_sha", sa.String(64), nullable=False),
        sa.Column("result_branch", sa.String(300), nullable=False),
        sa.Column("result_commit_sha", sa.String(64), nullable=False),
        sa.Column("merge_commit_sha", sa.String(64)),
        sa.Column("diff_artifact_id", sa.String(36), sa.ForeignKey("artifact_refs.id")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("merged_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by_session_id", sa.String(36), sa.ForeignKey("sessions.id")),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_merge_reviews_local_user_id", "merge_reviews", ["local_user_id"])
    op.create_index("ix_merge_reviews_attempt_id", "merge_reviews", ["task_attempt_id"])


def downgrade() -> None:
    op.drop_table("merge_reviews")
