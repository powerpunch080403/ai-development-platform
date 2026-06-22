from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from aidp_server.artifacts import create_text_artifact, read_text_artifact
from aidp_server.audit import record_audit_event
from aidp_server.auth import CurrentAuth
from aidp_server.config import Settings, ensure_runtime_dirs, get_settings
from aidp_server.db.models import (
    ArtifactKind,
    ArtifactRef,
    GitWorktree,
    GitWorktreeStatus,
    ProjectRepository,
    Task,
    TaskAttempt,
    TaskAttemptStatus,
    TaskStatus,
)
from aidp_server.db.session import get_session
from aidp_server.git_utils import inspect_git_repository, run_git_write


class WorktreeView(BaseModel):
    id: str
    task_attempt_id: str
    worktree_path: str
    branch_name: str
    base_branch: str | None
    base_commit_sha: str | None
    result_commit_sha: str | None
    status: str


class StatusView(BaseModel):
    is_dirty: bool
    porcelain: str
    status: str


class DiffView(BaseModel):
    diff: str
    truncated: bool


class CommitRequest(BaseModel):
    commit_message: str = Field(min_length=1, max_length=300)


class ArtifactView(BaseModel):
    id: str
    kind: str
    storage_path: str
    content_type: str
    size_bytes: int
    checksum: str
    created_at: datetime


class ArtifactTextView(BaseModel):
    id: str
    text: str


router = APIRouter(tags=["worktrees and artifacts"])
MAX_DIFF = 1_000_000


def owned(session: Session, model: type, oid: str, uid: str) -> Any:
    v = session.get(model, oid)
    if v is None or getattr(v, "local_user_id", None) != uid:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return v


def view(v: GitWorktree) -> WorktreeView:
    return WorktreeView(
        id=v.id,
        task_attempt_id=v.task_attempt_id,
        worktree_path=v.worktree_path,
        branch_name=v.branch_name,
        base_branch=v.base_branch,
        base_commit_sha=v.base_commit_sha,
        result_commit_sha=v.result_commit_sha,
        status=v.status.value,
    )


def av(v: ArtifactRef) -> ArtifactView:
    return ArtifactView(
        id=v.id,
        kind=v.kind.value,
        storage_path=v.storage_path,
        content_type=v.content_type,
        size_bytes=v.size_bytes,
        checksum=v.checksum,
        created_at=v.created_at,
    )


def command(path: Path, *args: str) -> str:
    r = run_git_write(path, *args)
    if r.returncode:
        raise HTTPException(status_code=422, detail=r.stderr.strip() or "Git command failed")
    return r.stdout


@router.post("/task-attempts/{attempt_id}/worktree", response_model=WorktreeView, status_code=201)
def create_worktree(
    attempt_id: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorktreeView:
    a = owned(session, TaskAttempt, attempt_id, current.user.id)
    if not a.claimed_by_worker_id:
        raise HTTPException(status_code=409, detail="Attempt must be claimed")
    if session.scalar(select(GitWorktree).where(GitWorktree.task_attempt_id == a.id)):
        raise HTTPException(status_code=409, detail="Attempt already has a worktree")
    task = session.get(Task, a.task_id)
    repo = session.get(ProjectRepository, a.repository_id) if a.repository_id else None
    if not task or not repo:
        raise HTTPException(status_code=409, detail="Task repository is required")
    status = inspect_git_repository(repo.repository_path)
    if not status.is_git_repository or status.error_code:
        raise HTTPException(status_code=422, detail=status.error_message)
    if status.is_dirty:
        raise HTTPException(status_code=409, detail="Repository is dirty")
    worktrees, _ = ensure_runtime_dirs(settings)
    path = (worktrees / a.project_id[:8] / repo.id[:8] / a.id[:12]).resolve()
    if worktrees not in path.parents or path.exists():
        raise HTTPException(status_code=409, detail="Worktree path already exists")
    base = status.last_commit_sha
    if not base:
        raise HTTPException(status_code=409, detail="Repository has no commit")
    stem = f"aidp/task-{task.id[:8]}/attempt-{a.attempt_number}-{a.id[:8]}"
    branch = stem
    suffix = 1
    while (
        run_git_write(
            Path(repo.repository_path), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"
        ).returncode
        == 0
    ):
        suffix += 1
        branch = f"{stem}-{suffix}"
    wt = GitWorktree(
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=repo.id,
        task_id=task.id,
        task_attempt_id=a.id,
        worker_id=a.claimed_by_worker_id,
        worktree_path=str(path),
        branch_name=branch,
        base_branch=status.current_branch,
        base_commit_sha=base,
        status=GitWorktreeStatus.CREATING,
    )
    session.add(wt)
    session.flush()
    result = run_git_write(
        Path(repo.repository_path), "worktree", "add", "-b", branch, str(path), base
    )
    if result.returncode:
        wt.status = GitWorktreeStatus.FAILED
        wt.failed_at = datetime.now(timezone.utc)
        wt.error_message = result.stderr
        session.commit()
        raise HTTPException(status_code=422, detail=result.stderr.strip())
    wt.status = GitWorktreeStatus.READY
    wt.prepared_at = datetime.now(timezone.utc)
    a.status = TaskAttemptStatus.RUNNING_WORKER
    record_audit_event(
        session,
        event_type="worktree.created",
        message="Git worktree created",
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=repo.id,
        metadata={"worktree_id": wt.id, "branch": branch},
    )
    session.commit()
    return view(wt)


@router.get("/task-attempts/{attempt_id}/worktree", response_model=WorktreeView)
def attempt_worktree(
    attempt_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> WorktreeView:
    owned(session, TaskAttempt, attempt_id, current.user.id)
    v = session.scalar(select(GitWorktree).where(GitWorktree.task_attempt_id == attempt_id))
    if not v:
        raise HTTPException(status_code=404, detail="Worktree not found")
    return view(v)


@router.get("/worktrees/{wid}", response_model=WorktreeView)
def get_worktree(
    wid: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> WorktreeView:
    return view(owned(session, GitWorktree, wid, current.user.id))


@router.get("/worktrees/{wid}/status", response_model=StatusView)
def worktree_status(
    wid: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> StatusView:
    w = owned(session, GitWorktree, wid, current.user.id)
    porcelain = command(Path(w.worktree_path), "status", "--porcelain").rstrip()
    dirty = bool(porcelain)
    if dirty:
        w.status = GitWorktreeStatus.DIRTY_RESULT
    elif w.status is not GitWorktreeStatus.COMMITTED:
        w.status = GitWorktreeStatus.READY
    session.commit()
    return StatusView(is_dirty=dirty, porcelain=porcelain, status=w.status.value)


@router.get("/worktrees/{wid}/diff", response_model=DiffView)
def worktree_diff(
    wid: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> DiffView:
    w = owned(session, GitWorktree, wid, current.user.id)
    text = command(Path(w.worktree_path), "diff", "--binary", "HEAD")
    return DiffView(diff=text[:MAX_DIFF], truncated=len(text) > MAX_DIFF)


@router.post("/worktrees/{wid}/commit-result", response_model=WorktreeView)
def commit_result(
    wid: str,
    request: CommitRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorktreeView:
    w = owned(session, GitWorktree, wid, current.user.id)
    a = session.get(TaskAttempt, w.task_attempt_id)
    task = session.get(Task, w.task_id)
    if not a or not task or not a.claimed_by_worker_id:
        raise HTTPException(status_code=409, detail="Attempt is not claimed")
    path = Path(w.worktree_path)
    status_text = command(path, "status", "--porcelain").rstrip()
    if not status_text:
        raise HTTPException(status_code=409, detail="Worktree has no changes")
    command(path, "add", "-A")
    diff = command(path, "diff", "--cached", "--binary")
    create_text_artifact(
        session,
        settings,
        content=diff,
        kind=ArtifactKind.DIFF_PATCH,
        user_id=current.user.id,
        project_id=w.project_id,
        repository_id=w.repository_id,
        task_id=w.task_id,
        attempt_id=w.task_attempt_id,
        worker_id=w.worker_id,
    )
    create_text_artifact(
        session,
        settings,
        content=status_text,
        kind=ArtifactKind.GIT_STATUS,
        user_id=current.user.id,
        project_id=w.project_id,
        repository_id=w.repository_id,
        task_id=w.task_id,
        attempt_id=w.task_attempt_id,
        worker_id=w.worker_id,
    )
    command(path, "commit", "-m", request.commit_message)
    sha = command(path, "rev-parse", "HEAD").strip()
    log = command(path, "show", "--stat", "--oneline", "--no-renames", sha)
    create_text_artifact(
        session,
        settings,
        content=log,
        kind=ArtifactKind.COMMIT_LOG,
        user_id=current.user.id,
        project_id=w.project_id,
        repository_id=w.repository_id,
        task_id=w.task_id,
        attempt_id=w.task_attempt_id,
        worker_id=w.worker_id,
    )
    now = datetime.now(timezone.utc)
    w.result_commit_sha = sha
    w.status = GitWorktreeStatus.COMMITTED
    w.committed_at = now
    a.status = TaskAttemptStatus.COMMITTED
    a.completed_at = now
    task.status = TaskStatus.WAITING_FOR_REVIEW
    record_audit_event(
        session,
        event_type="worktree.result_committed",
        message="Manual worker result committed",
        local_user_id=current.user.id,
        project_id=w.project_id,
        repository_id=w.repository_id,
        metadata={"worktree_id": w.id, "commit": sha},
    )
    session.commit()
    return view(w)


@router.get("/task-attempts/{attempt_id}/artifacts", response_model=list[ArtifactView])
def artifacts(
    attempt_id: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[ArtifactView]:
    owned(session, TaskAttempt, attempt_id, current.user.id)
    return [
        av(v)
        for v in session.scalars(
            select(ArtifactRef)
            .where(ArtifactRef.task_attempt_id == attempt_id)
            .order_by(ArtifactRef.created_at)
        )
    ]


@router.get("/artifacts/{aid}", response_model=ArtifactView)
def artifact(
    aid: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> ArtifactView:
    return av(owned(session, ArtifactRef, aid, current.user.id))


@router.get("/artifacts/{aid}/text", response_model=ArtifactTextView)
def artifact_text(
    aid: str,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ArtifactTextView:
    v = owned(session, ArtifactRef, aid, current.user.id)
    try:
        text = read_text_artifact(v, settings)
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Artifact content not found") from None
    return ArtifactTextView(id=v.id, text=text)
