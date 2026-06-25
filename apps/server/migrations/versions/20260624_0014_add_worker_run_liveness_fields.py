"""add_worker_run_liveness_fields

Revision ID: 20260624_0014
Revises: 20260624_0013
Create Date: 2026-06-25 03:20:00.000000
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260624_0014"
down_revision: str | None = "20260624_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("worker_runs") as batch:
        batch.add_column(sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("heartbeat_source", sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("worker_runs") as batch:
        batch.drop_column("heartbeat_source")
        batch.drop_column("lease_expires_at")
        batch.drop_column("last_heartbeat_at")
