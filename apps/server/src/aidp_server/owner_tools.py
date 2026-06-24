from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidp_server.audit import record_audit_event
from aidp_server.db.models import (
    AgentRun,
    Device,
    DeviceType,
    Project,
    RecordStatus,
    RiskLevel,
    Task,
    TaskAttempt,
    TaskAttemptStatus,
    TaskStatus,
    ToolCall,
    ToolCallerType,
    ToolCallStatus,
    ToolRegistryEntry,
    Worker,
    WorkerRun,
    WorkerStatus,
)
from aidp_server.tool_registry import seed_tool_registry

ALLOWED_OWNER_TOOLS = {
    "project.list",
    "task.list",
    "task.create",
    "attempt.accept",
    "attempt.reject",
    "attempt.follow_up",
    "worker.start_task_attempt",
    "worker.run_task_attempt",
}
READ_ONLY_OWNER_TOOLS = {"project.list", "task.list"}


def apply_authority_envelope(session: Session, tool_call: ToolCall, mode: str = "personal") -> bool:
    """Apply the Personal Mode authority envelope for Owner-requested tool calls."""
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
            "side_effect": tool_call.tool_name not in READ_ONLY_OWNER_TOOLS,
        },
    )

    if tool_call.tool_name in ALLOWED_OWNER_TOOLS:
        return True

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


def _fail(tool_call: ToolCall, code: str, message: str) -> dict[str, str]:
    tool_call.status = ToolCallStatus.FAILED
    tool_call.error_code = code
    tool_call.error_message = message
    return {"error": code}


def _owned_task(session: Session, task_id: str | None, user_id: str | None) -> Task | None:
    if not task_id:
        return None
    task = session.get(Task, task_id)
    if task is None or task.local_user_id != user_id:
        return None
    return task


def _owned_attempt(
    session: Session, attempt_id: str | None, user_id: str | None
) -> TaskAttempt | None:
    if not attempt_id:
        return None
    attempt = session.get(TaskAttempt, attempt_id)
    if attempt is None or attempt.local_user_id != user_id:
        return None
    return attempt


def _system_worker(session: Session, user_id: str, worker_adapter: str) -> Worker | None:
    db_worker_kind = "mock" if worker_adapter == "agy" else worker_adapter
    from aidp_server.db.models import WorkerKind

    try:
        WorkerKind(db_worker_kind)
    except ValueError:
        return None

    worker = session.scalars(select(Worker).where(Worker.worker_kind == db_worker_kind)).first()
    if worker:
        return worker

    device = session.scalars(
        select(Device)
        .where(Device.local_user_id == user_id)
        .where(Device.device_type == DeviceType.LOCAL_RUNTIME)
    ).first()
    if not device:
        device = session.scalars(select(Device).where(Device.local_user_id == user_id)).first()
    if not device:
        device = Device(
            local_user_id=user_id,
            device_type=DeviceType.LOCAL_RUNTIME,
            display_name="System Local Runtime",
        )
        session.add(device)
        session.flush()

    worker = Worker(
        local_user_id=user_id,
        device_id=device.id,
        display_name=f"System {db_worker_kind} Worker",
        worker_kind=db_worker_kind,
        status=WorkerStatus.AVAILABLE,
        capabilities_json={},
    )
    session.add(worker)
    session.flush()
    return worker


def _create_worker_run_for_attempt(
    session: Session,
    *,
    tool_call: ToolCall,
    task: Task,
    attempt: TaskAttempt,
    worker: Worker,
    worker_adapter: str,
) -> WorkerRun | None:
    existing_active_run = session.scalars(
        select(WorkerRun)
        .where(WorkerRun.task_attempt_id == attempt.id)
        .where(WorkerRun.status.in_([RecordStatus.CREATED, RecordStatus.RUNNING]))
        .order_by(WorkerRun.created_at.desc())
    ).first()
    if existing_active_run is not None:
        _fail(tool_call, "worker_run_exists", "TaskAttempt already has an active WorkerRun")
        return None

    attempt.worker_id = worker.id
    attempt.claimed_by_worker_id = worker.id
    worker_run = WorkerRun(
        local_user_id=tool_call.user_id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        task_id=task.id,
        task_attempt_id=attempt.id,
        worker_id=worker.id,
        adapter_kind=worker_adapter,
        status=RecordStatus.CREATED,
    )
    session.add(worker_run)
    session.flush()
    return worker_run


def _active_worker_run_for_worker(session: Session, worker_run: WorkerRun) -> WorkerRun | None:
    return session.scalars(
        select(WorkerRun)
        .where(WorkerRun.worker_id == worker_run.worker_id)
        .where(WorkerRun.id != worker_run.id)
        .where(WorkerRun.status == RecordStatus.RUNNING)
        .order_by(WorkerRun.created_at.asc())
    ).first()


def _queue_due_to_worker_capacity(
    session: Session,
    tool_call: ToolCall,
    *,
    worker_run: WorkerRun,
    attempt: TaskAttempt,
    active_worker_run: WorkerRun,
) -> dict[str, Any]:
    record_audit_event(
        session,
        event_type="worker_run.queued_capacity_full",
        message="WorkerRun left queued because worker capacity is full",
        local_user_id=tool_call.user_id,
        project_id=attempt.project_id,
        agent_run_id=tool_call.agent_run_id,
        tool_call_id=tool_call.id,
        metadata={
            "task_attempt_id": attempt.id,
            "worker_run_id": worker_run.id,
            "worker_id": worker_run.worker_id,
            "active_worker_run_id": active_worker_run.id,
            "capacity": 1,
        },
    )
    return {
        "task_attempt_id": attempt.id,
        "worker_run_id": worker_run.id,
        "status": "queued",
        "reason": "worker_capacity_full",
        "active_worker_run_id": active_worker_run.id,
        "worker_capacity": 1,
    }


def execute_owner_tool(
    session: Session, tool_call: ToolCall, background_tasks: BackgroundTasks | None = None
) -> dict[str, Any]:
    if tool_call.tool_name == "project.list":
        projects = session.scalars(
            select(Project)
            .where(Project.local_user_id == tool_call.user_id)
            .order_by(Project.created_at.desc())
        ).all()
        return {"projects": [{"id": p.id, "name": p.name} for p in projects]}

    if tool_call.tool_name == "task.list":
        query = select(Task).where(Task.local_user_id == tool_call.user_id)
        if tool_call.project_id:
            query = query.where(Task.project_id == tool_call.project_id)
        tasks = session.scalars(query.order_by(Task.created_at.desc())).all()
        return {"tasks": [{"id": t.id, "title": t.title, "status": t.status.value} for t in tasks]}

    if tool_call.tool_name == "task.create":
        args = tool_call.arguments_json or {}
        task = Task(
            local_user_id=tool_call.user_id,
            project_id=tool_call.project_id,
            agent_run_id=tool_call.agent_run_id,
            repository_id=args.get("repository_id"),
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
            metadata={"task_id": task.id, "source": "owner_tool", "repository_id": task.repository_id},
        )
        return {"task_id": task.id}

    if tool_call.tool_name in {"attempt.accept", "attempt.reject", "attempt.follow_up"}:
        from aidp_server.owner_attempt_tools import execute_attempt_action_tool

        return execute_attempt_action_tool(session, tool_call)

    if tool_call.tool_name == "worker.start_task_attempt":
        args = tool_call.arguments_json or {}
        worker_adapter = args.get("worker_adapter", "mock")
        worker = _system_worker(session, tool_call.user_id, worker_adapter)
        if worker is None:
            return _fail(tool_call, "unsupported_worker_adapter", f"Unsupported adapter: {worker_adapter}")

        attempt_id = args.get("task_attempt_id")
        if attempt_id:
            attempt = _owned_attempt(session, attempt_id, tool_call.user_id)
            if attempt is None:
                return _fail(tool_call, "task_attempt_not_found", "TaskAttempt not found or access denied")
            task = _owned_task(session, attempt.task_id, tool_call.user_id)
            if task is None:
                return _fail(tool_call, "task_not_found", "Task not found or access denied")
            if attempt.status is not TaskAttemptStatus.CREATED:
                return _fail(
                    tool_call,
                    "task_attempt_not_startable",
                    "Only created TaskAttempts can be started by this tool",
                )
        else:
            task = _owned_task(session, args.get("task_id"), tool_call.user_id)
            if task is None:
                return _fail(tool_call, "task_not_found", "Task not found or access denied")
            attempt_number = (
                session.scalar(
                    select(func.coalesce(func.max(TaskAttempt.attempt_number), 0)).where(
                        TaskAttempt.task_id == task.id
                    )
                )
                + 1
            )
            attempt = TaskAttempt(
                task_id=task.id,
                local_user_id=tool_call.user_id,
                project_id=task.project_id,
                repository_id=task.repository_id,
                worker_id=worker.id,
                claimed_by_worker_id=worker.id,
                status=TaskAttemptStatus.CREATED,
                attempt_number=attempt_number,
            )
            session.add(attempt)
            session.flush()

        worker_run = _create_worker_run_for_attempt(
            session,
            tool_call=tool_call,
            task=task,
            attempt=attempt,
            worker=worker,
            worker_adapter=worker_adapter,
        )
        if worker_run is None:
            return {"error": tool_call.error_code}

        record_audit_event(
            session,
            event_type="owner_tool_call.completed",
            message="worker.start_task_attempt completed",
            local_user_id=tool_call.user_id,
            project_id=task.project_id,
            agent_run_id=tool_call.agent_run_id,
            tool_call_id=tool_call.id,
            metadata={
                "fresh_worker_context": True,
                "previous_worker_context_reused": False,
                "continuity_source": "owner_authored_task_packet",
                "task_attempt_id": attempt.id,
                "worker_run_id": worker_run.id,
                "existing_attempt": bool(attempt_id),
            },
        )
        return {
            "task_attempt_id": attempt.id,
            "worker_run_id": worker_run.id,
            "status": "queued",
            "fresh_worker_context": True,
            "existing_attempt": bool(attempt_id),
        }

    if tool_call.tool_name == "worker.run_task_attempt":
        args = tool_call.arguments_json or {}
        worker_run_id = args.get("worker_run_id")
        task_attempt_id = args.get("task_attempt_id")
        if not worker_run_id and not task_attempt_id:
            return _fail(
                tool_call,
                "invalid_arguments",
                "worker_run_id or task_attempt_id is required",
            )

        worker_run = None
        attempt = None
        if worker_run_id:
            worker_run = session.get(WorkerRun, worker_run_id)
            if worker_run:
                attempt = session.get(TaskAttempt, worker_run.task_attempt_id)
        elif task_attempt_id:
            attempt = session.get(TaskAttempt, task_attempt_id)
            if attempt:
                worker_run = session.scalars(
                    select(WorkerRun)
                    .where(WorkerRun.task_attempt_id == attempt.id)
                    .order_by(WorkerRun.created_at.desc())
                ).first()

        if not worker_run:
            return _fail(tool_call, "worker_run_not_found", "WorkerRun not found")
        if not attempt:
            return _fail(tool_call, "task_attempt_not_found", "TaskAttempt not found")
        if worker_run.adapter_kind not in {"mock", "agy"}:
            return _fail(
                tool_call,
                "unsupported_worker_adapter",
                f"Unsupported worker adapter: {worker_run.adapter_kind}",
            )

        active_worker_run = _active_worker_run_for_worker(session, worker_run)
        if active_worker_run is not None:
            return _queue_due_to_worker_capacity(
                session,
                tool_call,
                worker_run=worker_run,
                attempt=attempt,
                active_worker_run=active_worker_run,
            )

        from aidp_server.config import get_settings
        from aidp_server.db.models import utc_now

        settings = get_settings()
        if worker_run.adapter_kind == "agy":
            if not settings.allow_owner_agy_worker_run:
                record_audit_event(
                    session,
                    event_type="owner_tool_call.rejected",
                    message="worker.run_task_attempt rejected (AGY disabled)",
                    local_user_id=tool_call.user_id,
                    project_id=attempt.project_id,
                    agent_run_id=tool_call.agent_run_id,
                    tool_call_id=tool_call.id,
                    metadata={"adapter": "agy", "gate": "disabled"},
                )
                return _fail(
                    tool_call,
                    "agy_worker_disabled",
                    "Owner-triggered AGY worker execution is disabled by local configuration.",
                )

            if not background_tasks:
                raise RuntimeError("background_tasks is required for AGY handoff")
            task = session.get(Task, attempt.task_id)
            from aidp_server.worker_execution import get_worker_execution_service
            from aidp_server.worktrees import ensure_worktree

            ensure_worktree(session, settings, attempt.id, tool_call.user_id)
            handoff_result = get_worker_execution_service(background_tasks).run_task_attempt(
                session=session,
                worker_run=worker_run,
                task_attempt=attempt,
                task=task,
                tool_call=tool_call,
                settings=settings,
            )
            worker_run.status = RecordStatus.RUNNING
            attempt.status = TaskAttemptStatus.RUNNING_WORKER
            session.flush()
            record_audit_event(
                session,
                event_type="owner_tool_call.completed",
                message="worker.run_task_attempt completed (AGY handoff)",
                local_user_id=tool_call.user_id,
                project_id=attempt.project_id,
                agent_run_id=tool_call.agent_run_id,
                tool_call_id=tool_call.id,
                metadata={
                    "task_attempt_id": attempt.id,
                    "worker_run_id": worker_run.id,
                    "adapter": "agy",
                    "fresh_worker_context": True,
                    "previous_worker_context_reused": False,
                },
            )
            return handoff_result

        now = utc_now()
        worker_run.status = RecordStatus.SUCCEEDED
        worker_run.completed_at = now
        worker_run.summary = "Mock execution completed by owner tool"
        attempt.status = TaskAttemptStatus.ACCEPTED
        attempt.completed_at = now
        attempt.result_summary = "Mock execution completed by owner tool"
        session.flush()
        record_audit_event(
            session,
            event_type="owner_tool_call.completed",
            message="worker.run_task_attempt completed",
            local_user_id=tool_call.user_id,
            project_id=attempt.project_id,
            agent_run_id=tool_call.agent_run_id,
            tool_call_id=tool_call.id,
            metadata={
                "task_attempt_id": attempt.id,
                "worker_run_id": worker_run.id,
                "fresh_worker_context": True,
                "previous_worker_context_reused": False,
            },
        )
        return {
            "task_attempt_id": attempt.id,
            "worker_run_id": worker_run.id,
            "status": "succeeded",
            "adapter": "mock",
            "fresh_worker_context": True,
            "previous_worker_context_reused": False,
        }

    raise ValueError(f"Unsupported tool: {tool_call.tool_name}")


def request_owner_tool_call(
    session: Session,
    agent_run_id: str,
    provider_kind: str,
    tool_name: str,
    arguments_json: dict[str, Any],
    provider_call_id: str | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> ToolCall:
    """Entrypoint for Owner Runtime Providers to request a tool call."""
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

    allowed = apply_authority_envelope(session, call)
    if not allowed:
        return call

    call.status = ToolCallStatus.RUNNING
    call.started_at = datetime.now(timezone.utc)
    session.add(call)
    session.flush()

    try:
        result = execute_owner_tool(session, call, background_tasks=background_tasks)
        if call.status is not ToolCallStatus.FAILED:
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
