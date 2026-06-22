from collections.abc import Mapping, Set
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from aidp_server.db.models import (
    GitWorktreeStatus,
    RecordStatus,
    TaskAttemptStatus,
    TaskStatus,
    WorkerStatus,
)

StatusT = TypeVar("StatusT", bound=StrEnum)


@dataclass(frozen=True)
class StateTransitionError(ValueError):
    entity: str
    current: StrEnum
    target: StrEnum

    def __str__(self) -> str:
        return (
            f"{self.entity} transition {self.current.value} -> {self.target.value} is not allowed"
        )

    def detail(self) -> dict[str, str]:
        return {
            "code": "STATE_TRANSITION_NOT_ALLOWED",
            "entity": self.entity,
            "from": self.current.value,
            "to": self.target.value,
        }


TASK_TRANSITIONS: Mapping[TaskStatus, Set[TaskStatus]] = {
    TaskStatus.DRAFT: {
        TaskStatus.READY,
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.CANCELLED,
    },
    TaskStatus.READY: {TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.QUEUED: {
        TaskStatus.RUNNING,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.RUNNING: {
        TaskStatus.WAITING_FOR_REVIEW,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.WAITING_FOR_REVIEW: {TaskStatus.CHANGES_REQUESTED, TaskStatus.COMPLETED},
    TaskStatus.CHANGES_REQUESTED: {
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.CANCELLED,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.COMPLETED: set(),
    TaskStatus.CANCELLED: set(),
    TaskStatus.FAILED: set(),
}

TASK_ATTEMPT_TRANSITIONS: Mapping[TaskAttemptStatus, Set[TaskAttemptStatus]] = {
    TaskAttemptStatus.CREATED: {
        TaskAttemptStatus.PREPARING_WORKTREE,
        TaskAttemptStatus.RUNNING_WORKER,
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    },
    TaskAttemptStatus.PREPARING_WORKTREE: {
        TaskAttemptStatus.RUNNING_WORKER,
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    },
    TaskAttemptStatus.RUNNING_WORKER: {
        TaskAttemptStatus.WAITING_FOR_COMMIT,
        TaskAttemptStatus.COMMITTED,
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    },
    TaskAttemptStatus.WAITING_FOR_COMMIT: {
        TaskAttemptStatus.COMMITTED,
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    },
    TaskAttemptStatus.COMMITTED: {
        TaskAttemptStatus.REVIEWING,
        TaskAttemptStatus.ACCEPTED,
        TaskAttemptStatus.REJECTED,
        TaskAttemptStatus.MERGE_READY,
        TaskAttemptStatus.MERGED,
    },
    TaskAttemptStatus.REVIEWING: {
        TaskAttemptStatus.ACCEPTED,
        TaskAttemptStatus.REJECTED,
        TaskAttemptStatus.FAILED,
    },
    TaskAttemptStatus.ACCEPTED: {TaskAttemptStatus.MERGE_READY, TaskAttemptStatus.MERGED},
    TaskAttemptStatus.REJECTED: {
        TaskAttemptStatus.RETRY_REQUESTED,
        TaskAttemptStatus.ABANDONED,
    },
    TaskAttemptStatus.RETRY_REQUESTED: {
        TaskAttemptStatus.PREPARING_WORKTREE,
        TaskAttemptStatus.RUNNING_WORKER,
        TaskAttemptStatus.CANCELLED,
        TaskAttemptStatus.ABANDONED,
    },
    TaskAttemptStatus.MERGE_READY: {TaskAttemptStatus.MERGED},
    TaskAttemptStatus.WORKER_FAILED: {
        TaskAttemptStatus.RETRY_REQUESTED,
        TaskAttemptStatus.CANCELLED,
        TaskAttemptStatus.ABANDONED,
    },
    TaskAttemptStatus.FAILED: {
        TaskAttemptStatus.RETRY_REQUESTED,
        TaskAttemptStatus.ABANDONED,
    },
    TaskAttemptStatus.MERGED: set(),
    TaskAttemptStatus.ABANDONED: set(),
    TaskAttemptStatus.CANCELLED: set(),
}

GIT_WORKTREE_TRANSITIONS: Mapping[GitWorktreeStatus, Set[GitWorktreeStatus]] = {
    GitWorktreeStatus.PLANNED: {GitWorktreeStatus.CREATING, GitWorktreeStatus.FAILED},
    GitWorktreeStatus.CREATING: {GitWorktreeStatus.READY, GitWorktreeStatus.FAILED},
    GitWorktreeStatus.READY: {
        GitWorktreeStatus.IN_USE,
        GitWorktreeStatus.DIRTY_RESULT,
        GitWorktreeStatus.COMMITTED,
        GitWorktreeStatus.ABANDONED,
        GitWorktreeStatus.FAILED,
    },
    GitWorktreeStatus.IN_USE: {
        GitWorktreeStatus.READY,
        GitWorktreeStatus.DIRTY_RESULT,
        GitWorktreeStatus.COMMITTED,
        GitWorktreeStatus.ABANDONED,
        GitWorktreeStatus.FAILED,
    },
    GitWorktreeStatus.DIRTY_RESULT: {
        GitWorktreeStatus.READY,
        GitWorktreeStatus.COMMITTED,
        GitWorktreeStatus.ABANDONED,
        GitWorktreeStatus.FAILED,
    },
    GitWorktreeStatus.COMMITTED: {
        GitWorktreeStatus.REVIEWING,
        GitWorktreeStatus.MERGE_READY,
        GitWorktreeStatus.CLEANUP_PENDING,
    },
    GitWorktreeStatus.REVIEWING: {
        GitWorktreeStatus.COMMITTED,
        GitWorktreeStatus.MERGE_READY,
        GitWorktreeStatus.CLEANUP_PENDING,
    },
    GitWorktreeStatus.MERGE_READY: {
        GitWorktreeStatus.MERGED,
        GitWorktreeStatus.CLEANUP_PENDING,
    },
    GitWorktreeStatus.MERGED: {GitWorktreeStatus.CLEANUP_PENDING},
    GitWorktreeStatus.ABANDONED: {GitWorktreeStatus.CLEANUP_PENDING},
    GitWorktreeStatus.FAILED: {GitWorktreeStatus.CLEANUP_PENDING},
    GitWorktreeStatus.CLEANUP_PENDING: {GitWorktreeStatus.CLEANED},
    GitWorktreeStatus.CLEANED: set(),
}

WORKER_RUN_TRANSITIONS: Mapping[RecordStatus, Set[RecordStatus]] = {
    RecordStatus.CREATED: {
        RecordStatus.RUNNING,
        RecordStatus.CANCELLED,
        RecordStatus.SKIPPED,
    },
    RecordStatus.RUNNING: {
        RecordStatus.SUCCEEDED,
        RecordStatus.FAILED,
        RecordStatus.CANCELLED,
    },
    RecordStatus.SUCCEEDED: set(),
    RecordStatus.FAILED: set(),
    RecordStatus.CANCELLED: set(),
    RecordStatus.SKIPPED: set(),
}

WORKER_TRANSITIONS: Mapping[WorkerStatus, Set[WorkerStatus]] = {
    WorkerStatus.AVAILABLE: {WorkerStatus.CLAIMED, WorkerStatus.REVOKED},
    WorkerStatus.CLAIMED: {
        WorkerStatus.RUNNING,
        WorkerStatus.AVAILABLE,
        WorkerStatus.EXPIRED,
        WorkerStatus.REVOKED,
    },
    WorkerStatus.RUNNING: {
        WorkerStatus.AVAILABLE,
        WorkerStatus.COMPLETED,
        WorkerStatus.CANCELLED,
        WorkerStatus.FAILED,
        WorkerStatus.HEARTBEAT_LOST,
        WorkerStatus.REVOKED,
    },
    WorkerStatus.HEARTBEAT_LOST: {
        WorkerStatus.AVAILABLE,
        WorkerStatus.EXPIRED,
        WorkerStatus.REVOKED,
    },
    WorkerStatus.EXPIRED: {WorkerStatus.AVAILABLE, WorkerStatus.REVOKED},
    WorkerStatus.RELEASED: {WorkerStatus.AVAILABLE, WorkerStatus.REVOKED},
    WorkerStatus.COMPLETED: {WorkerStatus.AVAILABLE, WorkerStatus.REVOKED},
    WorkerStatus.CANCELLED: {WorkerStatus.AVAILABLE, WorkerStatus.REVOKED},
    WorkerStatus.FAILED: {WorkerStatus.AVAILABLE, WorkerStatus.REVOKED},
    WorkerStatus.REVOKED: set(),
}

PUBLIC_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    status: set(targets) for status, targets in TASK_TRANSITIONS.items()
}
PUBLIC_TASK_TRANSITIONS[TaskStatus.RUNNING].discard(TaskStatus.WAITING_FOR_REVIEW)
PUBLIC_TASK_TRANSITIONS[TaskStatus.WAITING_FOR_REVIEW].discard(TaskStatus.COMPLETED)

PUBLIC_TASK_ATTEMPT_TRANSITIONS: Mapping[TaskAttemptStatus, Set[TaskAttemptStatus]] = {
    TaskAttemptStatus.CREATED: {
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    },
    TaskAttemptStatus.PREPARING_WORKTREE: {
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    },
    TaskAttemptStatus.RUNNING_WORKER: {
        TaskAttemptStatus.WAITING_FOR_COMMIT,
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    },
    TaskAttemptStatus.WAITING_FOR_COMMIT: {
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    },
    TaskAttemptStatus.WORKER_FAILED: {
        TaskAttemptStatus.RETRY_REQUESTED,
        TaskAttemptStatus.CANCELLED,
        TaskAttemptStatus.ABANDONED,
    },
    TaskAttemptStatus.FAILED: {
        TaskAttemptStatus.RETRY_REQUESTED,
        TaskAttemptStatus.ABANDONED,
    },
    TaskAttemptStatus.REJECTED: {TaskAttemptStatus.RETRY_REQUESTED},
}


def assert_allowed_transition(
    entity: str,
    current: StatusT,
    target: StatusT,
    transitions: Mapping[StatusT, Set[StatusT]],
) -> None:
    if current == target:
        return
    if target not in transitions.get(current, set()):
        raise StateTransitionError(entity, current, target)


def assert_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    assert_allowed_transition("task", current, target, TASK_TRANSITIONS)


def assert_task_attempt_transition(current: TaskAttemptStatus, target: TaskAttemptStatus) -> None:
    assert_allowed_transition("task_attempt", current, target, TASK_ATTEMPT_TRANSITIONS)


def assert_git_worktree_transition(current: GitWorktreeStatus, target: GitWorktreeStatus) -> None:
    assert_allowed_transition("git_worktree", current, target, GIT_WORKTREE_TRANSITIONS)


def assert_worker_run_transition(current: RecordStatus, target: RecordStatus) -> None:
    assert_allowed_transition("worker_run", current, target, WORKER_RUN_TRANSITIONS)


def assert_worker_transition(current: WorkerStatus, target: WorkerStatus) -> None:
    assert_allowed_transition("worker", current, target, WORKER_TRANSITIONS)


def assert_public_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    assert_allowed_transition("task", current, target, PUBLIC_TASK_TRANSITIONS)


def assert_public_task_attempt_transition(
    current: TaskAttemptStatus, target: TaskAttemptStatus
) -> None:
    assert_allowed_transition("task_attempt", current, target, PUBLIC_TASK_ATTEMPT_TRANSITIONS)
