from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidp_server.attempt_retry_policy import (
    ExplicitRetryPolicyError,
    ensure_explicit_retry_allowed,
)
from aidp_server.db.models import Task, TaskAttempt, TaskAttemptStatus, ToolCall
from aidp_server.state_transitions import StateTransitionError, assert_task_attempt_transition
from aidp_server.work_room import (
    TaskWorkRoomMessage,
    WorkRoomMessageSender,
    WorkRoomMessageType,
)

REVIEWABLE = {TaskAttemptStatus.COMMITTED, TaskAttemptStatus.REVIEWING}
FOLLOW_UP_SOURCES = REVIEWABLE | {
    TaskAttemptStatus.REJECTED,
    TaskAttemptStatus.WORKER_FAILED,
    TaskAttemptStatus.FAILED,
}


def _fail(tool_call: ToolCall, code: str, message: str) -> dict[str, str]:
    tool_call.error_code = code
    tool_call.error_message = message
    return {"error": code}


def _attempt(session: Session, tool_call: ToolCall) -> TaskAttempt | None:
    attempt_id = (tool_call.arguments_json or {}).get("task_attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id:
        _fail(tool_call, "invalid_arguments", "task_attempt_id is required")
        return None
    attempt = session.get(TaskAttempt, attempt_id)
    if attempt is None or attempt.local_user_id != tool_call.user_id:
        _fail(tool_call, "task_attempt_not_found", "TaskAttempt not found or access denied")
        return None
    return attempt


def _task(session: Session, tool_call: ToolCall, attempt: TaskAttempt) -> Task | None:
    task = session.get(Task, attempt.task_id)
    if task is None or task.local_user_id != tool_call.user_id:
        _fail(tool_call, "task_not_found", "Task not found or access denied")
        return None
    return task


def _transition(tool_call: ToolCall, attempt: TaskAttempt, target: TaskAttemptStatus) -> bool:
    try:
        assert_task_attempt_transition(attempt.status, target)
    except StateTransitionError as error:
        _fail(tool_call, "state_transition_not_allowed", str(error))
        return False
    attempt.status = target
    return True


def _message(
    session: Session,
    *,
    task: Task,
    attempt: TaskAttempt,
    message_type: WorkRoomMessageType,
    content: str,
    metadata: dict[str, object],
) -> TaskWorkRoomMessage:
    message = TaskWorkRoomMessage(
        local_user_id=attempt.local_user_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        task_id=task.id,
        task_attempt_id=attempt.id,
        worker_id=attempt.worker_id,
        sender=WorkRoomMessageSender.OWNER,
        message_type=message_type,
        content=content,
        content_type="text/markdown",
        metadata_json=metadata,
    )
    session.add(message)
    session.flush()
    return message


def accept_attempt(session: Session, tool_call: ToolCall) -> dict[str, Any]:
    attempt = _attempt(session, tool_call)
    if attempt is None:
        return {"error": tool_call.error_code}
    task = _task(session, tool_call, attempt)
    if task is None:
        return {"error": tool_call.error_code}
    if attempt.status not in REVIEWABLE:
        return _fail(tool_call, "attempt_not_reviewable", "Attempt is not reviewable")

    args = tool_call.arguments_json or {}
    review_summary = args.get("review_summary")
    content = review_summary if isinstance(review_summary, str) and review_summary else "Attempt accepted."
    if not _transition(tool_call, attempt, TaskAttemptStatus.ACCEPTED):
        return {"error": tool_call.error_code}
    attempt.completed_at = datetime.now(timezone.utc)
    if isinstance(review_summary, str) and review_summary:
        attempt.result_summary = review_summary
    message = _message(
        session,
        task=task,
        attempt=attempt,
        message_type=WorkRoomMessageType.SYSTEM_EVENT,
        content=content,
        metadata={"action": "accept"},
    )
    return {
        "task_id": task.id,
        "task_attempt_id": attempt.id,
        "status": attempt.status.value,
        "work_room_message_id": message.id,
        "explicit_retry": True,
        "automatic_retry": False,
    }


def reject_attempt(session: Session, tool_call: ToolCall) -> dict[str, Any]:
    attempt = _attempt(session, tool_call)
    if attempt is None:
        return {"error": tool_call.error_code}
    task = _task(session, tool_call, attempt)
    if task is None:
        return {"error": tool_call.error_code}
    if attempt.status not in REVIEWABLE:
        return _fail(tool_call, "attempt_not_reviewable", "Attempt is not reviewable")

    reason = (tool_call.arguments_json or {}).get("reason")
    if not isinstance(reason, str) or not reason:
        return _fail(tool_call, "invalid_arguments", "reason is required")
    if not _transition(tool_call, attempt, TaskAttemptStatus.REJECTED):
        return {"error": tool_call.error_code}
    attempt.completed_at = datetime.now(timezone.utc)
    attempt.result_summary = reason
    message = _message(
        session,
        task=task,
        attempt=attempt,
        message_type=WorkRoomMessageType.OWNER_FEEDBACK,
        content=reason,
        metadata={"action": "reject"},
    )
    return {
        "task_id": task.id,
        "task_attempt_id": attempt.id,
        "status": attempt.status.value,
        "work_room_message_id": message.id,
    }


def follow_up_attempt(session: Session, tool_call: ToolCall) -> dict[str, Any]:
    source = _attempt(session, tool_call)
    if source is None:
        return {"error": tool_call.error_code}
    task = _task(session, tool_call, source)
    if task is None:
        return {"error": tool_call.error_code}
    try:
        ensure_explicit_retry_allowed(session, task=task, source_attempt=source)
    except ExplicitRetryPolicyError as error:
        return _fail(tool_call, error.code, error.message)

    feedback = (tool_call.arguments_json or {}).get("feedback")
    if not isinstance(feedback, str) or not feedback:
        return _fail(tool_call, "invalid_arguments", "feedback is required")
    if source.status in REVIEWABLE:
        if not _transition(tool_call, source, TaskAttemptStatus.REJECTED):
            return {"error": tool_call.error_code}
        source.completed_at = datetime.now(timezone.utc)
        source.result_summary = feedback

    next_number = (
        session.scalar(select(func.max(TaskAttempt.attempt_number)).where(TaskAttempt.task_id == task.id))
        or 0
    ) + 1
    follow_up = TaskAttempt(
        task_id=task.id,
        local_user_id=tool_call.user_id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        status=TaskAttemptStatus.CREATED,
        attempt_number=next_number,
    )
    session.add(follow_up)
    session.flush()
    message = _message(
        session,
        task=task,
        attempt=follow_up,
        message_type=WorkRoomMessageType.OWNER_FEEDBACK,
        content=feedback,
        metadata={
            "action": "follow_up",
            "source_attempt_id": source.id,
            "explicit_retry": True,
            "automatic_retry": False,
        },
    )
    return {
        "task_id": task.id,
        "source_task_attempt_id": source.id,
        "follow_up_task_attempt_id": follow_up.id,
        "follow_up_attempt_number": follow_up.attempt_number,
        "status": follow_up.status.value,
        "work_room_message_id": message.id,
    }


def execute_attempt_action_tool(session: Session, tool_call: ToolCall) -> dict[str, Any]:
    if tool_call.tool_name == "attempt.accept":
        return accept_attempt(session, tool_call)
    if tool_call.tool_name == "attempt.reject":
        return reject_attempt(session, tool_call)
    if tool_call.tool_name == "attempt.follow_up":
        return follow_up_attempt(session, tool_call)
    raise ValueError(f"Unsupported attempt action tool: {tool_call.tool_name}")
