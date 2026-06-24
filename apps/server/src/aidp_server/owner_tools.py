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
    TaskAttempt,
    TaskAttemptStatus,
    WorkerRun,
    RecordStatus,
    Worker,
    WorkerStatus,
    Device,
    DeviceType,
)
from sqlalchemy import func
from aidp_server.tool_registry import seed_tool_registry
from fastapi import BackgroundTasks


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
    if tool_call.tool_name in [
        "project.list",
        "task.list",
        "task.create",
        "worker.start_task_attempt",
        "worker.run_task_attempt",
    ]:
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

    elif tool_call.tool_name == "worker.start_task_attempt":
        args = tool_call.arguments_json or {}
        task_id = args.get("task_id")
        worker_adapter = args.get("worker_adapter", "mock")

        if not task_id:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_code = "invalid_arguments"
            tool_call.error_message = "task_id is required"
            return {"error": "task_id is required"}

        task = session.get(Task, task_id)
        if not task or task.local_user_id != tool_call.user_id:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_code = "task_not_found"
            tool_call.error_message = "Task not found or access denied"
            return {"error": "task_not_found"}

        # for agy adapter, we use a mock worker for now to satisfy DB constraints
        db_worker_kind = "mock" if worker_adapter == "agy" else worker_adapter

        try:
            from aidp_server.db.models import WorkerKind

            WorkerKind(db_worker_kind)
        except ValueError:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_code = "unsupported_worker_adapter"
            tool_call.error_message = f"Unsupported adapter: {worker_adapter}"
            return {"error": "unsupported_worker_adapter"}

        worker = session.scalars(select(Worker).where(Worker.worker_kind == db_worker_kind)).first()
        if not worker:
            device = session.scalars(
                select(Device)
                .where(Device.local_user_id == tool_call.user_id)
                .where(Device.device_type == DeviceType.LOCAL_RUNTIME)
            ).first()

            if not device:
                device = session.scalars(
                    select(Device).where(Device.local_user_id == tool_call.user_id)
                ).first()

            if not device:
                device = Device(
                    local_user_id=tool_call.user_id,
                    device_type=DeviceType.LOCAL_RUNTIME,
                    display_name="System Local Runtime",
                )
                session.add(device)
                session.flush()

            worker = Worker(
                local_user_id=tool_call.user_id,
                device_id=device.id,
                display_name=f"System {db_worker_kind} Worker",
                worker_kind=db_worker_kind,
                status=WorkerStatus.AVAILABLE,
                capabilities_json={},
            )
            session.add(worker)
            session.flush()

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
            },
        )

        return {
            "task_attempt_id": attempt.id,
            "worker_run_id": worker_run.id,
            "status": "queued",
            "fresh_worker_context": True,
        }

    elif tool_call.tool_name == "worker.run_task_attempt":
        args = tool_call.arguments_json or {}
        worker_run_id = args.get("worker_run_id")
        task_attempt_id = args.get("task_attempt_id")

        if not worker_run_id and not task_attempt_id:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_code = "invalid_arguments"
            tool_call.error_message = "worker_run_id or task_attempt_id is required"
            return {"error": "invalid_arguments"}

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
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_code = "worker_run_not_found"
            tool_call.error_message = "WorkerRun not found"
            return {"error": "worker_run_not_found"}

        if not attempt:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_code = "task_attempt_not_found"
            tool_call.error_message = "TaskAttempt not found"
            return {"error": "task_attempt_not_found"}

        if worker_run.adapter_kind not in ["mock", "agy"]:
            tool_call.status = ToolCallStatus.FAILED
            tool_call.error_code = "unsupported_worker_adapter"
            tool_call.error_message = f"Unsupported worker adapter: {worker_run.adapter_kind}"
            return {"error": "unsupported_worker_adapter"}

        from aidp_server.config import get_settings
        from aidp_server.db.models import utc_now

        settings = get_settings()
        now = utc_now()

        if worker_run.adapter_kind == "agy":
            if not settings.allow_owner_agy_worker_run:
                tool_call.status = ToolCallStatus.FAILED
                tool_call.error_code = "agy_worker_disabled"
                tool_call.error_message = (
                    "Owner-triggered AGY worker execution is disabled by local configuration."
                )

                record_audit_event(
                    session,
                    event_type="owner_tool_call.rejected",
                    message="worker.run_task_attempt rejected (AGY disabled)",
                    local_user_id=tool_call.user_id,
                    project_id=attempt.project_id,
                    agent_run_id=tool_call.agent_run_id,
                    tool_call_id=tool_call.id,
                    metadata={
                        "tool_name": "worker.run_task_attempt",
                        "mode": "personal",
                        "authority_applied": True,
                        "owner_judgment_replaced": False,
                        "side_effect": True,
                        "fresh_worker_context": True,
                        "implicit_worker_memory": False,
                        "previous_worker_context_reused": False,
                        "continuity_source": "owner_authored_task_packet",
                        "adapter": "agy",
                        "gate": "disabled",
                    },
                )

                return {
                    "error": "agy_worker_disabled",
                    "adapter": "agy",
                    "gate": "disabled",
                    "fresh_worker_context": True,
                    "previous_worker_context_reused": False,
                }
            else:
                task = session.get(Task, attempt.task_id)
                if not background_tasks:
                    raise RuntimeError("background_tasks is required for AGY handoff")

                try:
                    from aidp_server.worker_execution import get_worker_execution_service

                    exec_service = get_worker_execution_service(background_tasks)
                    handoff_result = exec_service.run_task_attempt(
                        session=session,
                        worker_run=worker_run,
                        task_attempt=attempt,
                        task=task,
                        tool_call=tool_call,
                        settings=settings,
                    )
                except NotImplementedError as e:
                    tool_call.status = ToolCallStatus.FAILED
                    tool_call.error_code = "agy_handoff_not_implemented"
                    tool_call.error_message = str(e)

                    record_audit_event(
                        session,
                        event_type="owner_tool_call.rejected",
                        message="worker.run_task_attempt rejected (AGY handoff not implemented)",
                        local_user_id=tool_call.user_id,
                        project_id=attempt.project_id,
                        agent_run_id=tool_call.agent_run_id,
                        tool_call_id=tool_call.id,
                        metadata={
                            "tool_name": "worker.run_task_attempt",
                            "mode": "personal",
                            "authority_applied": True,
                            "owner_judgment_replaced": False,
                            "side_effect": True,
                            "fresh_worker_context": True,
                            "implicit_worker_memory": False,
                            "previous_worker_context_reused": False,
                            "continuity_source": "owner_authored_task_packet",
                            "adapter": "agy",
                            "error": "agy_handoff_not_implemented",
                        },
                    )
                    return {
                        "error": "agy_handoff_not_implemented",
                        "adapter": "agy",
                        "fresh_worker_context": True,
                        "previous_worker_context_reused": False,
                    }

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
                        "tool_name": "worker.run_task_attempt",
                        "mode": "personal",
                        "authority_applied": True,
                        "owner_judgment_replaced": False,
                        "side_effect": True,
                        "fresh_worker_context": True,
                        "implicit_worker_memory": False,
                        "previous_worker_context_reused": False,
                        "continuity_source": "owner_authored_task_packet",
                        "task_attempt_id": attempt.id,
                        "worker_run_id": worker_run.id,
                        "adapter": "agy",
                    },
                )

                return handoff_result

        from aidp_server.db.models import utc_now

        now = utc_now()

        # update statuses
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
                "tool_name": "worker.run_task_attempt",
                "mode": "personal",
                "authority_applied": True,
                "owner_judgment_replaced": False,
                "side_effect": True,
                "fresh_worker_context": True,
                "implicit_worker_memory": False,
                "previous_worker_context_reused": False,
                "continuity_source": "owner_authored_task_packet",
                "task_attempt_id": attempt.id,
                "worker_run_id": worker_run.id,
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
        result = execute_owner_tool(session, call, background_tasks=background_tasks)
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
