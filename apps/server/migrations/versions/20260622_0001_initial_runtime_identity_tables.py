"""Create initial Local Runtime identity tables.

Revision ID: 20260622_0001
Revises:
Create Date: 2026-06-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260622_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


account_link_status = sa.Enum(
    "local_only",
    "linked",
    "unlinked",
    "revoked",
    name="account_link_status",
    native_enum=False,
    create_constraint=True,
)
device_type = sa.Enum(
    "desktop_app",
    "web_ui",
    "local_runtime",
    "worker_node",
    "test_runner_node",
    "unknown",
    name="device_type",
    native_enum=False,
    create_constraint=True,
)
pairing_purpose = sa.Enum(
    "web_ui",
    "desktop_app",
    "worker_node",
    "test_runner_node",
    "recovery",
    name="pairing_purpose",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "local_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("account_id", sa.String(length=200), nullable=True),
        sa.Column(
            "account_link_status",
            account_link_status,
            nullable=False,
            server_default="local_only",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_local_users_account_id", "local_users", ["account_id"])

    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("local_user_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=200), nullable=True),
        sa.Column("device_type", device_type, nullable=False, server_default="unknown"),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("fingerprint_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["local_user_id"], ["local_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_devices_local_user_id", "devices", ["local_user_id"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("local_user_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=200), nullable=True),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["local_user_id"], ["local_users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_sessions_device_id", "sessions", ["device_id"])
    op.create_index("ix_sessions_local_user_id", "sessions", ["local_user_id"])

    op.create_table(
        "pairing_codes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("purpose", pairing_purpose, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_device_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["created_by_device_id"], ["devices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index("ix_pairing_codes_expires_at", "pairing_codes", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_pairing_codes_expires_at", table_name="pairing_codes")
    op.drop_table("pairing_codes")
    op.drop_index("ix_sessions_local_user_id", table_name="sessions")
    op.drop_index("ix_sessions_device_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_devices_local_user_id", table_name="devices")
    op.drop_table("devices")
    op.drop_index("ix_local_users_account_id", table_name="local_users")
    op.drop_table("local_users")
