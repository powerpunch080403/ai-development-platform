import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from aidp_server.db.models import ApprovalRequest, ApprovalStatus
from sqlalchemy import select
from sqlalchemy.orm import Session


def build_approval_fingerprint(
    action_type: str,
    local_user_id: str,
    project_id: str | None,
    repository_id: str | None,
    task_id: str | None,
    task_attempt_id: str | None,
    git_worktree_id: str | None,
    base_branch: str | None,
    base_commit_sha: str | None,
    result_branch: str | None,
    result_commit_sha: str | None,
    risk_level: str,
) -> str:
    payload = {
        "action_type": action_type,
        "local_user_id": local_user_id,
        "project_id": project_id,
        "repository_id": repository_id,
        "task_id": task_id,
        "task_attempt_id": task_attempt_id,
        "git_worktree_id": git_worktree_id,
        "base_branch": base_branch,
        "base_commit_sha": base_commit_sha,
        "result_branch": result_branch,
        "result_commit_sha": result_commit_sha,
        "risk_level": risk_level,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_approval_request(
    session: Session,
    local_user_id: str,
    action_type: str,
    risk_level: str,
    title: str,
    approval_fingerprint: str,
    project_id: str | None = None,
    repository_id: str | None = None,
    conversation_id: str | None = None,
    agent_run_id: str | None = None,
    tool_call_id: str | None = None,
    task_id: str | None = None,
    task_attempt_id: str | None = None,
    git_worktree_id: str | None = None,
    merge_review_id: str | None = None,
    description: str | None = None,
    scope_json: dict[str, Any] | None = None,
    arguments_json: dict[str, Any] | None = None,
    requested_by_session_id: str | None = None,
) -> ApprovalRequest:
    req = ApprovalRequest(
        local_user_id=local_user_id,
        project_id=project_id,
        repository_id=repository_id,
        conversation_id=conversation_id,
        agent_run_id=agent_run_id,
        tool_call_id=tool_call_id,
        task_id=task_id,
        task_attempt_id=task_attempt_id,
        git_worktree_id=git_worktree_id,
        merge_review_id=merge_review_id,
        action_type=action_type,
        risk_level=risk_level,
        status=ApprovalStatus.PENDING,
        title=title,
        description=description,
        scope_json=scope_json,
        arguments_json=arguments_json,
        approval_fingerprint=approval_fingerprint,
        requested_by_session_id=requested_by_session_id,
    )
    session.add(req)
    return req


def find_valid_approval_for_merge(session: Session, fingerprint: str) -> ApprovalRequest | None:
    return session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.approval_fingerprint == fingerprint,
            ApprovalRequest.status == ApprovalStatus.APPROVED,
        ).order_by(ApprovalRequest.created_at.desc())
    )


def approve_request(
    session: Session, req: ApprovalRequest, decided_by_session_id: str
) -> ApprovalRequest:
    req.status = ApprovalStatus.APPROVED
    req.decided_by_session_id = decided_by_session_id
    req.approved_at = datetime.now(timezone.utc)
    req.decided_at = req.approved_at
    return req


def reject_request(
    session: Session, req: ApprovalRequest, decided_by_session_id: str
) -> ApprovalRequest:
    req.status = ApprovalStatus.REJECTED
    req.decided_by_session_id = decided_by_session_id
    req.rejected_at = datetime.now(timezone.utc)
    req.decided_at = req.rejected_at
    return req


def mark_stale_if_fingerprint_changed(
    session: Session, attempt_id: str, current_fingerprint: str
) -> None:
    reqs = session.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.task_attempt_id == attempt_id,
            ApprovalRequest.status.in_([ApprovalStatus.PENDING, ApprovalStatus.APPROVED]),
        )
    ).all()
    for r in reqs:
        if r.approval_fingerprint != current_fingerprint:
            r.status = ApprovalStatus.STALE
            r.stale_at = datetime.now(timezone.utc)
