import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.artifacts import create_text_artifact
from aidp_server.config import Settings
from aidp_server.db.models import ArtifactKind, ArtifactRef, GitWorktree, Task, TaskAttempt
from aidp_server.write_scope import normalize_write_scope

EXTERNAL_CLI_CONSTRAINTS = [
    "Only operate inside the assigned worktree path.",
    "Do not modify the source repository path.",
    "Do not push to remotes.",
    "Do not merge into main/default.",
    "Do not edit files outside the worktree.",
    "Do not read or write .env or secret files unless explicitly allowed later.",
    "Produce a concise worker report.",
    "Leave review, approval, and squash merge to Owner.",
    "Only modify files within the declared write_scope.",
]


def build_external_cli_context_package(
    session: Session,
    attempt: TaskAttempt,
    task: Task,
    worktree: GitWorktree,
    worker_run_id: str | None = None,
) -> dict[str, Any]:
    artifact_ids = list(
        session.scalars(
            select(ArtifactRef.id)
            .where(ArtifactRef.task_attempt_id == attempt.id)
            .order_by(ArtifactRef.created_at)
        )
    )
    return {
        "id": str(uuid4()),
        "task_attempt_id": attempt.id,
        "task_id": task.id,
        "project_id": attempt.project_id,
        "repository_id": attempt.repository_id,
        "worker_run_id": worker_run_id,
        "git_worktree_id": worktree.id,
        "worktree_path": worktree.worktree_path,
        "branch_name": worktree.branch_name,
        "base_branch": worktree.base_branch,
        "base_commit_sha": worktree.base_commit_sha,
        "task_title": task.title,
        "task_instructions": task.instructions,
        "write_scope": normalize_write_scope(task.write_scope_json),
        "constraints": EXTERNAL_CLI_CONSTRAINTS,
        "allowed_working_directory": worktree.worktree_path,
        "forbidden_actions": [
            "source repository changes",
            "remote push",
            "default branch merge",
            "outside-worktree file access",
            "secret file access",
        ],
        "approval_review_boundary": "Owner performs review, approval, and squash merge.",
        "artifact_ids": artifact_ids,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def create_context_package_artifact(
    session: Session,
    settings: Settings,
    context_package: dict[str, Any],
    local_user_id: str,
    worker_id: str | None,
) -> str:
    artifact = create_text_artifact(
        session=session,
        settings=settings,
        content=json.dumps(context_package, indent=2, ensure_ascii=False),
        kind=ArtifactKind.GENERATED_REPORT,
        user_id=local_user_id,
        project_id=str(context_package["project_id"]),
        repository_id=str(context_package["repository_id"]),
        task_id=str(context_package["task_id"]),
        attempt_id=str(context_package["task_attempt_id"]),
        worker_id=worker_id,
    )
    return artifact.id
