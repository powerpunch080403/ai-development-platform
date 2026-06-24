"""merge_alembic_heads

Revision ID: 20260624_0012
Revises: 20260624_0011, 805fea55f3ba
Create Date: 2026-06-24 22:20:00.000000
"""
from collections.abc import Sequence


revision: str = "20260624_0012"
down_revision: tuple[str, str] = ("20260624_0011", "805fea55f3ba")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
