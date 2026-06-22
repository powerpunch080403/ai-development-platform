from typing import Any
from aidp_server.db.models import PolicyDecision, PolicyDecisionResult, RiskLevel
from sqlalchemy.orm import Session
from datetime import datetime, timezone


def evaluate_action(action_type: str) -> tuple[PolicyDecisionResult, RiskLevel]:
    """
    MVP Baseline Policy Evaluator
    """
    if action_type == "merge.perform_squash":
        return PolicyDecisionResult.APPROVAL_REQUIRED, RiskLevel.R3
    elif action_type in ("worktree.commit_result", "worker.run_mock", "worker.run_manual"):
        return PolicyDecisionResult.ALLOW, RiskLevel.R1
    elif action_type == "review.approve":
        return PolicyDecisionResult.ALLOW, RiskLevel.R2
    
    # Anything else defaults to deny (R4) for safety in this MVP slice
    return PolicyDecisionResult.DENY, RiskLevel.R4


def create_policy_decision(
    session: Session,
    local_user_id: str,
    action_type: str,
    context: dict[str, Any] | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    repository_id: str | None = None,
    task_id: str | None = None,
    task_attempt_id: str | None = None,
    tool_call_id: str | None = None,
    approval_request_id: str | None = None,
) -> PolicyDecision:
    decision, risk_level = evaluate_action(action_type)
    
    reason = f"MVP Baseline rule for {action_type}"
    if decision == PolicyDecisionResult.DENY:
        reason = f"Action {action_type} is not explicitly allowed in MVP Baseline."
    
    pd = PolicyDecision(
        local_user_id=local_user_id,
        session_id=session_id,
        project_id=project_id,
        repository_id=repository_id,
        task_id=task_id,
        task_attempt_id=task_attempt_id,
        tool_call_id=tool_call_id,
        approval_request_id=approval_request_id,
        action_type=action_type,
        risk_level=risk_level.value,
        decision=decision,
        reason=reason,
        context_json=context,
    )
    session.add(pd)
    return pd
