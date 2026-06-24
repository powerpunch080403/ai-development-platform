from dataclasses import dataclass


@dataclass(frozen=True)
class ActionPolicyDefinition:
    action_type: str
    risk_level: str
    decision: str
    description: str
    requires_approval: bool = False
    enabled_in_tool_registry: bool = True


ACTION_CATALOG: list[ActionPolicyDefinition] = [
    ActionPolicyDefinition("project.list", "R0", "allow", "List projects"),
    ActionPolicyDefinition("project.create", "R1", "allow", "Create a project"),
    ActionPolicyDefinition("repository.register", "R1", "allow", "Register a repository"),
    ActionPolicyDefinition("repository.get_status", "R0", "allow", "Get repository status"),
    ActionPolicyDefinition("repository.check_dirty", "R0", "allow", "Check if repository is dirty"),
    ActionPolicyDefinition("conversation.create", "R0", "allow", "Create conversation"),
    ActionPolicyDefinition("message.append", "R0", "allow", "Append message"),
    ActionPolicyDefinition("agent_run.create", "R1", "allow", "Create agent run"),
    ActionPolicyDefinition("audit.record_event", "R0", "allow", "Record audit event"),
    ActionPolicyDefinition("tool_call.record", "R1", "allow", "Record tool call"),
    ActionPolicyDefinition("work_item.create", "R1", "allow", "Create work item"),
    ActionPolicyDefinition("work_item.update_status", "R1", "allow", "Update work item status"),
    ActionPolicyDefinition("task.list", "R0", "allow", "List tasks"),
    ActionPolicyDefinition("task.create", "R1", "allow", "Create task"),
    ActionPolicyDefinition("task.update_status", "R1", "allow", "Update task status"),
    ActionPolicyDefinition("attempt.accept", "R1", "allow", "Accept a task attempt result"),
    ActionPolicyDefinition("attempt.reject", "R1", "allow", "Reject a task attempt result"),
    ActionPolicyDefinition(
        "attempt.follow_up",
        "R1",
        "allow",
        "Create a follow-up attempt from owner feedback",
    ),
    ActionPolicyDefinition(
        "worker.start_task_attempt", "R1", "allow", "Start task attempt via owner tool"
    ),
    ActionPolicyDefinition(
        "worker.run_task_attempt", "R1", "allow", "Run task attempt via owner tool"
    ),
    ActionPolicyDefinition(
        "worker.drain_queue", "R1", "allow", "Drain the next queued worker run"
    ),
    ActionPolicyDefinition(
        "worker.recover_stale_runs",
        "R1",
        "allow",
        "Recover stale running worker runs",
    ),
    ActionPolicyDefinition("task_attempt.create", "R1", "allow", "Create task attempt"),
    ActionPolicyDefinition("task_attempt.update_status", "R1", "allow", "Update task attempt status"),
    ActionPolicyDefinition("worker.register", "R1", "allow", "Register worker"),
    ActionPolicyDefinition("worker.claim_attempt", "R1", "allow", "Worker claim attempt"),
    ActionPolicyDefinition("worker.heartbeat", "R0", "allow", "Worker heartbeat"),
    ActionPolicyDefinition("worker.release_claim", "R1", "allow", "Worker release claim"),
    ActionPolicyDefinition("worker.revoke", "R2", "allow", "Worker revoke"),
    ActionPolicyDefinition("worktree.create", "R2", "allow", "Create git worktree"),
    ActionPolicyDefinition("worktree.get_status", "R0", "allow", "Get git worktree status"),
    ActionPolicyDefinition("worktree.get_diff", "R0", "allow", "Get git worktree diff"),
    ActionPolicyDefinition("worktree.commit_result", "R1", "allow", "Commit worktree result"),
    ActionPolicyDefinition("worktree.cleanup", "R2", "allow", "Cleanup git worktree"),
    ActionPolicyDefinition(
        "worktree.list_cleanup_pending", "R0", "allow", "List cleanup pending worktrees"
    ),
    ActionPolicyDefinition("artifact.create_ref", "R1", "allow", "Create artifact ref"),
    ActionPolicyDefinition("artifact.get_metadata", "R0", "allow", "Get artifact metadata"),
    ActionPolicyDefinition("artifact.read_text", "R0", "allow", "Read artifact text"),
    ActionPolicyDefinition("review.get_attempt", "R0", "allow", "Get review attempt"),
    ActionPolicyDefinition("review.approve", "R2", "allow", "Approve review"),
    ActionPolicyDefinition("review.reject", "R2", "allow", "Reject review"),
    ActionPolicyDefinition("approval.request", "R2", "allow", "Request approval"),
    ActionPolicyDefinition("approval.record_decision", "R2", "allow", "Record approval decision"),
    ActionPolicyDefinition("approval.reject", "R2", "allow", "Reject approval"),
    ActionPolicyDefinition("policy.evaluate", "R0", "allow", "Evaluate policy"),
    ActionPolicyDefinition("policy.record_decision", "R1", "allow", "Record policy decision"),
    ActionPolicyDefinition("merge.prepare_squash", "R2", "allow", "Prepare squash merge"),
    ActionPolicyDefinition(
        "merge.perform_squash",
        "R3",
        "approval_required",
        "Perform squash merge",
        requires_approval=True,
    ),
    ActionPolicyDefinition("worker.run_mock", "R1", "allow", "Run mock worker"),
    ActionPolicyDefinition("worker.run_manual", "R1", "allow", "Run manual worker"),
    ActionPolicyDefinition("worker_run.create", "R1", "allow", "Create worker run"),
    ActionPolicyDefinition("worker_run.update_status", "R1", "allow", "Update worker run status"),
    ActionPolicyDefinition("process_run.create", "R2", "allow", "Create process run"),
    ActionPolicyDefinition("process_run.get", "R0", "allow", "Get process run"),
    ActionPolicyDefinition("process_run.list_for_attempt", "R0", "allow", "List process runs for attempt"),
    ActionPolicyDefinition("process_run.cancel", "R2", "allow", "Cancel process run"),
    ActionPolicyDefinition("external_cli.context.preview", "R1", "allow", "Preview external CLI context"),
    ActionPolicyDefinition("external_cli.dry_run", "R2", "allow", "Dry run external CLI"),
    ActionPolicyDefinition(
        "external_cli.run_antigravity_experimental",
        "R2",
        "allow",
        "Run experimental Antigravity CLI",
    ),
]


def get_action_policy(action_type: str) -> ActionPolicyDefinition | None:
    for policy in ACTION_CATALOG:
        if policy.action_type == action_type:
            return policy
    return None
