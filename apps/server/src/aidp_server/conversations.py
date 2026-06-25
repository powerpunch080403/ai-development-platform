from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidp_server.audit import record_audit_event
from aidp_server.auth import CurrentAuth
from aidp_server.db.models import (
    AgentRun,
    AgentRunStatus,
    AgentRunStep,
    AgentRunStepType,
    ContentType,
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
    Project,
    RecordStatus,
    utc_now,
)
from aidp_server.db.session import get_session
from aidp_server.config import Settings, get_settings


class CreateConversationRequest(BaseModel):
    project_id: str | None = None
    title: str = Field(default="New Conversation", min_length=1, max_length=300)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Conversation title cannot be blank")
        return value


class AppendMessageRequest(BaseModel):
    role: MessageRole
    content: str = Field(min_length=1, max_length=100_000)
    content_type: ContentType = ContentType.TEXT


class CreateAgentRunRequest(BaseModel):
    conversation_id: str | None = None
    project_id: str | None = None
    purpose: str = Field(min_length=1, max_length=200)
    input_message_id: str | None = None


class StartAgentRunRequest(BaseModel):
    provider_kind: str | None = Field(default="codex_cli")


class UpdateAgentRunStatusRequest(BaseModel):
    status: AgentRunStatus
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = Field(default=None, max_length=4000)


class CreateAgentRunStepRequest(BaseModel):
    step_type: AgentRunStepType
    status: RecordStatus = RecordStatus.CREATED
    summary: str | None = Field(default=None, max_length=4000)


class ConversationView(BaseModel):
    id: str
    project_id: str | None
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class MessageView(BaseModel):
    id: str
    conversation_id: str
    agent_run_id: str | None
    role: str
    content: str
    content_type: str
    created_at: datetime


class AgentRunView(BaseModel):
    id: str
    conversation_id: str | None
    project_id: str | None
    status: str
    purpose: str
    input_message_id: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None
    error_code: str | None
    error_message: str | None


class AgentRunStepView(BaseModel):
    id: str
    agent_run_id: str
    step_index: int
    step_type: str
    status: str
    summary: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


router = APIRouter(tags=["conversations and agent runs"])


def owned(session: Session, model: type, object_id: str, user_id: str) -> Any:
    value = session.get(model, object_id)
    if value is None or value.local_user_id != user_id:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return value


def conversation_view(value: Conversation) -> ConversationView:
    return ConversationView(
        id=value.id,
        project_id=value.project_id,
        title=value.title,
        status=value.status.value,
        created_at=value.created_at,
        updated_at=value.updated_at,
        archived_at=value.archived_at,
    )


def message_view(value: Message) -> MessageView:
    return MessageView(
        id=value.id,
        conversation_id=value.conversation_id,
        agent_run_id=value.agent_run_id,
        role=value.role.value,
        content=value.content,
        content_type=value.content_type.value,
        created_at=value.created_at,
    )


def run_view(value: AgentRun) -> AgentRunView:
    return AgentRunView(
        id=value.id,
        conversation_id=value.conversation_id,
        project_id=value.project_id,
        status=value.status.value,
        purpose=value.purpose,
        input_message_id=value.input_message_id,
        created_at=value.created_at,
        started_at=value.started_at,
        completed_at=value.completed_at,
        failed_at=value.failed_at,
        cancelled_at=value.cancelled_at,
        error_code=value.error_code,
        error_message=value.error_message,
    )


@router.post("/conversations", response_model=ConversationView, status_code=201)
def create_conversation(
    request: CreateConversationRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ConversationView:
    if request.project_id:
        owned(session, Project, request.project_id, current.user.id)
    conversation = Conversation(
        local_user_id=current.user.id,
        project_id=request.project_id,
        title=request.title.strip() or "New Conversation",
        status=ConversationStatus.ACTIVE,
    )
    session.add(conversation)
    session.flush()
    record_audit_event(
        session,
        event_type="conversation.created",
        message="Conversation created",
        local_user_id=current.user.id,
        device_id=current.device.id,
        session_id=current.runtime_session.id,
        project_id=request.project_id,
        conversation_id=conversation.id,
    )
    session.commit()
    return conversation_view(conversation)


@router.get("/conversations", response_model=list[ConversationView])
def list_conversations(
    current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[ConversationView]:
    values = session.scalars(
        select(Conversation)
        .where(
            Conversation.local_user_id == current.user.id,
            Conversation.status == ConversationStatus.ACTIVE,
        )
        .order_by(Conversation.updated_at.desc())
    )
    return [conversation_view(value) for value in values]


@router.get("/conversations/{conversation_id}", response_model=ConversationView)
def get_conversation(
    conversation_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> ConversationView:
    return conversation_view(owned(session, Conversation, conversation_id, current.user.id))


@router.patch("/conversations/{conversation_id}", response_model=ConversationView)
def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ConversationView:
    conversation = owned(session, Conversation, conversation_id, current.user.id)
    if request.title is not None:
        conversation.title = request.title.strip()
    conversation.updated_at = utc_now()
    record_audit_event(
        session,
        event_type="conversation.updated",
        message="Conversation updated",
        local_user_id=current.user.id,
        device_id=current.device.id,
        session_id=current.runtime_session.id,
        project_id=conversation.project_id,
        conversation_id=conversation.id,
    )
    session.commit()
    return conversation_view(conversation)


@router.delete("/conversations/{conversation_id}", response_model=ConversationView)
def archive_conversation(
    conversation_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ConversationView:
    conversation = owned(session, Conversation, conversation_id, current.user.id)
    now = utc_now()
    conversation.status = ConversationStatus.ARCHIVED
    conversation.archived_at = now
    conversation.updated_at = now
    record_audit_event(
        session,
        event_type="conversation.archived",
        message="Conversation archived",
        local_user_id=current.user.id,
        device_id=current.device.id,
        session_id=current.runtime_session.id,
        project_id=conversation.project_id,
        conversation_id=conversation.id,
    )
    session.commit()
    return conversation_view(conversation)


@router.post(
    "/conversations/{conversation_id}/messages", response_model=MessageView, status_code=201
)
def append_message(
    conversation_id: str,
    request: AppendMessageRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> MessageView:
    conversation = owned(session, Conversation, conversation_id, current.user.id)
    if request.role not in {MessageRole.USER, MessageRole.SYSTEM, MessageRole.ASSISTANT}:
        raise HTTPException(status_code=400, detail="Role is reserved for internal records")
    message = Message(
        conversation_id=conversation.id,
        local_user_id=current.user.id,
        role=request.role,
        content=request.content,
        content_type=request.content_type,
    )
    session.add(message)
    conversation.updated_at = utc_now()
    session.flush()
    record_audit_event(
        session,
        event_type="message.appended",
        message="Conversation message appended",
        local_user_id=current.user.id,
        device_id=current.device.id,
        session_id=current.runtime_session.id,
        project_id=conversation.project_id,
        conversation_id=conversation.id,
        metadata={"role": request.role.value},
    )
    session.commit()
    return message_view(message)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageView])
def list_messages(
    conversation_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[MessageView]:
    owned(session, Conversation, conversation_id, current.user.id)
    values = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return [message_view(value) for value in values]


@router.post("/agent-runs", response_model=AgentRunView, status_code=201)
def create_agent_run(
    request: CreateAgentRunRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> AgentRunView:
    conversation = (
        owned(session, Conversation, request.conversation_id, current.user.id)
        if request.conversation_id
        else None
    )
    project_id = request.project_id or (conversation.project_id if conversation else None)
    if project_id:
        owned(session, Project, project_id, current.user.id)
    if conversation and request.project_id and conversation.project_id != request.project_id:
        raise HTTPException(status_code=400, detail="Conversation and project do not match")
    if request.input_message_id:
        message = owned(session, Message, request.input_message_id, current.user.id)
        if conversation and message.conversation_id != conversation.id:
            raise HTTPException(
                status_code=400, detail="Input message does not belong to conversation"
            )
    run = AgentRun(
        conversation_id=request.conversation_id,
        project_id=project_id,
        local_user_id=current.user.id,
        requested_by_session_id=current.runtime_session.id,
        status=AgentRunStatus.QUEUED,
        purpose=request.purpose,
        input_message_id=request.input_message_id,
    )
    session.add(run)
    session.flush()
    record_audit_event(
        session,
        event_type="agent_run.created",
        message="Agent run record created",
        local_user_id=current.user.id,
        device_id=current.device.id,
        session_id=current.runtime_session.id,
        project_id=project_id,
        conversation_id=request.conversation_id,
        agent_run_id=run.id,
    )
    session.commit()
    return run_view(run)


@router.get("/agent-runs/{run_id}", response_model=AgentRunView)
def get_agent_run(
    run_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> AgentRunView:
    return run_view(owned(session, AgentRun, run_id, current.user.id))


@router.get("/conversations/{conversation_id}/agent-runs", response_model=list[AgentRunView])
def list_agent_runs(
    conversation_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[AgentRunView]:
    owned(session, Conversation, conversation_id, current.user.id)
    return [
        run_view(value)
        for value in session.scalars(
            select(AgentRun)
            .where(AgentRun.conversation_id == conversation_id)
            .order_by(AgentRun.created_at.desc())
        )
    ]


@router.post("/agent-runs/{run_id}/status", response_model=AgentRunView)
def update_agent_run_status(
    run_id: str,
    request: UpdateAgentRunStatusRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> AgentRunView:
    run = owned(session, AgentRun, run_id, current.user.id)
    now = datetime.now(timezone.utc)
    run.status = request.status
    run.error_code = request.error_code
    run.error_message = request.error_message
    if (
        request.status not in {AgentRunStatus.QUEUED, AgentRunStatus.CANCELLED}
        and run.started_at is None
    ):
        run.started_at = now
    if request.status is AgentRunStatus.COMPLETED:
        run.completed_at = now
    elif request.status is AgentRunStatus.FAILED:
        run.failed_at = now
    elif request.status is AgentRunStatus.CANCELLED:
        run.cancelled_at = now
    record_audit_event(
        session,
        event_type="agent_run.status_changed",
        message=f"Agent run status changed to {request.status.value}",
        local_user_id=current.user.id,
        agent_run_id=run.id,
        conversation_id=run.conversation_id,
        project_id=run.project_id,
    )
    session.commit()
    return run_view(run)


@router.post("/agent-runs/{run_id}/start", response_model=AgentRunView)
def start_agent_run(
    run_id: str,
    request: StartAgentRunRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgentRunView:
    run = owned(session, AgentRun, run_id, current.user.id)
    if run.status not in {AgentRunStatus.QUEUED, AgentRunStatus.CANCELLED}:
        raise HTTPException(status_code=400, detail="AgentRun is not in a startable state")

    provider_kind = request.provider_kind or "codex_cli"

    if provider_kind == "fake":
        if not settings.allow_fake_owner_provider:
            raise HTTPException(status_code=403, detail="Fake owner provider is not allowed")
    elif provider_kind != "codex_cli":
        raise HTTPException(status_code=400, detail=f"Unknown owner provider kind: {provider_kind}")

    from aidp_server.owner_providers import get_owner_provider
    try:
        provider = get_owner_provider(provider_kind, settings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    provider.start_agent_run(session, run)
    session.commit()

    return run_view(run)


@router.post("/agent-runs/{run_id}/steps", response_model=AgentRunStepView, status_code=201)
def create_agent_run_step(
    run_id: str,
    request: CreateAgentRunStepRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> AgentRunStepView:
    run = owned(session, AgentRun, run_id, current.user.id)
    next_index = (
        session.scalar(
            select(func.max(AgentRunStep.step_index)).where(AgentRunStep.agent_run_id == run.id)
        )
        or -1
    ) + 1
    now = datetime.now(timezone.utc)
    step = AgentRunStep(
        agent_run_id=run.id,
        step_index=next_index,
        step_type=request.step_type,
        status=request.status,
        summary=request.summary,
        started_at=now if request.status is not RecordStatus.CREATED else None,
        completed_at=now if request.status is RecordStatus.COMPLETED else None,
    )
    session.add(step)
    session.flush()
    record_audit_event(
        session,
        event_type="agent_run.step_created",
        message="Agent run step recorded",
        local_user_id=current.user.id,
        agent_run_id=run.id,
        conversation_id=run.conversation_id,
        project_id=run.project_id,
        metadata={"step_index": next_index, "step_type": request.step_type.value},
    )
    session.commit()
    return AgentRunStepView(
        id=step.id,
        agent_run_id=step.agent_run_id,
        step_index=step.step_index,
        step_type=step.step_type.value,
        status=step.status.value,
        summary=step.summary,
        created_at=step.created_at,
        started_at=step.started_at,
        completed_at=step.completed_at,
    )
