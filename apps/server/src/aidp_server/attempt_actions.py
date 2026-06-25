from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidp_server.audit import record_audit_event
from aidp_server.auth import CurrentAuth
from aidp_server.attempt_retry_policy import (
    ExplicitRetryPolicyError,
    ensure_explicit_retry_allowed,
)
from aidp_server.db.models import Task, TaskAttempt, TaskAttemptStatus
from aidp_server.db.session import get_session
from aidp_server.state_transitions import StateTransitionError, assert_task_attempt_transition
from aidp_server.work import AttemptView, attempt_view
from aidp_server.work_room import (
    TaskWorkRoomMessage,
    WorkRoomMessageSender,
    WorkRoomMessageType,
    WorkRoomMessageView,
    work_room_message_view,
)

router = APIRouter(tags=["attempt review actions"])

REVIEWABLE_STATUSES = {
    TaskAttemptStatus.COMMITTED,
    TaskAttemptStatus.REVIEWING,
}
FOLLOW_UP_SOURCE_STATUSES = {
    TaskAttemptStatus.COMMITTED,
    TaskAttemptStatus.REVIEWING,
    TaskAttemptStatus.REJECTED,
    TaskAttemptStatus.WORKER_FAILED,
    TaskAttemptStatus.FAILED,
}


class AcceptAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    review_summary: str | None = Field(default=None, max_length=100_000)


class RejectAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reason: str = Field(min_length=1, max_length=100_000)


class FollowUpAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    feedback: str = Field(min_length=1, max_length=100_000)


class AttemptActionResponse(BaseModel):
    attempt: AttemptView
    work_room_message: WorkRoomMessageView


class FollowUpAttemptResponse(BaseModel):
    source_attempt: AttemptView
    follow_up_attempt: AttemptView
    work_room_message: WorkRoomMessageView


def _owned_attempt(session: Session, attempt_id: str, user_id: str) -> TaskAttempt:
    attempt = session.get(TaskAttempt, attempt_id)
    if attempt is None or attempt.local_user_id != user_id:
        raise HTTPException(status_code=404, detail="TaskAttempt not found")
    return attempt


def _task_for_attempt(session: Session, attempt: TaskAttempt) -> Task:
    task = session.get(Task, attempt.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _transition_attempt(attempt: TaskAttempt, target: TaskAttemptStatus) -> None:
    try:
        assert_task_attempt_transition(attempt.status, target)
    except StateTransitionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error.detail()) from error
    attempt.status = target


def _add_work_room_message(
    session: Session,
    *,
    task: Task,
    attempt: TaskAttempt,
    sender: WorkRoomMessageSender,
    message_type: WorkRoomMessageType,
    content: str,
    metadata: dict[str, object],
) -> TaskWorkRoomMessage:
    message = TaskWorkRoomMessage(
        local_user_id=attempt.local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=attempt.task_id,
        task_attempt_id=attempt.id,
        worker_id=attempt.worker_id,
        sender=sender,
        message_type=message_type,
        content=content,
        content_type="text/markdown",
        metadata_json=metadata,
    )
    session.add(message)
    session.flush()
    return message


def _audit(
    session: Session,
    current: CurrentAuth,
    *,
    event_type: str,
    message: str,
    task: Task,
    attempt: TaskAttempt,
    metadata: dict[str, object],
) -> None:
    record_audit_event(
        session,
        event_type=event_type,
        message=message,
        local_user_id=current.user.id,
        device_id=current.device.id,
        session_id=current.runtime_session.id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        metadata={"task_id": task.id, "task_attempt_id": attempt.id, **metadata},
    )


@router.post("/task-attempts/{attempt_id}/accept", response_model=AttemptActionResponse)
def accept_attempt(
    attempt_id: str,
    request: AcceptAttemptRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> AttemptActionResponse:
    attempt = _owned_attempt(session, attempt_id, current.user.id)
    task = _task_for_attempt(session, attempt)
    if attempt.status not in REVIEWABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Attempt is not reviewable")

    now = datetime.now(timezone.utc)
    _transition_attempt(attempt, TaskAttemptStatus.ACCEPTED)
    attempt.completed_at = now
    attempt.result_summary = request.review_summary or attempt.result_summary

    content = request.review_summary or "Attempt accepted by Owner."
    work_room_message = _add_work_room_message(
        session,
        task=task,
        attempt=attempt,
        sender=WorkRoomMessageSender.OWNER,
        message_type=WorkRoomMessageType.SYSTEM_EVENT,
        content=content,
        metadata={"action": "accept"},
    )
    _audit(
        session,
        current,
        event_type="task_attempt.accepted",
        message="Task attempt accepted",
        task=task,
        attempt=attempt,
        metadata={"message_id": work_room_message.id},
    )
    session.commit()
    session.refresh(attempt)
    session.refresh(work_room_message)
    return AttemptActionResponse(
        attempt=attempt_view(attempt),
        work_room_message=work_room_message_view(work_room_message),
    )


@router.post("/task-attempts/{attempt_id}/reject", response_model=AttemptActionResponse)
def reject_attempt(
    attempt_id: str,
    request: RejectAttemptRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> AttemptActionResponse:
    attempt = _owned_attempt(session, attempt_id, current.user.id)
    task = _task_for_attempt(session, attempt)
    if attempt.status not in REVIEWABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Attempt is not reviewable")

    now = datetime.now(timezone.utc)
    _transition_attempt(attempt, TaskAttemptStatus.REJECTED)
    attempt.completed_at = now
    attempt.result_summary = request.reason

    work_room_message = _add_work_room_message(
        session,
        task=task,
        attempt=attempt,
        sender=WorkRoomMessageSender.OWNER,
        message_type=WorkRoomMessageType.OWNER_FEEDBACK,
        content=request.reason,
        metadata={"action": "reject"},
    )
    _audit(
        session,
        current,
        event_type="task_attempt.rejected",
        message="Task attempt rejected",
        task=task,
        attempt=attempt,
        metadata={"message_id": work_room_message.id},
    )
    session.commit()
    session.refresh(attempt)
    session.refresh(work_room_message)
    return AttemptActionResponse(
        attempt=attempt_view(attempt),
        work_room_message=work_room_message_view(work_room_message),
    )


@router.post("/task-attempts/{attempt_id}/follow-up", response_model=FollowUpAttemptResponse)
def request_follow_up(
    attempt_id: str,
    request: FollowUpAttemptRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> FollowUpAttemptResponse:
    source_attempt = _owned_attempt(session, attempt_id, current.user.id)
    task = _task_for_attempt(session, source_attempt)
    try:
        ensure_explicit_retry_allowed(session, task=task, source_attempt=source_attempt)
    except ExplicitRetryPolicyError as error:
        raise HTTPException(status_code=409, detail=error.detail()) from error

    now = datetime.now(timezone.utc)
    if source_attempt.status in REVIEWABLE_STATUSES:
        _transition_attempt(source_attempt, TaskAttemptStatus.REJECTED)
        source_attempt.completed_at = now
        source_attempt.result_summary = request.feedback

    next_number = (
        session.scalar(
            select(func.max(TaskAttempt.attempt_number)).where(TaskAttempt.task_id == task.id)
        )
        or 0
    ) + 1
    follow_up_attempt = TaskAttempt(
        task_id=task.id,
        local_user_id=current.user.id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        status=TaskAttemptStatus.CREATED,
        attempt_number=next_number,
    )
    session.add(follow_up_attempt)
    session.flush()

    work_room_message = _add_work_room_message(
        session,
        task=task,
        attempt=follow_up_attempt,
        sender=WorkRoomMessageSender.OWNER,
        message_type=WorkRoomMessageType.OWNER_FEEDBACK,
        content=request.feedback,
        metadata={
            "action": "follow_up",
            "source_attempt_id": source_attempt.id,
            "explicit_retry": True,
            "automatic_retry": False,
        },
    )
    _audit(
        session,
        current,
        event_type="task_attempt.follow_up_requested",
        message="Task follow-up attempt created",
        task=task,
        attempt=follow_up_attempt,
        metadata={
            "source_attempt_id": source_attempt.id,
            "follow_up_attempt_id": follow_up_attempt.id,
            "message_id": work_room_message.id,
            "explicit_retry": True,
            "automatic_retry": False,
        },
    )
    session.commit()
    session.refresh(source_attempt)
    session.refresh(follow_up_attempt)
    session.refresh(work_room_message)
    return FollowUpAttemptResponse(
        source_attempt=attempt_view(source_attempt),
        follow_up_attempt=attempt_view(follow_up_attempt),
        work_room_message=work_room_message_view(work_room_message),
    )
