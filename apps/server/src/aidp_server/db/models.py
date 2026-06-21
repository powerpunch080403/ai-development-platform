from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from aidp_server.db.base import Base


def new_uuid() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccountLinkStatus(StrEnum):
    LOCAL_ONLY = "local_only"
    LINKED = "linked"
    UNLINKED = "unlinked"
    REVOKED = "revoked"


class DeviceType(StrEnum):
    DESKTOP_APP = "desktop_app"
    WEB_UI = "web_ui"
    LOCAL_RUNTIME = "local_runtime"
    WORKER_NODE = "worker_node"
    TEST_RUNNER_NODE = "test_runner_node"
    UNKNOWN = "unknown"


class PairingPurpose(StrEnum):
    WEB_UI = "web_ui"
    DESKTOP_APP = "desktop_app"
    WORKER_NODE = "worker_node"
    TEST_RUNNER_NODE = "test_runner_node"
    RECOVERY = "recovery"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class LocalUser(TimestampMixin, Base):
    __tablename__ = "local_users"
    __table_args__ = (Index("ix_local_users_account_id", "account_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_link_status: Mapped[AccountLinkStatus] = mapped_column(
        Enum(
            AccountLinkStatus,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=AccountLinkStatus.LOCAL_ONLY,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Device(TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_local_user_id", "local_user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    device_type: Mapped[DeviceType] = mapped_column(
        Enum(
            DeviceType,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=DeviceType.UNKNOWN,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    fingerprint_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RuntimeSession(TimestampMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_device_id", "device_id"),
        Index("ix_sessions_local_user_id", "local_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PairingCode(TimestampMixin, Base):
    __tablename__ = "pairing_codes"
    __table_args__ = (Index("ix_pairing_codes_expires_at", "expires_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    purpose: Mapped[PairingPurpose] = mapped_column(
        Enum(
            PairingPurpose,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_device_id: Mapped[str | None] = mapped_column(
        ForeignKey("devices.id"), nullable=True
    )
