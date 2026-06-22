"""Add conversation, agent run, tool call, and audit tables.

Revision ID: 20260622_0003
Revises: 20260622_0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260622_0003"
down_revision: str | None = "20260622_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        )
    ]


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column(
            "status",
            enum("conversation_status", "active", "archived"),
            server_default="active",
            nullable=False,
        ),
        *timestamps(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_conversations_local_user_id", "conversations", ["local_user_id"])
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=True
        ),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=False),
        sa.Column(
            "requested_by_session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=True
        ),
        sa.Column(
            "status",
            enum(
                "agent_run_status",
                "queued",
                "preparing_context",
                "running_model",
                "executing_tool",
                "waiting_for_approval",
                "waiting_for_user",
                "waiting_for_worker",
                "reviewing_worker_result",
                "retry_scheduled",
                "completed",
                "failed",
                "cancelled",
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("purpose", sa.String(200), nullable=False),
        sa.Column(
            "input_message_id",
            sa.String(36),
            sa.ForeignKey("messages.id", name="fk_agent_runs_input_message", use_alter=True),
            nullable=True,
        ),
        *timestamps(),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])
    op.create_index("ix_agent_runs_local_user_id", "agent_runs", ["local_user_id"])
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False
        ),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=False),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column(
            "role",
            enum("message_role", "user", "assistant", "system", "tool", "worker"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "content_type",
            enum("content_type", "text", "json", "markdown", "error"),
            server_default="text",
            nullable=False,
        ),
        *timestamps(),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_local_user_id", "messages", ["local_user_id"])

    op.create_table(
        "agent_run_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column(
            "step_type",
            enum("agent_run_step_type", "model", "tool_call", "message", "system", "review"),
            nullable=False,
        ),
        sa.Column(
            "status",
            enum(
                "record_status", "created", "running", "succeeded", "failed", "cancelled", "skipped"
            ),
            server_default="created",
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        *timestamps(),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("agent_run_id", "step_index", name="uq_agent_run_step_index"),
    )
    op.create_index("ix_agent_run_steps_agent_run_id", "agent_run_steps", ["agent_run_id"])

    op.create_table(
        "tool_registry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("tool_version", sa.String(50), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema_ref", sa.String(500), nullable=True),
        sa.Column("output_schema_ref", sa.String(500), nullable=True),
        sa.Column("has_side_effect", sa.Boolean(), nullable=False),
        sa.Column("default_risk_level", sa.String(20), nullable=False),
        sa.Column("required_grants", sa.JSON(), nullable=True),
        sa.Column("scope_evaluator", sa.String(200), nullable=True),
        sa.Column("idempotency_required", sa.Boolean(), nullable=False),
        sa.Column("approval_behavior", sa.String(100), nullable=False),
        sa.Column("audit_required", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tool_name", "tool_version", name="uq_tool_registry_name_version"),
    )

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("tool_version", sa.String(50), nullable=False),
        sa.Column("tool_category", sa.String(100), nullable=False),
        sa.Column(
            "caller_type",
            enum("tool_caller_type", "owner", "ui", "worker", "system", "central_authority"),
            nullable=False,
        ),
        sa.Column("caller_id", sa.String(200), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=True),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=True
        ),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column(
            "agent_run_step_id", sa.String(36), sa.ForeignKey("agent_run_steps.id"), nullable=True
        ),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column(
            "repository_id", sa.String(36), sa.ForeignKey("project_repositories.id"), nullable=True
        ),
        sa.Column("work_item_id", sa.String(36), nullable=True),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("task_attempt_id", sa.String(36), nullable=True),
        sa.Column("worker_run_id", sa.String(36), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("correlation_id", sa.String(200), nullable=True),
        sa.Column("arguments_json", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            enum(
                "tool_call_status",
                "created",
                "policy_checking",
                "waiting_for_approval",
                "running",
                "succeeded",
                "failed",
                "cancelled",
                "skipped_duplicate",
            ),
            server_default="created",
            nullable=False,
        ),
        sa.Column("result_ref", sa.String(500), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tool_calls_user_id", "tool_calls", ["user_id"])
    op.create_index("ix_tool_calls_agent_run_id", "tool_calls", ["agent_run_id"])
    op.create_index("ix_tool_calls_idempotency", "tool_calls", ["tool_name", "idempotency_key"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("local_user_id", sa.String(36), sa.ForeignKey("local_users.id"), nullable=True),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column(
            "repository_id", sa.String(36), sa.ForeignKey("project_repositories.id"), nullable=True
        ),
        sa.Column(
            "conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=True
        ),
        sa.Column("agent_run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=True),
        sa.Column("tool_call_id", sa.String(36), sa.ForeignKey("tool_calls.id"), nullable=True),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column(
            "severity",
            enum("audit_severity", "debug", "info", "warning", "error", "critical"),
            server_default="info",
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_audit_events_local_user_id", "audit_events", ["local_user_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("tool_calls")
    op.drop_table("tool_registry")
    op.drop_table("agent_run_steps")
    op.drop_table("messages")
    op.drop_table("agent_runs")
    op.drop_table("conversations")
