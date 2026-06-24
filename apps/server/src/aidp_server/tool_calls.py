from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.audit import record_audit_event
from aidp_server.auth import CurrentAuth
from aidp_server.db.models import (
    AuditEvent,
    AgentRun,
    AgentRunStep,
    Conversation,
    Project,
    ProjectRepository,
    ToolCall,
    ToolCallerType,
    ToolCallStatus,
    ToolRegistryEntry,
)
from aidp_server.db.session import get_session
from aidp_server.tool_registry import seed_tool_registry


class CreateToolCallRequest(BaseModel):
    tool_name: str
    tool_version: str = "1.0"
    caller_type: ToolCallerType = ToolCallerType.UI
    caller_id: str | None = None
    conversation_id: str | None = None
    agent_run_id: str | None = None
    agent_run_step_id: str | None = None
    project_id: str | None = None
    repository_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)
    correlation_id: str | None = Field(default=None, max_length=200)
    arguments_json: dict[str, Any] = Field(default_factory=dict)


class UpdateToolCallStatusRequest(BaseModel):
    status: ToolCallStatus
    result_ref: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ToolRegistryView(BaseModel):
    id: str
    tool_name: str
    tool_version: str
    category: str
    description: str
    has_side_effect: bool
    default_risk_level: str
    idempotency_required: bool
    approval_behavior: str
    audit_required: bool
    enabled: bool


class ToolCallView(BaseModel):
    id: str
    tool_name: str
    tool_version: str
    tool_category: str
    caller_type: str
    user_id: str | None
    conversation_id: str | None
    agent_run_id: str | None
    project_id: str | None
    repository_id: str | None
    risk_level: str
    idempotency_key: str | None
    correlation_id: str | None
    arguments_json: dict[str, Any]
    status: str
    result_ref: str | None
    result_json: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AuditEventView(BaseModel):
    id: str
    event_type: str
    severity: str
    message: str
    project_id: str | None
    conversation_id: str | None
    agent_run_id: str | None
    tool_call_id: str | None
    metadata_json: dict[str, Any] | None
    created_at: datetime


router = APIRouter(tags=["tool registry and audit"])


def call_view(value: ToolCall) -> ToolCallView:
    return ToolCallView(
        id=value.id,
        tool_name=value.tool_name,
        tool_version=value.tool_version,
        tool_category=value.tool_category,
        caller_type=value.caller_type.value,
        user_id=value.user_id,
        conversation_id=value.conversation_id,
        agent_run_id=value.agent_run_id,
        project_id=value.project_id,
        repository_id=value.repository_id,
        risk_level=value.risk_level,
        idempotency_key=value.idempotency_key,
        correlation_id=value.correlation_id,
        arguments_json=value.arguments_json,
        status=value.status.value,
        result_ref=value.result_ref,
        result_json=value.result_json,
        error_code=value.error_code,
        error_message=value.error_message,
        created_at=value.created_at,
        started_at=value.started_at,
        completed_at=value.completed_at,
    )


@router.get("/tool-registry", response_model=list[ToolRegistryView])
def get_tool_registry(
    current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[ToolRegistryView]:
    seed_tool_registry(session)
    values = session.scalars(select(ToolRegistryEntry).order_by(ToolRegistryEntry.tool_name))
    return [
        ToolRegistryView(
            id=v.id,
            tool_name=v.tool_name,
            tool_version=v.tool_version,
            category=v.category,
            description=v.description,
            has_side_effect=v.has_side_effect,
            default_risk_level=v.default_risk_level,
            idempotency_required=v.idempotency_required,
            approval_behavior=v.approval_behavior,
            audit_required=v.audit_required,
            enabled=v.enabled,
        )
        for v in values
    ]


@router.post("/tool-calls", response_model=ToolCallView, status_code=201)
def create_tool_call(
    request: CreateToolCallRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ToolCallView:
    seed_tool_registry(session)
    for model, object_id in (
        (Conversation, request.conversation_id),
        (AgentRun, request.agent_run_id),
        (Project, request.project_id),
        (ProjectRepository, request.repository_id),
    ):
        if object_id:
            linked = session.get(model, object_id)
            if linked is None or getattr(linked, "local_user_id", None) != current.user.id:
                raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    if request.agent_run_step_id:
        step = session.get(AgentRunStep, request.agent_run_step_id)
        run = session.get(AgentRun, step.agent_run_id) if step else None
        if run is None or run.local_user_id != current.user.id:
            raise HTTPException(status_code=404, detail="AgentRunStep not found")
    definition = session.scalar(
        select(ToolRegistryEntry).where(
            ToolRegistryEntry.tool_name == request.tool_name,
            ToolRegistryEntry.tool_version == request.tool_version,
            ToolRegistryEntry.enabled.is_(True),
            ToolRegistryEntry.deprecated_at.is_(None),
        )
    )
    if definition is None:
        raise HTTPException(status_code=400, detail="Tool is unknown, disabled, or deprecated")
    if definition.idempotency_required and not request.idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency key is required")
    if request.idempotency_key:
        duplicate = session.scalar(
            select(ToolCall).where(
                ToolCall.tool_name == request.tool_name,
                ToolCall.idempotency_key == request.idempotency_key,
                ToolCall.project_id == request.project_id,
                ToolCall.repository_id == request.repository_id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail="Duplicate tool call action scope")
    call = ToolCall(
        tool_name=definition.tool_name,
        tool_version=definition.tool_version,
        tool_category=definition.category,
        caller_type=request.caller_type,
        caller_id=request.caller_id,
        user_id=current.user.id,
        device_id=current.device.id,
        conversation_id=request.conversation_id,
        agent_run_id=request.agent_run_id,
        agent_run_step_id=request.agent_run_step_id,
        project_id=request.project_id,
        repository_id=request.repository_id,
        risk_level=definition.default_risk_level,
        idempotency_key=request.idempotency_key,
        correlation_id=request.correlation_id,
        arguments_json=request.arguments_json,
        status=ToolCallStatus.CREATED,
    )
    session.add(call)
    session.flush()
    record_audit_event(
        session,
        event_type="tool_call.created",
        message=f"Tool call envelope created for {call.tool_name}",
        local_user_id=current.user.id,
        device_id=current.device.id,
        session_id=current.runtime_session.id,
        project_id=call.project_id,
        repository_id=call.repository_id,
        conversation_id=call.conversation_id,
        agent_run_id=call.agent_run_id,
        tool_call_id=call.id,
    )
    session.commit()
    return call_view(call)


@router.get("/tool-calls/{call_id}", response_model=ToolCallView)
def get_tool_call(
    call_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> ToolCallView:
    call = session.get(ToolCall, call_id)
    if call is None or call.user_id != current.user.id:
        raise HTTPException(status_code=404, detail="Tool call not found")
    return call_view(call)


@router.post("/tool-calls/{call_id}/status", response_model=ToolCallView)
def update_tool_call_status(
    call_id: str,
    request: UpdateToolCallStatusRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ToolCallView:
    call = session.get(ToolCall, call_id)
    if call is None or call.user_id != current.user.id:
        raise HTTPException(status_code=404, detail="Tool call not found")
    now = datetime.now(timezone.utc)
    call.status = request.status
    call.result_ref = request.result_ref
    call.error_code = request.error_code
    call.error_message = request.error_message
    if request.status is ToolCallStatus.RUNNING and call.started_at is None:
        call.started_at = now
    if request.status in {
        ToolCallStatus.SUCCEEDED,
        ToolCallStatus.FAILED,
        ToolCallStatus.CANCELLED,
        ToolCallStatus.REJECTED,
        ToolCallStatus.SKIPPED_DUPLICATE,
    }:
        call.completed_at = now
    record_audit_event(
        session,
        event_type="tool_call.status_changed",
        message=f"Tool call status changed to {request.status.value}",
        local_user_id=current.user.id,
        tool_call_id=call.id,
        project_id=call.project_id,
        conversation_id=call.conversation_id,
        agent_run_id=call.agent_run_id,
    )
    session.commit()
    return call_view(call)


@router.get("/agent-runs/{run_id}/tool-calls", response_model=list[ToolCallView])
def list_tool_calls(
    run_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[ToolCallView]:
    values = session.scalars(
        select(ToolCall)
        .where(
            ToolCall.user_id == current.user.id,
            ToolCall.agent_run_id == run_id,
        )
        .order_by(ToolCall.created_at.asc())
    )
    return [call_view(v) for v in values]


class OwnerToolCallRequest(BaseModel):
    provider_kind: str
    tool_name: str
    arguments_json: dict[str, Any] = Field(default_factory=dict)
    provider_call_id: str | None = None


@router.post("/agent-runs/{run_id}/tool-calls", response_model=ToolCallView, status_code=201)
def request_owner_tool_call_endpoint(
    run_id: str,
    request: OwnerToolCallRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    background_tasks: BackgroundTasks,
) -> ToolCallView:
    from aidp_server.owner_tools import request_owner_tool_call

    run = session.get(AgentRun, run_id)
    if not run or run.local_user_id != current.user.id:
        raise HTTPException(status_code=404, detail="AgentRun not found")

    try:
        call = request_owner_tool_call(
            session=session,
            agent_run_id=run_id,
            provider_kind=request.provider_kind,
            tool_name=request.tool_name,
            arguments_json=request.arguments_json,
            provider_call_id=request.provider_call_id,
            background_tasks=background_tasks,
        )
        session.commit()
        return call_view(call)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/audit-events", response_model=list[AuditEventView])
def list_audit_events(
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    project_id: Annotated[str | None, Query()] = None,
    conversation_id: Annotated[str | None, Query()] = None,
    agent_run_id: Annotated[str | None, Query()] = None,
) -> list[AuditEventView]:
    query = select(AuditEvent).where(AuditEvent.local_user_id == current.user.id)
    if project_id:
        query = query.where(AuditEvent.project_id == project_id)
    if conversation_id:
        query = query.where(AuditEvent.conversation_id == conversation_id)
    if agent_run_id:
        query = query.where(AuditEvent.agent_run_id == agent_run_id)
    values = session.scalars(query.order_by(AuditEvent.created_at.desc()))
    return [
        AuditEventView(
            id=v.id,
            event_type=v.event_type,
            severity=v.severity.value,
            message=v.message,
            project_id=v.project_id,
            conversation_id=v.conversation_id,
            agent_run_id=v.agent_run_id,
            tool_call_id=v.tool_call_id,
            metadata_json=v.metadata_json,
            created_at=v.created_at,
        )
        for v in values
    ]
