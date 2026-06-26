"""add_owner_provider_runtime_fields

Revision ID: 20260626_0015
Revises: 20260624_0014
Create Date: 2026-06-26 00:00:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260626_0015"
down_revision: str | None = "20260624_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("provider_kind", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("provider_model", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("runtime_version", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("provider_metadata_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("error_category", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("retry_after", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_column("retry_after")
        batch.drop_column("error_category")
        batch.drop_column("provider_metadata_json")
        batch.drop_column("runtime_version")
        batch.drop_column("provider_model")
        batch.drop_column("provider_kind")
