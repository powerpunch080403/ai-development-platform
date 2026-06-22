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
    ApprovalStatus,
    ApprovalRequest,
)
from aidp_server.db.session import get_session
from aidp_server.git_utils import inspect_git_repository, run_git_write
from aidp_server.policy import evaluate_action, create_policy_decision
from aidp_server.approvals import (
    build_approval_fingerprint,
    create_approval_request,
    approve_request,
    reject_request,
    find_valid_approval_for_merge,
    mark_stale_if_fingerprint_changed,
)


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
    approval_status: str
    approval_request_id: str | None


class PrepareView(BaseModel):
    merge_possible: bool
    source_clean: bool
    base_head_matches: bool
    current_branch: str | None
    current_head: str | None
    approval_status: str
    policy_decision: str
    risk_level: str


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


def checks(repo: ProjectRepository, w: GitWorktree) -> tuple[bool, bool, bool, str | None, str | None]:
    s = inspect_git_repository(repo.repository_path)
    clean = s.is_git_repository and not s.error_code and not s.is_dirty
    matches = s.last_commit_sha == w.base_commit_sha and s.current_branch == w.base_branch
    merge_possible = bool(clean and matches and w.result_commit_sha)
    return merge_possible, bool(clean), matches, s.current_branch, s.last_commit_sha


def get_current_approval(session: Session, attempt_id: str, fingerprint: str) -> ApprovalRequest | None:
    reqs = session.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.task_attempt_id == attempt_id,
            ApprovalRequest.action_type == "merge.perform_squash"
        ).order_by(ApprovalRequest.created_at.desc())
    ).all()
    if not reqs:
        return None
    req = reqs[0]
    if req.approval_fingerprint != fingerprint and req.status in (ApprovalStatus.PENDING, ApprovalStatus.APPROVED):
        req.status = ApprovalStatus.STALE
        req.stale_at = datetime.now(timezone.utc)
        session.commit()
    return req


def detail(
    session: Session, current: CurrentAuth, a: TaskAttempt, task: Task, w: GitWorktree, repo: ProjectRepository
) -> ReviewView:
    merge_possible, source_clean, base_head_matches, current_branch, current_head = checks(repo, w)
    r = session.scalar(
        select(MergeReview).where(MergeReview.task_attempt_id == a.id).order_by(MergeReview.created_at.desc())
    )
    
    fp = build_approval_fingerprint(
        "merge.perform_squash", current.user.id, a.project_id, w.repository_id,
        a.task_id, a.id, w.id, w.base_branch, current_head or w.base_commit_sha,
        w.branch_name, w.result_commit_sha, "R3"
    )
    ar = get_current_approval(session, a.id, fp)
    app_status = ar.status.value if ar else ApprovalStatus.PENDING.value
    
    d = (
        git(Path(repo.repository_path), "diff", f"{w.base_commit_sha}..{w.result_commit_sha}", "--binary")
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
        source_clean=source_clean,
        base_head_matches=base_head_matches,
        merge_possible=merge_possible,
        approval_status=app_status,
        approval_request_id=ar.id if ar else None,
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
            out.append(detail(session, current, *x))
        except HTTPException:
            continue
    return out


@router.get("/task-attempts/{aid}/review", response_model=ReviewView)
def get_review(
    aid: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> ReviewView:
    return detail(session, current, *bundle(session, aid, current.user.id))


@router.post("/task-attempts/{aid}/review/approve", response_model=ReviewView)
def approve(
    aid: str,
    request: SummaryRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ReviewView:
    a, t, w, repo = bundle(session, aid, current.user.id)
    ensure_committed(a, w)
    r = session.scalar(select(MergeReview).where(MergeReview.task_attempt_id == a.id).order_by(MergeReview.created_at.desc()))
    r = r or new_review(session, current, a, w, MergeReviewStatus.CREATED, None)
    
    r.status = MergeReviewStatus.APPROVED
    r.review_summary = request.review_summary
    r.approved_at = datetime.now(timezone.utc)
    r.approved_by_session_id = current.runtime_session.id
    
    fp = build_approval_fingerprint(
        "merge.perform_squash", current.user.id, a.project_id, w.repository_id,
        a.task_id, a.id, w.id, w.base_branch, w.base_commit_sha,
        w.branch_name, w.result_commit_sha, "R3"
    )
    
    ar = get_current_approval(session, a.id, fp)
    if not ar or ar.status != ApprovalStatus.PENDING:
        ar = create_approval_request(
            session=session,
            local_user_id=current.user.id,
            action_type="merge.perform_squash",
            risk_level="R3",
            title=f"Approve squash merge for {t.title}",
            approval_fingerprint=fp,
            project_id=a.project_id,
            repository_id=w.repository_id,
            task_id=a.task_id,
            task_attempt_id=a.id,
            git_worktree_id=w.id,
            merge_review_id=r.id,
            requested_by_session_id=current.runtime_session.id,
        )
    
    approve_request(session, ar, current.runtime_session.id)
    
    create_policy_decision(
        session=session,
        local_user_id=current.user.id,
        action_type="review.approve",
        session_id=current.runtime_session.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        task_id=a.task_id,
        task_attempt_id=a.id,
        approval_request_id=ar.id,
    )
    
    record_audit_event(
        session,
        event_type="review.approved",
        message="Attempt approved for squash merge",
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        agent_run_id=None,
        metadata={"attempt_id": a.id, "review_id": r.id, "approval_request_id": ar.id},
    )
    session.commit()
    return detail(session, current, a, t, w, repo)


@router.post("/task-attempts/{aid}/review/reject", response_model=ReviewView)
def reject(
    aid: str,
    request: SummaryRequest,
    current: CurrentAuth,
    session: Annotated[Session, Depends(get_session)],
) -> ReviewView:
    a, t, w, repo = bundle(session, aid, current.user.id)
    ensure_committed(a, w)
    r = session.scalar(select(MergeReview).where(MergeReview.task_attempt_id == a.id).order_by(MergeReview.created_at.desc()))
    r = r or new_review(session, current, a, w, MergeReviewStatus.CREATED, None)
    
    r.status = MergeReviewStatus.REJECTED
    r.review_summary = request.review_summary
    r.rejected_at = datetime.now(timezone.utc)
    a.status = TaskAttemptStatus.REJECTED
    t.status = TaskStatus.CHANGES_REQUESTED
    w.status = GitWorktreeStatus.REVIEWING
    
    reqs = session.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.task_attempt_id == a.id,
            ApprovalRequest.status.in_([ApprovalStatus.PENDING, ApprovalStatus.APPROVED]),
        )
    ).all()
    for ar in reqs:
        reject_request(session, ar, current.runtime_session.id)
        
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
    return detail(session, current, a, t, w, repo)


@router.post("/task-attempts/{aid}/merge/prepare", response_model=PrepareView)
def prepare(
    aid: str, current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> PrepareView:
    a, t, w, repo = bundle(session, aid, current.user.id)
    ensure_committed(a, w)
    merge_possible, source_clean, base_head_matches, current_branch, current_head = checks(repo, w)
    
    decision, risk_level = evaluate_action("merge.perform_squash")
    
    fp = build_approval_fingerprint(
        "merge.perform_squash", current.user.id, a.project_id, w.repository_id,
        a.task_id, a.id, w.id, w.base_branch, current_head or w.base_commit_sha,
        w.branch_name, w.result_commit_sha, "R3"
    )
    ar = get_current_approval(session, a.id, fp)
    app_status = ar.status.value if ar else ApprovalStatus.PENDING.value
    
    if not source_clean:
        raise HTTPException(status_code=409, detail="Source repository is dirty")
    if not base_head_matches:
        raise HTTPException(status_code=409, detail="Base commit is stale")
        
    record_audit_event(
        session,
        event_type="merge.prepared",
        message="Squash merge preconditions passed",
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        metadata={"attempt_id": a.id, "approval_status": app_status},
    )
    session.commit()
    
    return PrepareView(
        merge_possible=merge_possible,
        source_clean=source_clean,
        base_head_matches=base_head_matches,
        current_branch=current_branch,
        current_head=current_head,
        approval_status=app_status,
        policy_decision=decision.value,
        risk_level=risk_level.value,
    )


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
    r = session.scalar(select(MergeReview).where(MergeReview.task_attempt_id == a.id).order_by(MergeReview.created_at.desc()))
    if not r or r.status not in {MergeReviewStatus.APPROVED, MergeReviewStatus.MERGE_PREPARED}:
        raise HTTPException(status_code=409, detail="Explicit approval is required")
        
    merge_possible, source_clean, base_head_matches, current_branch, current_head = checks(repo, w)
        
    decision, risk_level = evaluate_action("merge.perform_squash")
    
    fp = build_approval_fingerprint(
        "merge.perform_squash", current.user.id, a.project_id, w.repository_id,
        a.task_id, a.id, w.id, w.base_branch, current_head or w.base_commit_sha,
        w.branch_name, w.result_commit_sha, "R3"
    )
    
    ar = find_valid_approval_for_merge(session, fp)
    if not ar:
        mark_stale_if_fingerprint_changed(session, a.id, fp)
        session.commit()
        raise HTTPException(status_code=409, detail="Valid approval request not found or stale")
        
    if not source_clean:
        raise HTTPException(status_code=409, detail="Source repository is dirty")
    if not base_head_matches:
        raise HTTPException(status_code=409, detail="Base commit is stale")
        
    create_policy_decision(
        session=session,
        local_user_id=current.user.id,
        action_type="merge.perform_squash",
        session_id=current.runtime_session.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        task_id=a.task_id,
        task_attempt_id=a.id,
    )
        
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
    w.status = GitWorktreeStatus.CLEANUP_PENDING
    
    record_audit_event(
        session,
        event_type="merge.squash_completed",
        message="Squash merge completed",
        local_user_id=current.user.id,
        project_id=a.project_id,
        repository_id=w.repository_id,
        metadata={"attempt_id": a.id, "merge_commit": sha, "approval_request_id": ar.id},
    )
    session.commit()
    return detail(session, current, a, t, w, repo)

