from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from aidp_server.artifacts import create_text_artifact
from aidp_server.audit import record_audit_event
from aidp_server.auth import CurrentAuth
from aidp_server.config import Settings, get_settings
from aidp_server.db.models import (
    ArtifactKind,
    GitWorktree,
    GitWorktreeStatus,
    MergeReview,
    MergeReviewStatus,
    ProjectRepository,
    Task,
    TaskAttempt,
    TaskAttemptStatus,
    TaskStatus,
)
from aidp_server.db.session import get_session
from aidp_server.git_utils import inspect_git_repository, run_git_write


class SummaryRequest(BaseModel):
    review_summary: str | None = Field(default=None, max_length=4000)


class SquashRequest(BaseModel):
    commit_message: str | None = Field(default=None, max_length=500)


class ReviewView(BaseModel):
    task_attempt_id: str
    task_id: str
    task_title: str
    repository_name: str
    worktree_id: str
    base_branch: str
    base_commit_sha: str
    result_branch: str
    result_commit_sha: str
    merge_commit_sha: str | None
    review_status: str
    diff: str
    source_clean: bool
    base_head_matches: bool
    merge_possible: bool


class PrepareView(BaseModel):
    merge_possible: bool
    source_clean: bool
    base_head_matches: bool
    current_branch: str | None
    current_head: str | None


router = APIRouter(tags=["owner review and squash merge"])
MAX_DIFF = 1_000_000


def owned(session: Session, model: type, oid: str, uid: str) -> Any:
    v = session.get(model, oid)
    if v is None or getattr(v, "local_user_id", None) != uid:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return v


def bundle(session: Session, aid: str, uid: str) -> tuple[Any, Any, Any, Any]:
    a = owned(session, TaskAttempt, aid, uid)
    task = session.get(Task, a.task_id)
    w = session.scalar(select(GitWorktree).where(GitWorktree.task_attempt_id == a.id))
    repo = session.get(ProjectRepository, a.repository_id) if a.repository_id else None
    if not task or not w or not repo:
        raise HTTPException(status_code=409, detail="Review records are incomplete")
    return a, task, w, repo


def git(path: Path, *args: str) -> str:
    r = run_git_write(path, *args)
    if r.returncode:
        raise HTTPException(status_code=422, detail=r.stderr.strip() or "Git command failed")
    return r.stdout


def checks(repo: ProjectRepository, w: GitWorktree) -> PrepareView:
    s = inspect_git_repository(repo.repository_path)
    clean = s.is_git_repository and not s.error_code and not s.is_dirty
    matches = s.last_commit_sha == w.base_commit_sha and s.current_branch == w.base_branch
    return PrepareView(
        merge_possible=bool(clean and matches and w.result_commit_sha),
        source_clean=bool(clean),
        base_head_matches=matches,
        current_branch=s.current_branch,
        current_head=s.last_commit_sha,
    )


def review_row(session: Session, a: TaskAttempt, w: GitWorktree) -> MergeReview | None:
    return session.scalar(
        select(MergeReview)
        .where(MergeReview.task_attempt_id == a.id)
        .order_by(MergeReview.created_at.desc())
    )


def detail(
    session: Session, a: TaskAttempt, task: Task, w: GitWorktree, repo: ProjectRepository
) -> ReviewView:
    c = checks(repo, w)
    r = review_row(session, a, w)
    d = (
        git(
            Path(repo.repository_path),
            "diff",
            f"{w.base_commit_sha}..{w.result_commit_sha}",
            "--binary",
        )
        if w.result_commit_sha
        else ""
    )
    return ReviewView(
        task_attempt_id=a.id,
        task_id=task.id,
        task_title=task.title,
        repository_name=repo.repository_name,
        worktree_id=w.id,
        base_branch=w.base_branch or "",
        base_commit_sha=w.base_commit_sha or "",
        result_branch=w.branch_name,
        result_commit_sha=w.result_commit_sha or "",
        merge_commit_sha=r.merge_commit_sha if r else None,
        review_status=r.status.value if r else "created",
        diff=d[:MAX_DIFF],
        source_clean=c.source_clean,
        base_head_matches=c.base_head_matches,
        merge_possible=c.merge_possible,
    )


def ensure_committed(a: TaskAttempt, w: GitWorktree) -> None:
    if (
        a.status is not TaskAttemptStatus.COMMITTED
        or w.status is not GitWorktreeStatus.COMMITTED
        or not w.result_commit_sha
    ):
        raise HTTPException(status_code=409, detail="Attempt is not committed")


def new_review(
    session: Session,
    current: Any,
    a: TaskAttempt,
    w: GitWorktree,
    status: MergeReviewStatus,
    summary: str | None,
) -> MergeReview:
    r = MergeReview(
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        task_id=a.task_id,
        task_attempt_id=a.id,
        git_worktree_id=w.id,
        status=status,
        review_summary=summary,
        base_branch=w.base_branch or "",
        base_commit_sha=w.base_commit_sha or "",
        result_branch=w.branch_name,
        result_commit_sha=w.result_commit_sha or "",
    )
    session.add(r)
    return r


@router.get("/reviews/merge-ready", response_model=list[ReviewView])
def ready(
    current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[ReviewView]:
    out = []
    for a in session.scalars(
        select(TaskAttempt).where(
            TaskAttempt.local_user_id == current.user.id,
            TaskAttempt.status == TaskAttemptStatus.COMMITTED,
        )
    ):
        try:
            x = bundle(session, a.id, current.user.id)
            out.append(detail(session, *x))
        except HTTPException:
            continue
    return out


@router.get("/task-attempts/{aid}/review", response_model=ReviewView)
def get_review(
    aid: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> ReviewView:
    return detail(session, *bundle(session, aid, current.user.id))


@router.post("/task-attempts/{aid}/review/approve", response_model=ReviewView)
def approve(
    aid: str,
    request: SummaryRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ReviewView:
    a, t, w, repo = bundle(session, aid, current.user.id)
    ensure_committed(a, w)
    r = review_row(session, a, w) or new_review(
        session, current, a, w, MergeReviewStatus.CREATED, None
    )
    r.status = MergeReviewStatus.APPROVED
    r.review_summary = request.review_summary
    r.approved_at = datetime.now(timezone.utc)
    r.approved_by_session_id = current.runtime_session.id
    record_audit_event(
        session,
        event_type="review.approved",
        message="Attempt approved for squash merge",
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        agent_run_id=None,
        metadata={"attempt_id": a.id, "review_id": r.id},
    )
    session.commit()
    return detail(session, a, t, w, repo)


@router.post("/task-attempts/{aid}/review/reject", response_model=ReviewView)
def reject(
    aid: str,
    request: SummaryRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ReviewView:
    a, t, w, repo = bundle(session, aid, current.user.id)
    ensure_committed(a, w)
    r = review_row(session, a, w) or new_review(
        session, current, a, w, MergeReviewStatus.CREATED, None
    )
    r.status = MergeReviewStatus.REJECTED
    r.review_summary = request.review_summary
    r.rejected_at = datetime.now(timezone.utc)
    a.status = TaskAttemptStatus.REJECTED
    t.status = TaskStatus.CHANGES_REQUESTED
    w.status = GitWorktreeStatus.REVIEWING
    record_audit_event(
        session,
        event_type="review.rejected",
        message="Attempt review rejected",
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        metadata={"attempt_id": a.id},
    )
    session.commit()
    return detail(session, a, t, w, repo)


@router.post("/task-attempts/{aid}/merge/prepare", response_model=PrepareView)
def prepare(
    aid: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> PrepareView:
    a, t, w, repo = bundle(session, aid, current.user.id)
    ensure_committed(a, w)
    c = checks(repo, w)
    if not c.source_clean:
        raise HTTPException(status_code=409, detail="Source repository is dirty")
    if not c.base_head_matches:
        raise HTTPException(status_code=409, detail="Base commit is stale")
    record_audit_event(
        session,
        event_type="merge.prepared",
        message="Squash merge preconditions passed",
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        metadata={"attempt_id": a.id},
    )
    session.commit()
    return c


@router.post("/task-attempts/{aid}/merge/squash", response_model=ReviewView)
def squash(
    aid: str,
    request: SquashRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReviewView:
    a, t, w, repo = bundle(session, aid, current.user.id)
    ensure_committed(a, w)
    r = review_row(session, a, w)
    if not r or r.status not in {MergeReviewStatus.APPROVED, MergeReviewStatus.MERGE_PREPARED}:
        raise HTTPException(status_code=409, detail="Explicit approval is required")
    c = checks(repo, w)
    if not c.source_clean:
        raise HTTPException(status_code=409, detail="Source repository is dirty")
    if not c.base_head_matches:
        raise HTTPException(status_code=409, detail="Base commit is stale")
    path = Path(repo.repository_path)
    message = (
        request.commit_message or f"{t.title}\n\nSquash merge result from task attempt {a.id}."
    )
    merge = run_git_write(path, "merge", "--squash", w.result_commit_sha or "")
    if merge.returncode:
        run_git_write(path, "reset", "--merge", w.base_commit_sha or "HEAD")
        r.status = MergeReviewStatus.FAILED
        r.failed_at = datetime.now(timezone.utc)
        r.error_message = merge.stderr
        session.commit()
        raise HTTPException(status_code=422, detail=merge.stderr.strip())
    commit = run_git_write(path, "commit", "-m", message)
    if commit.returncode:
        run_git_write(path, "reset", "--merge", w.base_commit_sha or "HEAD")
        raise HTTPException(status_code=422, detail=commit.stderr.strip())
    sha = git(path, "rev-parse", "HEAD").strip()
    log = git(path, "show", "--stat", "--oneline", sha)
    create_text_artifact(
        session,
        settings,
        content=log,
        kind=ArtifactKind.GENERATED_REPORT,
        user_id=current.user.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        task_id=t.id,
        attempt_id=a.id,
        worker_id=w.worker_id,
    )
    now = datetime.now(timezone.utc)
    r.status = MergeReviewStatus.MERGED
    r.merge_commit_sha = sha
    r.merged_at = now
    a.status = TaskAttemptStatus.MERGED
    t.status = TaskStatus.COMPLETED
    w.status = GitWorktreeStatus.MERGED
    record_audit_event(
        session,
        event_type="merge.squash_completed",
        message="Squash merge completed",
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        metadata={"attempt_id": a.id, "merge_commit": sha},
    )
    session.commit()
    return detail(session, a, t, w, repo)
