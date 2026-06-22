from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from aidp_server.audit import record_audit_event
from aidp_server.auth import CurrentAuth
from aidp_server.db.models import (
    AgentRun,
    Conversation,
    Project,
    ProjectRepository,
    RiskLevel,
    Task,
    TaskAttempt,
    TaskAttemptStatus,
    TaskStatus,
    WorkItem,
    WorkItemStatus,
    WorkItemType,
    Worker,
    WorkerKind,
    WorkerStatus,
)
from aidp_server.db.session import get_session

LEASE_TTL = timedelta(minutes=5)
RELEASE_STATUSES = {
    TaskAttemptStatus.WORKER_FAILED,
    TaskAttemptStatus.CANCELLED,
    TaskAttemptStatus.CREATED,
    TaskAttemptStatus.REVIEWING,
}
FRESH_CLAIM_STATUSES = {
    TaskAttemptStatus.CREATED,
    TaskAttemptStatus.RETRY_REQUESTED,
    TaskAttemptStatus.WORKER_FAILED,
}


def as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


class CreateWorkItemRequest(BaseModel):
    parent_work_item_id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    work_item_type: WorkItemType = WorkItemType.UNKNOWN
    priority: int | None = None


class UpdateWorkItemStatusRequest(BaseModel):
    status: WorkItemStatus


class CreateTaskRequest(BaseModel):
    repository_id: str | None = None
    work_item_id: str | None = None
    conversation_id: str | None = None
    agent_run_id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    instructions: str = Field(min_length=1, max_length=100_000)
    risk_level: RiskLevel = RiskLevel.R1
    requested_worker_kind: WorkerKind | None = None


class UpdateTaskStatusRequest(BaseModel):
    status: TaskStatus
    error_code: str | None = None
    error_message: str | None = None


class CreateAttemptRequest(BaseModel):
    status: TaskAttemptStatus = TaskAttemptStatus.CREATED


class UpdateAttemptStatusRequest(BaseModel):
    status: TaskAttemptStatus
    result_summary: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class RegisterWorkerRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=300)
    worker_kind: WorkerKind
    capabilities: dict[str, Any] | None = None


class ClaimRequest(BaseModel):
    task_attempt_id: str


class ReleaseRequest(BaseModel):
    task_attempt_id: str
    next_status: TaskAttemptStatus | None = None
    result_summary: str | None = None


class WorkItemView(BaseModel):
    id: str
    project_id: str
    parent_work_item_id: str | None
    title: str
    description: str | None
    work_item_type: str
    status: str
    priority: int | None
    created_at: datetime
    updated_at: datetime


class TaskView(BaseModel):
    id: str
    project_id: str
    repository_id: str | None
    work_item_id: str | None
    title: str
    instructions: str
    status: str
    risk_level: str
    requested_worker_kind: str | None
    created_at: datetime
    updated_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None


class AttemptView(BaseModel):
    id: str
    task_id: str
    project_id: str
    repository_id: str | None
    claimed_by_worker_id: str | None
    status: str
    attempt_number: int
    lease_expires_at: datetime | None
    claimed_at: datetime | None
    result_summary: str | None
    created_at: datetime
    updated_at: datetime


class WorkerView(BaseModel):
    id: str
    display_name: str
    worker_kind: str
    status: str
    capabilities: dict[str, Any] | None
    last_seen_at: datetime | None
    registered_at: datetime
    revoked_at: datetime | None


router = APIRouter(tags=["work, tasks, and workers"])


def owned(session: Session, model: type, object_id: str, user_id: str) -> Any:
    value = session.get(model, object_id)
    if value is None or getattr(value, "local_user_id", None) != user_id:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return value


def wi_view(v: WorkItem) -> WorkItemView:
    return WorkItemView(
        id=v.id,
        project_id=v.project_id,
        parent_work_item_id=v.parent_work_item_id,
        title=v.title,
        description=v.description,
        work_item_type=v.work_item_type.value,
        status=v.status.value,
        priority=v.priority,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def task_view(v: Task) -> TaskView:
    return TaskView(
        id=v.id,
        project_id=v.project_id,
        repository_id=v.repository_id,
        work_item_id=v.work_item_id,
        title=v.title,
        instructions=v.instructions,
        status=v.status.value,
        risk_level=v.risk_level.value,
        requested_worker_kind=v.requested_worker_kind.value if v.requested_worker_kind else None,
        created_at=v.created_at,
        updated_at=v.updated_at,
        queued_at=v.queued_at,
        started_at=v.started_at,
        completed_at=v.completed_at,
    )


def attempt_view(v: TaskAttempt) -> AttemptView:
    return AttemptView(
        id=v.id,
        task_id=v.task_id,
        project_id=v.project_id,
        repository_id=v.repository_id,
        claimed_by_worker_id=v.claimed_by_worker_id,
        status=v.status.value,
        attempt_number=v.attempt_number,
        lease_expires_at=v.lease_expires_at,
        claimed_at=v.claimed_at,
        result_summary=v.result_summary,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def worker_view(v: Worker) -> WorkerView:
    return WorkerView(
        id=v.id,
        display_name=v.display_name,
        worker_kind=v.worker_kind.value,
        status=v.status.value,
        capabilities=v.capabilities_json,
        last_seen_at=v.last_seen_at,
        registered_at=v.registered_at,
        revoked_at=v.revoked_at,
    )


def audit(session: Session, current: Any, event: str, message: str, **links: Any) -> None:
    record_audit_event(
        session,
        event_type=event,
        message=message,
        local_user_id=current.user.id,
        device_id=current.device.id,
        session_id=current.runtime_session.id,
        **links,
    )


@router.post("/projects/{project_id}/work-items", response_model=WorkItemView, status_code=201)
def create_work_item(
    project_id: str,
    request: CreateWorkItemRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> WorkItemView:
    owned(session, Project, project_id, current.user.id)
    if request.parent_work_item_id:
        parent = owned(session, WorkItem, request.parent_work_item_id, current.user.id)
        if parent.project_id != project_id:
            raise HTTPException(
                status_code=400, detail="Parent work item belongs to another project"
            )
    item = WorkItem(
        local_user_id=current.user.id,
        project_id=project_id,
        parent_work_item_id=request.parent_work_item_id,
        title=request.title,
        description=request.description,
        work_item_type=request.work_item_type,
        status=WorkItemStatus.ACTIVE,
        priority=request.priority,
    )
    session.add(item)
    session.flush()
    audit(
        session,
        current,
        "work_item.created",
        "Work item created",
        project_id=project_id,
        metadata={"work_item_id": item.id},
    )
    session.commit()
    return wi_view(item)


@router.get("/projects/{project_id}/work-items", response_model=list[WorkItemView])
def list_work_items(
    project_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[WorkItemView]:
    owned(session, Project, project_id, current.user.id)
    return [
        wi_view(v)
        for v in session.scalars(
            select(WorkItem).where(WorkItem.project_id == project_id).order_by(WorkItem.created_at)
        )
    ]


@router.get("/work-items/{item_id}", response_model=WorkItemView)
def get_work_item(
    item_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> WorkItemView:
    return wi_view(owned(session, WorkItem, item_id, current.user.id))


@router.post("/work-items/{item_id}/status", response_model=WorkItemView)
def update_work_item(
    item_id: str,
    request: UpdateWorkItemStatusRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> WorkItemView:
    item = owned(session, WorkItem, item_id, current.user.id)
    item.status = request.status
    audit(
        session,
        current,
        "work_item.status_changed",
        f"Work item status changed to {request.status.value}",
        project_id=item.project_id,
        metadata={"work_item_id": item.id},
    )
    session.commit()
    return wi_view(item)


@router.post("/projects/{project_id}/tasks", response_model=TaskView, status_code=201)
def create_task(
    project_id: str,
    request: CreateTaskRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> TaskView:
    owned(session, Project, project_id, current.user.id)
    for model, oid in (
        (ProjectRepository, request.repository_id),
        (WorkItem, request.work_item_id),
        (Conversation, request.conversation_id),
        (AgentRun, request.agent_run_id),
    ):
        if oid:
            linked = owned(session, model, oid, current.user.id)
            if getattr(linked, "project_id", project_id) != project_id:
                raise HTTPException(
                    status_code=400, detail=f"{model.__name__} belongs to another project"
                )
    task = Task(
        local_user_id=current.user.id,
        project_id=project_id,
        repository_id=request.repository_id,
        work_item_id=request.work_item_id,
        conversation_id=request.conversation_id,
        agent_run_id=request.agent_run_id,
        created_by_session_id=current.runtime_session.id,
        title=request.title,
        instructions=request.instructions,
        status=TaskStatus.DRAFT,
        risk_level=request.risk_level,
        requested_worker_kind=request.requested_worker_kind,
    )
    session.add(task)
    session.flush()
    audit(
        session,
        current,
        "task.created",
        "Task created",
        project_id=project_id,
        repository_id=request.repository_id,
        conversation_id=request.conversation_id,
        agent_run_id=request.agent_run_id,
        metadata={"task_id": task.id},
    )
    session.commit()
    return task_view(task)


@router.get("/projects/{project_id}/tasks", response_model=list[TaskView])
def list_tasks(
    project_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[TaskView]:
    owned(session, Project, project_id, current.user.id)
    return [
        task_view(v)
        for v in session.scalars(
            select(Task).where(Task.project_id == project_id).order_by(Task.created_at.desc())
        )
    ]


@router.get("/tasks/{task_id}", response_model=TaskView)
def get_task(
    task_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> TaskView:
    return task_view(owned(session, Task, task_id, current.user.id))


@router.post("/tasks/{task_id}/status", response_model=TaskView)
def update_task(
    task_id: str,
    request: UpdateTaskStatusRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> TaskView:
    task = owned(session, Task, task_id, current.user.id)
    now = datetime.now(timezone.utc)
    task.status = request.status
    task.error_code = request.error_code
    task.error_message = request.error_message
    if request.status is TaskStatus.QUEUED:
        task.queued_at = now
    elif request.status is TaskStatus.RUNNING:
        task.started_at = task.started_at or now
    elif request.status is TaskStatus.COMPLETED:
        task.completed_at = now
    elif request.status is TaskStatus.CANCELLED:
        task.cancelled_at = now
    elif request.status is TaskStatus.FAILED:
        task.failed_at = now
    audit(
        session,
        current,
        "task.status_changed",
        f"Task status changed to {request.status.value}",
        project_id=task.project_id,
        metadata={"task_id": task.id},
    )
    session.commit()
    return task_view(task)


@router.post("/tasks/{task_id}/attempts", response_model=AttemptView, status_code=201)
def create_attempt(
    task_id: str,
    request: CreateAttemptRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> AttemptView:
    task = owned(session, Task, task_id, current.user.id)
    number = (
        session.scalar(
            select(func.max(TaskAttempt.attempt_number)).where(TaskAttempt.task_id == task.id)
        )
        or 0
    ) + 1
    attempt = TaskAttempt(
        task_id=task.id,
        local_user_id=current.user.id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        status=request.status,
        attempt_number=number,
    )
    session.add(attempt)
    session.flush()
    audit(
        session,
        current,
        "task_attempt.created",
        "Task attempt created",
        project_id=task.project_id,
        repository_id=task.repository_id,
        metadata={"task_id": task.id, "task_attempt_id": attempt.id},
    )
    session.commit()
    return attempt_view(attempt)


@router.get("/tasks/{task_id}/attempts", response_model=list[AttemptView])
def list_attempts(
    task_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[AttemptView]:
    owned(session, Task, task_id, current.user.id)
    return [
        attempt_view(v)
        for v in session.scalars(
            select(TaskAttempt)
            .where(TaskAttempt.task_id == task_id)
            .order_by(TaskAttempt.attempt_number)
        )
    ]


@router.get("/task-attempts/{attempt_id}", response_model=AttemptView)
def get_attempt(
    attempt_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> AttemptView:
    return attempt_view(owned(session, TaskAttempt, attempt_id, current.user.id))


@router.post("/task-attempts/{attempt_id}/status", response_model=AttemptView)
def update_attempt(
    attempt_id: str,
    request: UpdateAttemptStatusRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> AttemptView:
    a = owned(session, TaskAttempt, attempt_id, current.user.id)
    now = datetime.now(timezone.utc)
    a.status = request.status
    a.result_summary = request.result_summary
    a.error_code = request.error_code
    a.error_message = request.error_message
    if request.status is TaskAttemptStatus.RUNNING_WORKER:
        a.started_at = a.started_at or now
    elif request.status in {TaskAttemptStatus.ACCEPTED, TaskAttemptStatus.MERGED}:
        a.completed_at = now
    elif request.status is TaskAttemptStatus.CANCELLED:
        a.cancelled_at = now
    elif request.status in {TaskAttemptStatus.FAILED, TaskAttemptStatus.WORKER_FAILED}:
        a.failed_at = now
    audit(
        session,
        current,
        "task_attempt.status_changed",
        f"Attempt status changed to {request.status.value}",
        project_id=a.project_id,
        repository_id=a.repository_id,
        metadata={"task_attempt_id": a.id},
    )
    session.commit()
    return attempt_view(a)


@router.post("/workers", response_model=WorkerView, status_code=201)
def register_worker(
    request: RegisterWorkerRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> WorkerView:
    now = datetime.now(timezone.utc)
    w = Worker(
        local_user_id=current.user.id,
        device_id=current.device.id,
        display_name=request.display_name,
        worker_kind=request.worker_kind,
        status=WorkerStatus.AVAILABLE,
        capabilities_json=request.capabilities,
        last_seen_at=now,
        registered_at=now,
    )
    session.add(w)
    session.flush()
    audit(session, current, "worker.registered", "Worker registered", metadata={"worker_id": w.id})
    session.commit()
    return worker_view(w)


@router.get("/workers", response_model=list[WorkerView])
def list_workers(
    current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[WorkerView]:
    return [
        worker_view(v)
        for v in session.scalars(
            select(Worker)
            .where(Worker.local_user_id == current.user.id)
            .order_by(Worker.registered_at)
        )
    ]


@router.get("/workers/{worker_id}", response_model=WorkerView)
def get_worker(
    worker_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> WorkerView:
    return worker_view(owned(session, Worker, worker_id, current.user.id))


@router.post("/workers/{worker_id}/heartbeat", response_model=WorkerView)
def heartbeat(
    worker_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> WorkerView:
    w = owned(session, Worker, worker_id, current.user.id)
    if w.revoked_at:
        raise HTTPException(status_code=409, detail="Worker is revoked")
    now = datetime.now(timezone.utc)
    w.last_seen_at = now
    session.execute(
        update(TaskAttempt)
        .where(TaskAttempt.claimed_by_worker_id == w.id, TaskAttempt.lease_expires_at > now)
        .values(lease_expires_at=now + LEASE_TTL),
        execution_options={"synchronize_session": False},
    )
    audit(
        session,
        current,
        "worker.heartbeat",
        "Worker heartbeat recorded",
        metadata={"worker_id": w.id},
    )
    session.commit()
    return worker_view(w)


@router.post("/workers/{worker_id}/revoke", response_model=WorkerView)
def revoke_worker(
    worker_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> WorkerView:
    w = owned(session, Worker, worker_id, current.user.id)
    w.revoked_at = datetime.now(timezone.utc)
    w.status = WorkerStatus.REVOKED
    audit(session, current, "worker.revoked", "Worker revoked", metadata={"worker_id": w.id})
    session.commit()
    return worker_view(w)


@router.post("/workers/{worker_id}/claim", response_model=AttemptView)
def claim(
    worker_id: str,
    request: ClaimRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> AttemptView:
    w = owned(session, Worker, worker_id, current.user.id)
    a = owned(session, TaskAttempt, request.task_attempt_id, current.user.id)
    if w.revoked_at:
        raise HTTPException(status_code=409, detail="Worker is revoked")
    now = datetime.now(timezone.utc)
    expired_claim = (
        a.claimed_by_worker_id and a.lease_expires_at and as_utc(a.lease_expires_at) <= now
    )
    if a.claimed_by_worker_id is None and a.status not in FRESH_CLAIM_STATUSES:
        raise HTTPException(status_code=409, detail="Attempt status is not claimable")
    if expired_claim:
        previous_worker = session.get(Worker, a.claimed_by_worker_id)
        if previous_worker and previous_worker.status is not WorkerStatus.REVOKED:
            previous_worker.status = WorkerStatus.EXPIRED
    active = session.scalar(
        select(TaskAttempt.id).where(
            TaskAttempt.claimed_by_worker_id == w.id,
            TaskAttempt.lease_expires_at > now,
            TaskAttempt.id != a.id,
        )
    )
    if active:
        raise HTTPException(status_code=409, detail="Worker already has an active claim")
    result = session.execute(
        update(TaskAttempt)
        .where(
            TaskAttempt.id == a.id,
            or_(TaskAttempt.claimed_by_worker_id.is_(None), TaskAttempt.lease_expires_at <= now),
        )
        .values(
            claimed_by_worker_id=w.id,
            worker_id=w.id,
            claimed_at=now,
            lease_expires_at=now + LEASE_TTL,
            status=TaskAttemptStatus.RUNNING_WORKER,
            started_at=func.coalesce(TaskAttempt.started_at, now),
        ),
        execution_options={"synchronize_session": False},
    )
    if getattr(result, "rowcount", 0) != 1:
        session.rollback()
        raise HTTPException(status_code=409, detail="Attempt has an active lease")
    task = session.get(Task, a.task_id)
    w.status = WorkerStatus.CLAIMED
    w.last_seen_at = now
    if task:
        task.status = TaskStatus.RUNNING
        task.started_at = task.started_at or now
    audit(
        session,
        current,
        "worker.claimed_attempt",
        "Worker claimed task attempt",
        project_id=a.project_id,
        repository_id=a.repository_id,
        metadata={"worker_id": w.id, "task_attempt_id": a.id},
    )
    session.commit()
    session.refresh(a)
    return attempt_view(a)


@router.post("/workers/{worker_id}/release", response_model=AttemptView)
def release(
    worker_id: str,
    request: ReleaseRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> AttemptView:
    w = owned(session, Worker, worker_id, current.user.id)
    a = owned(session, TaskAttempt, request.task_attempt_id, current.user.id)
    if a.claimed_by_worker_id != w.id:
        raise HTTPException(status_code=409, detail="Worker does not own this claim")
    if request.next_status and request.next_status not in RELEASE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid release next status")
    a.claimed_by_worker_id = None
    a.lease_expires_at = None
    a.claimed_at = None
    a.result_summary = request.result_summary
    if request.next_status:
        a.status = request.next_status
    w.status = WorkerStatus.AVAILABLE
    audit(
        session,
        current,
        "worker.released_attempt",
        "Worker released task attempt",
        project_id=a.project_id,
        repository_id=a.repository_id,
        metadata={"worker_id": w.id, "task_attempt_id": a.id},
    )
    session.commit()
    return attempt_view(a)
