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
    QUEUED = "queued"
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
    REJECTED = "rejected"
    SKIPPED_DUPLICATE = "skipped_duplicate"


class AuditSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class WorkItemType(StrEnum):
    GOAL = "goal"
    FEATURE = "feature"
    BUG = "bug"
    RESEARCH = "research"
    IMPROVEMENT = "improvement"
    CHORE = "chore"
    UNKNOWN = "unknown"


class WorkItemStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class TaskStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_REVIEW = "waiting_for_review"
    CHANGES_REQUESTED = "changes_requested"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RiskLevel(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


class WorkerKind(StrEnum):
    MOCK = "mock"
    MANUAL = "manual"
    EXTERNAL_CLI = "external_cli"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class TaskAttemptStatus(StrEnum):
    CREATED = "created"
    QUEUED_WORKER = "queued_worker"
    PREPARING_WORKTREE = "preparing_worktree"
    RUNNING_WORKER = "running_worker"
    WAITING_FOR_COMMIT = "waiting_for_commit"
    COMMITTED = "committed"
    WORKER_FAILED = "worker_failed"
    REVIEWING = "reviewing"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RETRY_REQUESTED = "retry_requested"
    MERGE_READY = "merge_ready"
    MERGED = "merged"
    ABANDONED = "abandoned"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WorkerStatus(StrEnum):
    AVAILABLE = "available"
    CLAIMED = "claimed"
    RUNNING = "running"
    HEARTBEAT_LOST = "heartbeat_lost"
    EXPIRED = "expired"
    RELEASED = "released"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    REVOKED = "revoked"


class GitWorktreeStatus(StrEnum):
    PLANNED = "planned"
    CREATING = "creating"
    READY = "ready"
    IN_USE = "in_use"
    DIRTY_RESULT = "dirty_result"
    COMMITTED = "committed"
    REVIEWING = "reviewing"
    MERGE_READY = "merge_ready"
    MERGED = "merged"
    ABANDONED = "abandoned"
    CLEANUP_PENDING = "cleanup_pending"
    CLEANED = "cleaned"
    FAILED = "failed"


class ArtifactKind(StrEnum):
    DIFF_PATCH = "diff_patch"
    GIT_STATUS = "git_status"
    COMMIT_LOG = "commit_log"
    WORKER_REPORT = "worker_report"
    ERROR_LOG = "error_log"
    CLI_TRANSCRIPT = "cli_transcript"
    GENERATED_REPORT = "generated_report"
    UNKNOWN = "unknown"


class MergeReviewStatus(StrEnum):
    CREATED = "created"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    MERGE_PREPARED = "merge_prepared"
    MERGED = "merged"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ApprovalMode(StrEnum):
    ASK_FOR_APPROVAL = "ask_for_approval"
    APPROVE_ON_MY_BEHALF = "approve_on_my_behalf"
    FULL_ACCESS = "full_access"
    CUSTOM = "custom"


class PolicyDecisionResult(StrEnum):
    ALLOW = "allow"
    APPROVAL_REQUIRED = "approval_required"
    DENY = "deny"


class ProcessRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


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
    working_scope_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
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
    provider_kind: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_after: Mapped[str | None] = mapped_column(String(200), nullable=True)


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
    provider_kind: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_after: Mapped[str | None] = mapped_column(String(200), nullable=True)


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
    result_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    provider_kind: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_after: Mapped[str | None] = mapped_column(String(200), nullable=True)
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


class WorkItem(TimestampMixin, Base):
    __tablename__ = "work_items"
    __table_args__ = (
        Index("ix_work_items_local_user_id", "local_user_id"),
        Index("ix_work_items_project_id", "project_id"),
        Index("ix_work_items_parent_id", "parent_work_item_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    parent_work_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("work_items.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_item_type: Mapped[WorkItemType] = mapped_column(enum_column(WorkItemType), nullable=False)
    status: Mapped[WorkItemStatus] = mapped_column(
        enum_column(WorkItemStatus), nullable=False, default=WorkItemStatus.ACTIVE
    )
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_local_user_id", "local_user_id"),
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_work_item_id", "work_item_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_repositories.id"), nullable=True
    )
    work_item_id: Mapped[str | None] = mapped_column(ForeignKey("work_items.id"), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    created_by_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    write_scope_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        enum_column(TaskStatus), nullable=False, default=TaskStatus.DRAFT
    )
    risk_level: Mapped[RiskLevel] = mapped_column(enum_column(RiskLevel), nullable=False)
    requested_worker_kind: Mapped[WorkerKind | None] = mapped_column(
        enum_column(WorkerKind), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class Worker(Base):
    __tablename__ = "workers"
    __table_args__ = (Index("ix_workers_local_user_id", "local_user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    worker_kind: Mapped[WorkerKind] = mapped_column(enum_column(WorkerKind), nullable=False)
    status: Mapped[WorkerStatus] = mapped_column(
        enum_column(WorkerStatus), nullable=False, default=WorkerStatus.AVAILABLE
    )
    capabilities_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskAttempt(TimestampMixin, Base):
    __tablename__ = "task_attempts"
    __table_args__ = (
        Index("ix_task_attempts_task_id", "task_id"),
        Index("ix_task_attempts_local_user_id", "local_user_id"),
        UniqueConstraint("task_id", "attempt_number", name="uq_task_attempt_number"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("project_repositories.id"))
    worker_id: Mapped[str | None] = mapped_column(ForeignKey("workers.id"))
    claimed_by_worker_id: Mapped[str | None] = mapped_column(ForeignKey("workers.id"))
    status: Mapped[TaskAttemptStatus] = mapped_column(
        enum_column(TaskAttemptStatus), nullable=False, default=TaskAttemptStatus.CREATED
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    result_summary: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class WorkerRun(TimestampMixin, Base):
    __tablename__ = "worker_runs"
    __table_args__ = (
        Index("ix_worker_runs_task_id", "task_id"),
        Index("ix_worker_runs_attempt_id", "task_attempt_id"),
        Index("ix_worker_runs_worker_id", "worker_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("project_repositories.id"))
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    task_attempt_id: Mapped[str] = mapped_column(ForeignKey("task_attempts.id"), nullable=False)
    worker_id: Mapped[str] = mapped_column(ForeignKey("workers.id"), nullable=False)
    adapter_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        enum_column(RecordStatus), nullable=False, default=RecordStatus.CREATED
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_source: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class GitWorktree(TimestampMixin, Base):
    __tablename__ = "git_worktrees"
    __table_args__ = (
        Index("ix_git_worktrees_repository_id", "repository_id"),
        Index("ix_git_worktrees_project_id", "project_id"),
        Index("ix_git_worktrees_task_id", "task_id"),
        Index("ix_git_worktrees_attempt_id", "task_attempt_id"),
        UniqueConstraint("task_attempt_id", name="uq_git_worktree_attempt"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("project_repositories.id"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    task_attempt_id: Mapped[str] = mapped_column(ForeignKey("task_attempts.id"), nullable=False)
    worker_id: Mapped[str | None] = mapped_column(ForeignKey("workers.id"))
    worktree_path: Mapped[str] = mapped_column(Text, nullable=False)
    branch_name: Mapped[str] = mapped_column(String(300), nullable=False)
    base_branch: Mapped[str | None] = mapped_column(String(300))
    base_commit_sha: Mapped[str | None] = mapped_column(String(64))
    result_commit_sha: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[GitWorktreeStatus] = mapped_column(
        enum_column(GitWorktreeStatus), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleanup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class ArtifactRef(TimestampMixin, Base):
    __tablename__ = "artifact_refs"
    __table_args__ = (
        Index("ix_artifact_refs_attempt_id", "task_attempt_id"),
        Index("ix_artifact_refs_local_user_id", "local_user_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_type: Mapped[str] = mapped_column(String(100), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    local_user_id: Mapped[str | None] = mapped_column(ForeignKey("local_users.id"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("project_repositories.id"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    task_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("task_attempts.id"))
    worker_id: Mapped[str | None] = mapped_column(ForeignKey("workers.id"))
    tool_call_id: Mapped[str | None] = mapped_column(ForeignKey("tool_calls.id"))
    kind: Mapped[ArtifactKind] = mapped_column(enum_column(ArtifactKind), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    retention_policy: Mapped[str | None] = mapped_column(String(100))


class MergeReview(TimestampMixin, Base):
    __tablename__ = "merge_reviews"
    __table_args__ = (
        Index("ix_merge_reviews_local_user_id", "local_user_id"),
        Index("ix_merge_reviews_attempt_id", "task_attempt_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    repository_id: Mapped[str] = mapped_column(
        ForeignKey("project_repositories.id"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    task_attempt_id: Mapped[str] = mapped_column(ForeignKey("task_attempts.id"), nullable=False)
    git_worktree_id: Mapped[str] = mapped_column(ForeignKey("git_worktrees.id"), nullable=False)
    status: Mapped[MergeReviewStatus] = mapped_column(
        enum_column(MergeReviewStatus), nullable=False
    )
    review_summary: Mapped[str | None] = mapped_column(Text)
    base_branch: Mapped[str] = mapped_column(String(300), nullable=False)
    base_commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    result_branch: Mapped[str] = mapped_column(String(300), nullable=False)
    result_commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    merge_commit_sha: Mapped[str | None] = mapped_column(String(64))
    diff_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_refs.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class ApprovalRequest(TimestampMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_local_user_id", "local_user_id"),
        Index("ix_approval_requests_task_attempt_id", "task_attempt_id"),
        Index("ix_approval_requests_fingerprint", "approval_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("project_repositories.id"))
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"))
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"))
    tool_call_id: Mapped[str | None] = mapped_column(ForeignKey("tool_calls.id"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    task_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("task_attempts.id"))
    git_worktree_id: Mapped[str | None] = mapped_column(ForeignKey("git_worktrees.id"))
    merge_review_id: Mapped[str | None] = mapped_column(ForeignKey("merge_reviews.id"))
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        enum_column(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scope_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    arguments_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    approval_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by_session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"))
    decided_by_session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)


class PolicyDecision(TimestampMixin, Base):
    __tablename__ = "policy_decisions"
    __table_args__ = (
        Index("ix_policy_decisions_local_user_id", "local_user_id"),
        Index("ix_policy_decisions_task_attempt_id", "task_attempt_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str | None] = mapped_column(ForeignKey("local_users.id"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("project_repositories.id"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    task_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("task_attempts.id"))
    tool_call_id: Mapped[str | None] = mapped_column(ForeignKey("tool_calls.id"))
    approval_request_id: Mapped[str | None] = mapped_column(ForeignKey("approval_requests.id"))
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[PolicyDecisionResult] = mapped_column(
        enum_column(PolicyDecisionResult), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict[str, object] | None] = mapped_column(JSON)


class Grant(TimestampMixin, Base):
    __tablename__ = "grants"
    __table_args__ = (
        Index("ix_grants_local_user_id", "local_user_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    approval_mode: Mapped[ApprovalMode] = mapped_column(
        enum_column(ApprovalMode), nullable=False, default=ApprovalMode.ASK_FOR_APPROVAL
    )
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("project_repositories.id"))
    project_working_scope_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    risk_ceiling: Mapped[RiskLevel] = mapped_column(
        enum_column(RiskLevel), nullable=False, default=RiskLevel.R1
    )
    allow_scope_expansion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_new_files: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_protected_paths: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_high_risk_changes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_danger_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessRun(TimestampMixin, Base):
    __tablename__ = "process_runs"
    __table_args__ = (
        Index("ix_process_runs_local_user_id", "local_user_id"),
        Index("ix_process_runs_task_attempt_id", "task_attempt_id"),
        Index("ix_process_runs_worker_run_id", "worker_run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str | None] = mapped_column(ForeignKey("local_users.id"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("project_repositories.id"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    task_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("task_attempts.id"), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(ForeignKey("workers.id"), nullable=True)
    worker_run_id: Mapped[str | None] = mapped_column(ForeignKey("worker_runs.id"), nullable=True)
    tool_call_id: Mapped[str | None] = mapped_column(ForeignKey("tool_calls.id"), nullable=True)
    
    command_display: Mapped[str] = mapped_column(Text, nullable=False)
    executable: Mapped[str] = mapped_column(Text, nullable=False)
    arguments_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    working_directory: Mapped[str] = mapped_column(Text, nullable=False)
    
    status: Mapped[ProcessRunStatus] = mapped_column(
        enum_column(ProcessRunStatus), nullable=False, default=ProcessRunStatus.CREATED
    )
    
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timed_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    stdout_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_refs.id"), nullable=True)
    stderr_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_refs.id"), nullable=True)
    combined_log_artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_refs.id"), nullable=True)
    
    provider_kind: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_after: Mapped[str | None] = mapped_column(String(200), nullable=True)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
