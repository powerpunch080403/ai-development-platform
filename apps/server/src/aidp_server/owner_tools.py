from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.audit import record_audit_event
from aidp_server.db.models import (
    AgentRun,
    Project,
    Task,
    TaskStatus,
    RiskLevel,
    ToolCall,
    ToolCallerType,
    ToolCallStatus,
    ToolRegistryEntry,
)
from aidp_server.tool_registry import seed_tool_registry


def apply_authority_envelope(session: Session, tool_call: ToolCall, mode: str = "personal") -> bool:
    """
    Applies the authority envelope to the tool call.
    In Personal Mode, it does not replace Owner's judgment.
    For this slice, read-only tools and minimal side-effect tools are allowed.
    """
    # Personal Mode behavior
    record_audit_event(
        session,
        event_type="owner_tool_call.authority_applied",
        message=f"Authority envelope applied for {tool_call.tool_name}",
        local_user_id=tool_call.user_id,
        tool_call_id=tool_call.id,
        agent_run_id=tool_call.agent_run_id,
        metadata={
            "mode": mode,
            "authority_applied": True,
            "owner_judgment_replaced": False,
            "side_effect": False if tool_call.tool_name in ["project.list", "task.list"] else True,
        },
    )

    # Team Mode: TODO: central policy will restrict visible context/files before Owner reasoning.

    # Allow specific tools for this slice
    if tool_call.tool_name in ["project.list", "task.list", "task.create"]:
        return True

    # Reject everything else for now
    tool_call.status = ToolCallStatus.REJECTED
    tool_call.error_code = "NOT_IMPLEMENTED_IN_SLICE"
    tool_call.error_message = "Only specific tools are allowed in this MVP slice"
    tool_call.completed_at = datetime.now(timezone.utc)
    session.add(tool_call)

    record_audit_event(
        session,
        event_type="owner_tool_call.rejected",
        message=f"Tool call {tool_call.tool_name} rejected by authority envelope",
        local_user_id=tool_call.user_id,
        tool_call_id=tool_call.id,
        agent_run_id=tool_call.agent_run_id,
    )
    return False


def execute_owner_tool(session: Session, tool_call: ToolCall) -> dict[str, Any]:
    if tool_call.tool_name == "project.list":
        projects = session.scalars(
            select(Project)
            .where(Project.local_user_id == tool_call.user_id)
            .order_by(Project.created_at.desc())
        ).all()
        return {"projects": [{"id": p.id, "name": p.name} for p in projects]}

    elif tool_call.tool_name == "task.list":
        query = select(Task).where(Task.local_user_id == tool_call.user_id)
        if tool_call.project_id:
            query = query.where(Task.project_id == tool_call.project_id)
        tasks = session.scalars(query.order_by(Task.created_at.desc())).all()
        return {"tasks": [{"id": t.id, "title": t.title, "status": t.status.value} for t in tasks]}

    elif tool_call.tool_name == "task.create":
        args = tool_call.arguments_json or {}
        task = Task(
            local_user_id=tool_call.user_id,
            project_id=tool_call.project_id,
            agent_run_id=tool_call.agent_run_id,
            title=args.get("title", "Untitled Task"),
            instructions=args.get("instructions", ""),
            status=TaskStatus.DRAFT,
            risk_level=RiskLevel.R1,
        )
        session.add(task)
        session.flush()
        record_audit_event(
            session,
            event_type="task.created",
            message="Task created via owner tool",
            local_user_id=tool_call.user_id,
            project_id=tool_call.project_id,
            agent_run_id=tool_call.agent_run_id,
            metadata={"task_id": task.id, "source": "owner_tool"},
        )
        return {"task_id": task.id}

    raise ValueError(f"Unsupported tool: {tool_call.tool_name}")


def request_owner_tool_call(
    session: Session,
    agent_run_id: str,
    provider_kind: str,
    tool_name: str,
    arguments_json: dict[str, Any],
    provider_call_id: str | None = None,
) -> ToolCall:
    """
    Entrypoint for Owner Runtime Providers to request a tool call.
    """
    run = session.get(AgentRun, agent_run_id)
    if not run:
        raise ValueError("AgentRun not found")

    seed_tool_registry(session)

    definition = session.scalar(
        select(ToolRegistryEntry).where(
            ToolRegistryEntry.tool_name == tool_name,
            ToolRegistryEntry.enabled.is_(True),
            ToolRegistryEntry.deprecated_at.is_(None),
        )
    )

    now = datetime.now(timezone.utc)

    if not definition:
        # Unknown tool
        call = ToolCall(
            tool_name=tool_name,
            tool_version="1.0",
            tool_category="unknown",
            caller_type=ToolCallerType.OWNER,
            caller_id=provider_kind,
            user_id=run.local_user_id,
            agent_run_id=run.id,
            project_id=run.project_id,
            risk_level="R0",
            correlation_id=provider_call_id,
            arguments_json=arguments_json,
            status=ToolCallStatus.REJECTED,
            error_code="UNKNOWN_TOOL",
            error_message="The requested tool is unknown or disabled",
            completed_at=now,
        )
        session.add(call)
        session.flush()
        record_audit_event(
            session,
            event_type="owner_tool_call.rejected",
            message=f"Unknown tool call {tool_name} requested and rejected",
            local_user_id=run.local_user_id,
            tool_call_id=call.id,
            agent_run_id=run.id,
        )
        return call

    # 1. requested -> recorded
    call = ToolCall(
        tool_name=definition.tool_name,
        tool_version=definition.tool_version,
        tool_category=definition.category,
        caller_type=ToolCallerType.OWNER,
        caller_id=provider_kind,
        user_id=run.local_user_id,
        agent_run_id=run.id,
        project_id=run.project_id,
        risk_level=definition.default_risk_level,
        correlation_id=provider_call_id,
        arguments_json=arguments_json,
        status=ToolCallStatus.CREATED,
    )
    session.add(call)
    session.flush()

    record_audit_event(
        session,
        event_type="owner_tool_call.recorded",
        message=f"Tool call requested by owner provider {provider_kind}",
        local_user_id=run.local_user_id,
        tool_call_id=call.id,
        agent_run_id=run.id,
        metadata={"source": "owner_runtime_provider", "provider_call_id": provider_call_id},
    )

    # 2. authority_applied
    allowed = apply_authority_envelope(session, call)
    if not allowed:
        return call

    # 3. executing
    call.status = ToolCallStatus.RUNNING
    call.started_at = datetime.now(timezone.utc)
    session.add(call)
    session.flush()

    # 4. completed / failed
    try:
        result = execute_owner_tool(session, call)
        call.status = ToolCallStatus.SUCCEEDED
        call.completed_at = datetime.now(timezone.utc)
        call.result_json = result

        record_audit_event(
            session,
            event_type="owner_tool_call.completed",
            message=f"Tool call {tool_name} completed successfully",
            local_user_id=run.local_user_id,
            tool_call_id=call.id,
            agent_run_id=run.id,
        )
    except Exception as e:
        call.status = ToolCallStatus.FAILED
        call.error_message = str(e)
        call.completed_at = datetime.now(timezone.utc)
        record_audit_event(
            session,
            event_type="owner_tool_call.failed",
            message=f"Tool call {tool_name} failed",
            local_user_id=run.local_user_id,
            tool_call_id=call.id,
            agent_run_id=run.id,
        )

    return call
