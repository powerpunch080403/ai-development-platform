"""Add projects and project repositories.

Revision ID: 20260622_0002
Revises: 20260622_0001
Create Date: 2026-06-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260622_0002"
down_revision: str | None = "20260622_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


project_status = sa.Enum(
    "active", "archived", name="project_status", native_enum=False, create_constraint=True
)
repository_role = sa.Enum(
    "primary",
    "supporting",
    "docs",
    "infra",
    "unknown",
    name="repository_role",
    native_enum=False,
    create_constraint=True,
)
vcs_type = sa.Enum("git", "unknown", name="vcs_type", native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("local_user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", project_status, server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["local_user_id"], ["local_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_local_user_id", "projects", ["local_user_id"])

    op.create_table(
        "project_repositories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("local_user_id", sa.String(length=36), nullable=False),
        sa.Column("repository_path", sa.Text(), nullable=False),
        sa.Column("repository_name", sa.String(length=255), nullable=False),
        sa.Column("repository_role", repository_role, server_default="unknown", nullable=False),
        sa.Column("vcs_type", vcs_type, server_default="git", nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("current_branch", sa.String(length=255), nullable=True),
        sa.Column("last_commit_sha", sa.String(length=64), nullable=True),
        sa.Column("is_dirty", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_status_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["local_user_id"], ["local_users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "repository_path", name="uq_project_repository_path"),
    )
    op.create_index("ix_project_repositories_project_id", "project_repositories", ["project_id"])
    op.create_index(
        "ix_project_repositories_local_user_id", "project_repositories", ["local_user_id"]
    )
    op.create_index(
        "uq_project_repositories_one_primary",
        "project_repositories",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("repository_role = 'primary' AND archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_project_repositories_one_primary", table_name="project_repositories")
    op.drop_index("ix_project_repositories_local_user_id", table_name="project_repositories")
    op.drop_index("ix_project_repositories_project_id", table_name="project_repositories")
    op.drop_table("project_repositories")
    op.drop_index("ix_projects_local_user_id", table_name="projects")
    op.drop_table("projects")
