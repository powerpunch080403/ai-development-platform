from datetime import datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from aidp_server.audit import record_audit_event
from aidp_server.auth import CurrentAuth
from aidp_server.db.base import Base
from aidp_server.db.models import (
    Project,
    Task,
    TaskAttempt,
    TimestampMixin,
    enum_column,
    new_uuid,
    utc_now,
)
from aidp_server.db.session import get_session


class WorkRoomMessageSender(StrEnum):
    OWNER = "owner"
    WORKER = "worker"
    SYSTEM = "system"


class WorkRoomMessageType(StrEnum):
    OWNER_INSTRUCTION = "owner_instruction"
    OWNER_FEEDBACK = "owner_feedback"
    WORKER_REPORT = "worker_report"
    WORKER_QUESTION = "worker_question"
    SYSTEM_EVENT = "system_event"


class TaskWorkRoomMessage(TimestampMixin, Base):
    __tablename__ = "task_work_room_messages"
    __table_args__ = (
        Index("ix_task_work_room_messages_task_id", "task_id"),
        Index("ix_task_work_room_messages_attempt_id", "task_attempt_id"),
        Index("ix_task_work_room_messages_local_user_id", "local_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    local_user_id: Mapped[str] = mapped_column(ForeignKey("local_users.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("project_repositories.id"))
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    task_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("task_attempts.id"))
    worker_id: Mapped[str | None] = mapped_column(ForeignKey("workers.id"))
    worker_run_id: Mapped[str | None] = mapped_column(ForeignKey("worker_runs.id"))
    process_run_id: Mapped[str | None] = mapped_column(ForeignKey("process_runs.id"))
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifact_refs.id"))
    sender: Mapped[WorkRoomMessageSender] = mapped_column(
        enum_column(WorkRoomMessageSender), nullable=False
    )
    message_type: Mapped[WorkRoomMessageType] = mapped_column(
        enum_column(WorkRoomMessageType), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="text/markdown")
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class CreateWorkRoomMessageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_attempt_id: str | None = None
    worker_id: str | None = None
    worker_run_id: str | None = None
    process_run_id: str | None = None
    artifact_id: str | None = None
    sender: WorkRoomMessageSender = WorkRoomMessageSender.OWNER
    message_type: WorkRoomMessageType
    content: str = Field(min_length=1, max_length=100_000)
    content_type: str = Field(default="text/markdown", max_length=100)
    metadata: dict[str, object] | None = None


class WorkRoomMessageView(BaseModel):
    id: str
    local_user_id: str
    project_id: str
    repository_id: str | None
    task_id: str
    task_attempt_id: str | None
    worker_id: str | None
    worker_run_id: str | None
    process_run_id: str | None
    artifact_id: str | None
    sender: str
    message_type: str
    content: str
    content_type: str
    metadata: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


router = APIRouter(tags=["task work room"])


def _owned(session: Session, model: type, object_id: str, user_id: str):
    value = session.get(model, object_id)
    if value is None or getattr(value, "local_user_id", None) != user_id:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return value


def work_room_message_view(message: TaskWorkRoomMessage) -> WorkRoomMessageView:
    return WorkRoomMessageView(
        id=message.id,
        local_user_id=message.local_user_id,
        project_id=message.project_id,
        repository_id=message.repository_id,
        task_id=message.task_id,
        task_attempt_id=message.task_attempt_id,
        worker_id=message.worker_id,
        worker_run_id=message.worker_run_id,
        process_run_id=message.process_run_id,
        artifact_id=message.artifact_id,
        sender=message.sender.value,
        message_type=message.message_type.value,
        content=message.content,
        content_type=message.content_type,
        metadata=message.metadata_json,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def _ensure_optional_attempt_belongs_to_task(
    session: Session, *, task: Task, attempt_id: str | None, user_id: str
) -> None:
    if attempt_id is None:
        return
    attempt = _owned(session, TaskAttempt, attempt_id, user_id)
    if attempt.task_id != task.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task_attempt_id belongs to another task",
        )


@router.get("/tasks/{task_id}/work-room/messages", response_model=list[WorkRoomMessageView])
def list_work_room_messages(
    task_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> list[WorkRoomMessageView]:
    task = _owned(session, Task, task_id, current.user.id)
    messages = session.scalars(
        select(TaskWorkRoomMessage)
        .where(TaskWorkRoomMessage.task_id == task.id)
        .order_by(TaskWorkRoomMessage.created_at.asc(), TaskWorkRoomMessage.id.asc())
    ).all()
    return [work_room_message_view(message) for message in messages]


@router.post(
    "/tasks/{task_id}/work-room/messages",
    response_model=WorkRoomMessageView,
    status_code=status.HTTP_201_CREATED,
)
def create_work_room_message(
    task_id: str,
    request: CreateWorkRoomMessageRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> WorkRoomMessageView:
    task = _owned(session, Task, task_id, current.user.id)
    _owned(session, Project, task.project_id, current.user.id)
    _ensure_optional_attempt_belongs_to_task(
        session, task=task, attempt_id=request.task_attempt_id, user_id=current.user.id
    )

    message = TaskWorkRoomMessage(
        local_user_id=current.user.id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        task_id=task.id,
        task_attempt_id=request.task_attempt_id,
        worker_id=request.worker_id,
        worker_run_id=request.worker_run_id,
        process_run_id=request.process_run_id,
        artifact_id=request.artifact_id,
        sender=request.sender,
        message_type=request.message_type,
        content=request.content,
        content_type=request.content_type,
        metadata_json=request.metadata,
    )
    session.add(message)
    session.flush()
    record_audit_event(
        session,
        event_type="task_work_room.message_created",
        message="Task work room message created",
        local_user_id=current.user.id,
        device_id=current.device.id,
        session_id=current.runtime_session.id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        metadata={
            "task_id": task.id,
            "task_attempt_id": request.task_attempt_id,
            "message_id": message.id,
            "message_type": request.message_type.value,
            "sender": request.sender.value,
        },
    )
    session.commit()
    session.refresh(message)
    return work_room_message_view(message)
