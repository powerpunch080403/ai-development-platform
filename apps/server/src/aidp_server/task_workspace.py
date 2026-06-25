from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.auth import CurrentAuth
from aidp_server.attempt_retry_policy import (
    EXPLICIT_RETRY_SOURCE_STATUSES,
    RETRY_BLOCKING_ATTEMPT_STATUSES,
)
from aidp_server.db.models import (
    ArtifactRef,
    GitWorktree,
    ProcessRun,
    RecordStatus,
    Task,
    TaskAttempt,
    TaskAttemptStatus,
    WorkerRun,
)
from aidp_server.db.session import get_session
from aidp_server.work_room import (
    TaskWorkRoomMessage,
    WorkRoomMessageView,
    work_room_message_view,
)
from aidp_server.write_scope import normalize_write_scope

router = APIRouter(tags=["task workspace"])


class WorkspaceTaskView(BaseModel):
    id: str
    project_id: str
    repository_id: str | None
    work_item_id: str | None
    conversation_id: str | None
    agent_run_id: str | None
    title: str
    instructions: str
    write_scope: dict[str, object]
    status: str
    risk_level: str
    requested_worker_kind: str | None
    created_at: datetime
    updated_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    error_code: str | None
    error_message: str | None


class WorkspaceAttemptView(BaseModel):
    id: str
    task_id: str
    project_id: str
    repository_id: str | None
    worker_id: str | None
    claimed_by_worker_id: str | None
    status: str
    attempt_number: int
    lease_expires_at: datetime | None
    claimed_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    failed_at: datetime | None
    error_code: str | None
    error_message: str | None
    result_summary: str | None
    created_at: datetime
    updated_at: datetime


class WorkspaceWorkerRunView(BaseModel):
    id: str
    project_id: str
    repository_id: str | None
    task_id: str
    task_attempt_id: str
    worker_id: str
    adapter_kind: str
    status: str
    last_heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    heartbeat_source: str | None
    lease_expired: bool
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None
    summary: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class WorkspaceProcessRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    repository_id: str | None
    task_id: str | None
    task_attempt_id: str | None
    worker_id: str | None
    worker_run_id: str | None
    tool_call_id: str | None
    command_display: str
    executable: str
    arguments_json: dict[str, object]
    working_directory: str
    status: str
    exit_code: int | None
    timeout_seconds: int
    started_at: datetime | None
    completed_at: datetime | None
    timed_out_at: datetime | None
    cancelled_at: datetime | None
    failed_at: datetime | None
    duration_ms: int | None
    stdout_artifact_id: str | None
    stderr_artifact_id: str | None
    combined_log_artifact_id: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class WorkspaceArtifactView(BaseModel):
    id: str
    owner_type: str
    owner_id: str
    project_id: str | None
    repository_id: str | None
    task_id: str | None
    task_attempt_id: str | None
    worker_id: str | None
    tool_call_id: str | None
    kind: str
    storage_path: str
    content_type: str
    size_bytes: int
    checksum: str
    retention_policy: str | None
    created_at: datetime


class WorkspaceWorktreeView(BaseModel):
    id: str
    project_id: str
    repository_id: str
    task_id: str
    task_attempt_id: str
    worker_id: str | None
    worktree_path: str
    branch_name: str
    base_branch: str | None
    base_commit_sha: str | None
    result_commit_sha: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    prepared_at: datetime | None
    committed_at: datetime | None
    cleanup_at: datetime | None
    failed_at: datetime | None
    error_code: str | None
    error_message: str | None


class WorkspaceAttemptBundleView(BaseModel):
    attempt: WorkspaceAttemptView
    worker_runs: list[WorkspaceWorkerRunView]
    process_runs: list[WorkspaceProcessRunView]
    artifacts: list[WorkspaceArtifactView]
    worktree: WorkspaceWorktreeView | None


class WorkspaceOperationsSummaryView(BaseModel):
    active_attempt_count: int
    active_worker_run_count: int
    stale_worker_run_count: int
    attention_count: int
    follow_up_available: bool
    follow_up_source_attempt_id: str | None
    follow_up_blocked_by_attempt_id: str | None
    follow_up_blocked_by_status: str | None
    latest_worker_run_id: str | None
    latest_worker_run_status: str | None
    latest_worker_run_lease_expired: bool


class TaskWorkspaceView(BaseModel):
    task: WorkspaceTaskView
    attempts: list[WorkspaceAttemptBundleView]
    operations_summary: WorkspaceOperationsSummaryView
    work_room_messages: list[WorkRoomMessageView]


def task_view(task: Task) -> WorkspaceTaskView:
    return WorkspaceTaskView(
        id=task.id,
        project_id=task.project_id,
        repository_id=task.repository_id,
        work_item_id=task.work_item_id,
        conversation_id=task.conversation_id,
        agent_run_id=task.agent_run_id,
        title=task.title,
        instructions=task.instructions,
        write_scope=normalize_write_scope(task.write_scope_json),
        status=task.status.value,
        risk_level=task.risk_level.value,
        requested_worker_kind=task.requested_worker_kind.value
        if task.requested_worker_kind
        else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
        queued_at=task.queued_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        failed_at=task.failed_at,
        error_code=task.error_code,
        error_message=task.error_message,
    )


def attempt_view(attempt: TaskAttempt) -> WorkspaceAttemptView:
    return WorkspaceAttemptView(
        id=attempt.id,
        task_id=attempt.task_id,
        project_id=attempt.project_id,
        repository_id=attempt.repository_id,
        worker_id=attempt.worker_id,
        claimed_by_worker_id=attempt.claimed_by_worker_id,
        status=attempt.status.value,
        attempt_number=attempt.attempt_number,
        lease_expires_at=attempt.lease_expires_at,
        claimed_at=attempt.claimed_at,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        cancelled_at=attempt.cancelled_at,
        failed_at=attempt.failed_at,
        error_code=attempt.error_code,
        error_message=attempt.error_message,
        result_summary=attempt.result_summary,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
    )


def as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def worker_run_lease_expired(run: WorkerRun, *, now: datetime) -> bool:
    return (
        run.status == RecordStatus.RUNNING
        and run.lease_expires_at is not None
        and as_utc(run.lease_expires_at) <= now
    )


def worker_run_view(run: WorkerRun, *, now: datetime | None = None) -> WorkspaceWorkerRunView:
    effective_now = now or datetime.now(timezone.utc)
    return WorkspaceWorkerRunView(
        id=run.id,
        project_id=run.project_id,
        repository_id=run.repository_id,
        task_id=run.task_id,
        task_attempt_id=run.task_attempt_id,
        worker_id=run.worker_id,
        adapter_kind=run.adapter_kind,
        status=run.status.value,
        last_heartbeat_at=run.last_heartbeat_at,
        lease_expires_at=run.lease_expires_at,
        heartbeat_source=run.heartbeat_source,
        lease_expired=worker_run_lease_expired(run, now=effective_now),
        started_at=run.started_at,
        completed_at=run.completed_at,
        failed_at=run.failed_at,
        cancelled_at=run.cancelled_at,
        summary=run.summary,
        error_code=run.error_code,
        error_message=run.error_message,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def process_run_view(run: ProcessRun) -> WorkspaceProcessRunView:
    return WorkspaceProcessRunView.model_validate(run)


def operations_summary_view(
    *,
    attempts: list[TaskAttempt],
    worker_runs: list[WorkerRun],
    now: datetime,
) -> WorkspaceOperationsSummaryView:
    active_attempts = [
        attempt for attempt in attempts if attempt.status in RETRY_BLOCKING_ATTEMPT_STATUSES
    ]
    active_worker_runs = [
        run for run in worker_runs if run.status in {RecordStatus.QUEUED, RecordStatus.RUNNING}
    ]
    stale_worker_runs = [
        run for run in worker_runs if worker_run_lease_expired(run, now=now)
    ]
    attention_attempts = [
        attempt
        for attempt in attempts
        if attempt.status in {TaskAttemptStatus.WORKER_FAILED, TaskAttemptStatus.FAILED}
    ]

    source_attempt = next(
        (
            attempt
            for attempt in sorted(attempts, key=lambda item: item.attempt_number, reverse=True)
            if attempt.status in EXPLICIT_RETRY_SOURCE_STATUSES
        ),
        None,
    )
    blocking_attempt = next(
        (
            attempt
            for attempt in sorted(attempts, key=lambda item: item.attempt_number)
            if source_attempt is not None
            and attempt.id != source_attempt.id
            and attempt.status in RETRY_BLOCKING_ATTEMPT_STATUSES
        ),
        None,
    )
    latest_worker_run = next(
        iter(sorted(worker_runs, key=lambda item: item.updated_at, reverse=True)),
        None,
    )

    return WorkspaceOperationsSummaryView(
        active_attempt_count=len(active_attempts),
        active_worker_run_count=len(active_worker_runs),
        stale_worker_run_count=len(stale_worker_runs),
        attention_count=len(attention_attempts) + len(stale_worker_runs),
        follow_up_available=source_attempt is not None and blocking_attempt is None,
        follow_up_source_attempt_id=source_attempt.id if source_attempt is not None else None,
        follow_up_blocked_by_attempt_id=blocking_attempt.id if blocking_attempt is not None else None,
        follow_up_blocked_by_status=blocking_attempt.status.value
        if blocking_attempt is not None
        else None,
        latest_worker_run_id=latest_worker_run.id if latest_worker_run is not None else None,
        latest_worker_run_status=latest_worker_run.status.value
        if latest_worker_run is not None
        else None,
        latest_worker_run_lease_expired=worker_run_lease_expired(latest_worker_run, now=now)
        if latest_worker_run is not None
        else False,
    )


def artifact_view(artifact: ArtifactRef) -> WorkspaceArtifactView:
    return WorkspaceArtifactView(
        id=artifact.id,
        owner_type=artifact.owner_type,
        owner_id=artifact.owner_id,
        project_id=artifact.project_id,
        repository_id=artifact.repository_id,
        task_id=artifact.task_id,
        task_attempt_id=artifact.task_attempt_id,
        worker_id=artifact.worker_id,
        tool_call_id=artifact.tool_call_id,
        kind=artifact.kind.value,
        storage_path=artifact.storage_path,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        checksum=artifact.checksum,
        retention_policy=artifact.retention_policy,
        created_at=artifact.created_at,
    )


def worktree_view(worktree: GitWorktree) -> WorkspaceWorktreeView:
    return WorkspaceWorktreeView(
        id=worktree.id,
        project_id=worktree.project_id,
        repository_id=worktree.repository_id,
        task_id=worktree.task_id,
        task_attempt_id=worktree.task_attempt_id,
        worker_id=worktree.worker_id,
        worktree_path=worktree.worktree_path,
        branch_name=worktree.branch_name,
        base_branch=worktree.base_branch,
        base_commit_sha=worktree.base_commit_sha,
        result_commit_sha=worktree.result_commit_sha,
        status=worktree.status.value,
        created_at=worktree.created_at,
        updated_at=worktree.updated_at,
        prepared_at=worktree.prepared_at,
        committed_at=worktree.committed_at,
        cleanup_at=worktree.cleanup_at,
        failed_at=worktree.failed_at,
        error_code=worktree.error_code,
        error_message=worktree.error_message,
    )


@router.get("/tasks/{task_id}/workspace", response_model=TaskWorkspaceView)
def get_task_workspace(
    task_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> TaskWorkspaceView:
    task = session.get(Task, task_id)
    if task is None or task.local_user_id != current.user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    attempts = session.scalars(
        select(TaskAttempt).where(TaskAttempt.task_id == task.id).order_by(TaskAttempt.attempt_number)
    ).all()
    attempt_ids = [attempt.id for attempt in attempts]

    worker_runs_by_attempt: dict[str, list[WorkerRun]] = {attempt.id: [] for attempt in attempts}
    process_runs_by_attempt: dict[str, list[ProcessRun]] = {attempt.id: [] for attempt in attempts}
    artifacts_by_attempt: dict[str, list[ArtifactRef]] = {attempt.id: [] for attempt in attempts}
    worktrees_by_attempt: dict[str, GitWorktree] = {}

    all_worker_runs: list[WorkerRun] = []

    if attempt_ids:
        worker_runs = session.scalars(
            select(WorkerRun)
            .where(WorkerRun.task_attempt_id.in_(attempt_ids))
            .order_by(WorkerRun.created_at.asc())
        ).all()
        all_worker_runs = list(worker_runs)
        for run in worker_runs:
            worker_runs_by_attempt.setdefault(run.task_attempt_id, []).append(run)

        process_runs = session.scalars(
            select(ProcessRun)
            .where(ProcessRun.task_attempt_id.in_(attempt_ids))
            .order_by(ProcessRun.created_at.asc())
        ).all()
        for run in process_runs:
            if run.task_attempt_id:
                process_runs_by_attempt.setdefault(run.task_attempt_id, []).append(run)

        artifacts = session.scalars(
            select(ArtifactRef)
            .where(ArtifactRef.task_attempt_id.in_(attempt_ids))
            .order_by(ArtifactRef.created_at.asc())
        ).all()
        for artifact in artifacts:
            if artifact.task_attempt_id:
                artifacts_by_attempt.setdefault(artifact.task_attempt_id, []).append(artifact)

        worktrees = session.scalars(
            select(GitWorktree).where(GitWorktree.task_attempt_id.in_(attempt_ids))
        ).all()
        worktrees_by_attempt = {worktree.task_attempt_id: worktree for worktree in worktrees}

    work_room_messages = session.scalars(
        select(TaskWorkRoomMessage)
        .where(TaskWorkRoomMessage.task_id == task.id)
        .order_by(TaskWorkRoomMessage.created_at.asc(), TaskWorkRoomMessage.id.asc())
    ).all()

    now = datetime.now(timezone.utc)

    return TaskWorkspaceView(
        task=task_view(task),
        attempts=[
            WorkspaceAttemptBundleView(
                attempt=attempt_view(attempt),
                worker_runs=[
                    worker_run_view(run, now=now) for run in worker_runs_by_attempt[attempt.id]
                ],
                process_runs=[process_run_view(run) for run in process_runs_by_attempt[attempt.id]],
                artifacts=[artifact_view(artifact) for artifact in artifacts_by_attempt[attempt.id]],
                worktree=worktree_view(worktrees_by_attempt[attempt.id])
                if attempt.id in worktrees_by_attempt
                else None,
            )
            for attempt in attempts
        ],
        operations_summary=operations_summary_view(
            attempts=list(attempts),
            worker_runs=all_worker_runs,
            now=now,
        ),
        work_room_messages=[work_room_message_view(message) for message in work_room_messages],
    )
