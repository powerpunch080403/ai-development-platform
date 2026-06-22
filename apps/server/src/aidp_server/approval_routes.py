from typing import Annotated
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime

from aidp_server.auth import CurrentAuth
from aidp_server.db.session import get_session
from aidp_server.db.models import ApprovalRequest, PolicyDecision


router = APIRouter(tags=["approvals and policies"])


class ApprovalRequestView(BaseModel):
    id: str
    local_user_id: str
    project_id: str | None
    repository_id: str | None
    task_attempt_id: str | None
    action_type: str
    risk_level: str
    status: str
    title: str
    description: str | None
    created_at: datetime
    decided_at: datetime | None


class PolicyDecisionView(BaseModel):
    id: str
    local_user_id: str | None
    action_type: str
    risk_level: str
    decision: str
    reason: str
    created_at: datetime


@router.get("/approval-requests", response_model=list[ApprovalRequestView])
def list_approval_requests(
    current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[ApprovalRequestView]:
    items = session.scalars(
        select(ApprovalRequest)
        .where(ApprovalRequest.local_user_id == current.user.id)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(100)
    ).all()
    return [
        ApprovalRequestView(
            id=i.id,
            local_user_id=i.local_user_id,
            project_id=i.project_id,
            repository_id=i.repository_id,
            task_attempt_id=i.task_attempt_id,
            action_type=i.action_type,
            risk_level=i.risk_level,
            status=i.status.value,
            title=i.title,
            description=i.description,
            created_at=i.created_at,
            decided_at=i.decided_at,
        )
        for i in items
    ]


@router.get("/policy-decisions", response_model=list[PolicyDecisionView])
def list_policy_decisions(
    current: CurrentAuth, session: Annotated[Session, Depends(get_session)]
) -> list[PolicyDecisionView]:
    items = session.scalars(
        select(PolicyDecision)
        .where(PolicyDecision.local_user_id == current.user.id)
        .order_by(PolicyDecision.created_at.desc())
        .limit(100)
    ).all()
    return [
        PolicyDecisionView(
            id=i.id,
            local_user_id=i.local_user_id,
            action_type=i.action_type,
            risk_level=i.risk_level,
            decision=i.decision.value,
            reason=i.reason,
            created_at=i.created_at,
        )
        for i in items
    ]
