"""add task write scope

Revision ID: 20260622_0010
Revises: 49a6fdce6fff
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260622_0010"
down_revision: str | None = "49a6fdce6fff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("write_scope_json", sa.JSON(), nullable=True))
    tasks = sa.table("tasks", sa.column("write_scope_json", sa.JSON()))
    op.execute(
        tasks.update()
        .where(tasks.c.write_scope_json.is_(None))
        .values(write_scope_json={"mode": "paths", "paths": ["."], "allow_new_files": True})
    )


def downgrade() -> None:
    op.drop_column("tasks", "write_scope_json")
