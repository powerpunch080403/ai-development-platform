from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidp_server.db.models import (
    AgentRun,
    AgentRunStatus,
    AgentRunStep,
    AgentRunStepType,
    RecordStatus,
    ToolCall,
    ToolCallStatus,
)


@dataclass(frozen=True)
class OwnerToolRequest:
    tool_name: str
    arguments_json: dict[str, Any] = field(default_factory=dict)
    provider_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_step_index(session: Session, run_id: str) -> int:
    return (
        session.scalar(
            select(func.max(AgentRunStep.step_index)).where(AgentRunStep.agent_run_id == run_id)
        )
        or -1
    ) + 1


def _step_status_for_tool_call(call: ToolCall) -> RecordStatus:
    if call.status is ToolCallStatus.SUCCEEDED:
        return RecordStatus.SUCCEEDED
    if call.status in {
        ToolCallStatus.FAILED,
        ToolCallStatus.REJECTED,
        ToolCallStatus.CANCELLED,
        ToolCallStatus.SKIPPED_DUPLICATE,
    }:
        return RecordStatus.FAILED
    return RecordStatus.RUNNING


def request_tool_from_owner_provider(
    session: Session,
    run: AgentRun,
    *,
    provider_kind: str,
    request: OwnerToolRequest,
    background_tasks: BackgroundTasks | None = None,
) -> ToolCall:
    """Execute one Owner-requested tool through the platform ToolCall bridge.

    Owner providers call this seam instead of directly creating Tasks, WorkerRuns,
    worktrees, approvals, merge commits, or cleanup side effects.
    """

    from aidp_server.owner_tools import request_owner_tool_call

    now = _now()
    previous_status = run.status
    run.status = AgentRunStatus.EXECUTING_TOOL
    run.started_at = run.started_at or now

    step = AgentRunStep(
        agent_run_id=run.id,
        step_index=_next_step_index(session, run.id),
        step_type=AgentRunStepType.TOOL_CALL,
        status=RecordStatus.RUNNING,
        summary=f"Owner requested tool: {request.tool_name}",
        started_at=now,
        provider_kind=provider_kind,
        provider_metadata_json={
            "provider_kind": provider_kind,
            "tool_name": request.tool_name,
            "provider_call_id": request.provider_call_id,
            **request.metadata,
        },
    )
    session.add(step)
    session.flush()

    call = request_owner_tool_call(
        session=session,
        agent_run_id=run.id,
        provider_kind=provider_kind,
        tool_name=request.tool_name,
        arguments_json=request.arguments_json,
        provider_call_id=request.provider_call_id,
        background_tasks=background_tasks,
    )

    completed_at = _now()
    step.status = _step_status_for_tool_call(call)
    step.completed_at = completed_at
    step.summary = f"Owner tool completed: {request.tool_name} -> {call.status.value}"
    step.provider_metadata_json = {
        **(step.provider_metadata_json or {}),
        "tool_call_id": call.id,
        "tool_status": call.status.value,
        "tool_error_code": call.error_code,
    }
    step.error_code = call.error_code
    step.error_message = call.error_message

    if run.status is AgentRunStatus.EXECUTING_TOOL:
        run.status = previous_status

    session.flush()
    return call
