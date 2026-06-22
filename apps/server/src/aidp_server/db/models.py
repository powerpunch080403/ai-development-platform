from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
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


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class RepositoryRole(StrEnum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    DOCS = "docs"
    INFRA = "infra"
    UNKNOWN = "unknown"


class VcsType(StrEnum):
    GIT = "git"
    UNKNOWN = "unknown"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    WORKER = "worker"


class ContentType(StrEnum):
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"
    ERROR = "error"


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    PREPARING_CONTEXT = "preparing_context"
    RUNNING_MODEL = "running_model"
    EXECUTING_TOOL = "executing_tool"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_WORKER = "waiting_for_worker"
    REVIEWING_WORKER_RESULT = "reviewing_worker_result"
    RETRY_SCHEDULED = "retry_scheduled"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRunStepType(StrEnum):
    MODEL = "model"
    TOOL_CALL = "tool_call"
    MESSAGE = "message"
    SYSTEM = "system"
    REVIEW = "review"


class RecordStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class ToolCallerType(StrEnum):
    OWNER = "owner"
    UI = "ui"
    WORKER = "worker"
    SYSTEM = "system"
    CENTRAL_AUTHORITY = "central_authority"


class ToolCallStatus(StrEnum):
    CREATED = "created"
    POLICY_CHECKING = "policy_checking"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED_DUPLICATE = "skipped_duplicate"


class AuditSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


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


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_local_user_id", "local_user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(
            ProjectStatus,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=ProjectStatus.ACTIVE,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectRepository(TimestampMixin, Base):
    __tablename__ = "project_repositories"
    __table_args__ = (
        Index("ix_project_repositories_project_id", "project_id"),
        Index("ix_project_repositories_local_user_id", "local_user_id"),
        Index(
            "uq_project_repositories_one_primary",
            "project_id",
            unique=True,
            sqlite_where=text("repository_role = 'primary' AND archived_at IS NULL"),
        ),
        UniqueConstraint("project_id", "repository_path", name="uq_project_repository_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    repository_path: Mapped[str] = mapped_column(Text, nullable=False)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_role: Mapped[RepositoryRole] = mapped_column(
        Enum(
            RepositoryRole,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=RepositoryRole.UNKNOWN,
        nullable=False,
    )
    vcs_type: Mapped[VcsType] = mapped_column(
        Enum(
            VcsType,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=VcsType.GIT,
        nullable=False,
    )
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_dirty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_status_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def enum_column(enum_type: type[StrEnum]) -> Enum:
    return Enum(
        enum_type,
        native_enum=False,
        create_constraint=True,
        values_callable=lambda values: [item.value for item in values],
    )


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_local_user_id", "local_user_id"),
        Index("ix_conversations_project_id", "project_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="New Conversation")
    status: Mapped[ConversationStatus] = mapped_column(
        enum_column(ConversationStatus), nullable=False, default=ConversationStatus.ACTIVE
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_local_user_id", "local_user_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    role: Mapped[MessageRole] = mapped_column(enum_column(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[ContentType] = mapped_column(
        enum_column(ContentType), nullable=False, default=ContentType.TEXT
    )


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index("ix_agent_runs_conversation_id", "conversation_id"),
        Index("ix_agent_runs_local_user_id", "local_user_id"),
        Index("ix_agent_runs_project_id", "project_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    requested_by_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_column(AgentRunStatus), nullable=False, default=AgentRunStatus.QUEUED
    )
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    input_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", name="fk_agent_runs_input_message", use_alter=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentRunStep(TimestampMixin, Base):
    __tablename__ = "agent_run_steps"
    __table_args__ = (
        Index("ix_agent_run_steps_agent_run_id", "agent_run_id"),
        UniqueConstraint("agent_run_id", "step_index", name="uq_agent_run_step_index"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[AgentRunStepType] = mapped_column(
        enum_column(AgentRunStepType), nullable=False
    )
    status: Mapped[RecordStatus] = mapped_column(
        enum_column(RecordStatus), nullable=False, default=RecordStatus.CREATED
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ToolRegistryEntry(TimestampMixin, Base):
    __tablename__ = "tool_registry"
    __table_args__ = (
        UniqueConstraint("tool_name", "tool_version", name="uq_tool_registry_name_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    output_schema_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    has_side_effect: Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    required_grants: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    scope_evaluator: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    approval_behavior: Mapped[str] = mapped_column(String(100), nullable=False)
    audit_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ToolCall(TimestampMixin, Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("ix_tool_calls_user_id", "user_id"),
        Index("ix_tool_calls_agent_run_id", "agent_run_id"),
        Index("ix_tool_calls_idempotency", "tool_name", "idempotency_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_version: Mapped[str] = mapped_column(String(50), nullable=False)
    tool_category: Mapped[str] = mapped_column(String(100), nullable=False)
    caller_type: Mapped[ToolCallerType] = mapped_column(enum_column(ToolCallerType), nullable=False)
    caller_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("local_users.id"), nullable=True)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    agent_run_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_run_steps.id"), nullable=True
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_repositories.id"), nullable=True
    )
    work_item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    worker_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    arguments_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[ToolCallStatus] = mapped_column(
        enum_column(ToolCallStatus), nullable=False, default=ToolCallStatus.CREATED
    )
    result_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(TimestampMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_local_user_id", "local_user_id"),
        Index("ix_audit_events_created_at", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str | None] = mapped_column(ForeignKey("local_users.id"), nullable=True)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_repositories.id"), nullable=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(ForeignKey("tool_calls.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[AuditSeverity] = mapped_column(
        enum_column(AuditSeverity), nullable=False, default=AuditSeverity.INFO
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
