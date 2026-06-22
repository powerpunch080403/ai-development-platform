from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.db.models import ToolRegistryEntry

TOOL_DEFINITIONS = (
    ("project.create", "project", True, "R2"),
    ("repository.register", "repository", True, "R2"),
    ("repository.get_status", "repository", False, "R1"),
    ("repository.check_dirty", "repository", False, "R1"),
    ("conversation.create", "conversation", True, "R1"),
    ("message.append", "conversation", True, "R1"),
    ("agent_run.create", "agent_run", True, "R1"),
    ("audit.record_event", "audit", True, "R1"),
    ("tool_call.record", "tool", True, "R1"),
    ("work_item.create", "work_item", True, "R1"),
    ("work_item.update_status", "work_item", True, "R1"),
    ("task.create", "task", True, "R2"),
    ("task.update_status", "task", True, "R2"),
    ("task_attempt.create", "task_attempt", True, "R2"),
    ("task_attempt.update_status", "task_attempt", True, "R2"),
    ("worker.register", "worker", True, "R2"),
    ("worker.claim_attempt", "worker", True, "R2"),
    ("worker.heartbeat", "worker", True, "R1"),
    ("worker.release_claim", "worker", True, "R2"),
    ("worker.revoke", "worker", True, "R2"),
    ("worker.run_mock", "worker", True, "R2"),
    ("worker_run.create", "worker", True, "R1"),
    ("worker_run.update_status", "worker", True, "R1"),
    ("worktree.create", "worktree", True, "R2"),
    ("worktree.get_status", "worktree", False, "R1"),
    ("worktree.get_diff", "worktree", False, "R1"),
    ("worktree.commit_result", "worktree", True, "R2"),
    ("artifact.create_ref", "artifact", True, "R1"),
    ("artifact.get_metadata", "artifact", False, "R1"),
    ("artifact.read_text", "artifact", False, "R1"),
    ("review.get_attempt", "review", False, "R1"),
    ("review.approve", "review", True, "R3"),
    ("review.reject", "review", True, "R2"),
    ("merge.prepare_squash", "merge", False, "R3"),
    ("merge.perform_squash", "merge", True, "R3"),
    ("worktree.cleanup", "worktree", True, "R2"),
    ("worktree.list_cleanup_pending", "worktree", False, "R1"),
    ("worker.run_manual", "worker", True, "R2"),
    ("worker_run.get", "worker", False, "R1"),
    ("worker_run.list_for_attempt", "worker", False, "R1"),
    ("worker_run.fail", "worker", True, "R2"),
    ("worker_run.cancel", "worker", True, "R2"),
    ("approval.request", "approval", True, "R2"),
    ("approval.record_decision", "approval", True, "R3"),
    ("approval.reject", "approval", True, "R2"),
    ("policy.evaluate", "policy", False, "R1"),
    ("policy.record_decision", "policy", True, "R2"),
    ("process_run.create", "process_run", True, "R2"),
    ("process_run.get", "process_run", False, "R1"),
    ("process_run.list_for_attempt", "process_run", False, "R1"),
    ("process_run.cancel", "process_run", True, "R2"),
    ("external_cli.context.preview", "external_cli", False, "R1"),
    ("external_cli.dry_run", "external_cli", True, "R2"),
)


def seed_tool_registry(session: Session) -> None:
    existing = set(
        session.execute(select(ToolRegistryEntry.tool_name, ToolRegistryEntry.tool_version))
    )
    for tool_name, category, has_side_effect, risk_level in TOOL_DEFINITIONS:
        if (tool_name, "1.0") in existing:
            continue
        session.add(
            ToolRegistryEntry(
                tool_name=tool_name,
                tool_version="1.0",
                category=category,
                description=f"Baseline record contract for {tool_name}",
                has_side_effect=has_side_effect,
                default_risk_level=risk_level,
                required_grants=None,
                scope_evaluator=None,
                idempotency_required=has_side_effect,
                approval_behavior="policy",
                audit_required=True,
                enabled=True,
            )
        )
    session.commit()
