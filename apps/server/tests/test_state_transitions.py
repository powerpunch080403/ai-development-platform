import pytest

from aidp_server.db.models import RecordStatus, TaskAttemptStatus
from aidp_server.state_transitions import (
    StateTransitionError,
    assert_public_task_attempt_transition,
    assert_task_attempt_transition,
    assert_worker_run_transition,
)


def test_task_attempt_created_can_enter_queued_worker() -> None:
    assert_task_attempt_transition(
        TaskAttemptStatus.CREATED,
        TaskAttemptStatus.QUEUED_WORKER,
    )


@pytest.mark.parametrize(
    "target",
    [
        TaskAttemptStatus.RUNNING_WORKER,
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    ],
)
def test_task_attempt_queued_worker_internal_transitions(target: TaskAttemptStatus) -> None:
    assert_task_attempt_transition(TaskAttemptStatus.QUEUED_WORKER, target)


@pytest.mark.parametrize(
    "target",
    [
        TaskAttemptStatus.WORKER_FAILED,
        TaskAttemptStatus.FAILED,
        TaskAttemptStatus.CANCELLED,
    ],
)
def test_task_attempt_queued_worker_public_failure_transitions(
    target: TaskAttemptStatus,
) -> None:
    assert_public_task_attempt_transition(TaskAttemptStatus.QUEUED_WORKER, target)


def test_public_transition_cannot_manually_queue_task_attempt() -> None:
    with pytest.raises(StateTransitionError):
        assert_public_task_attempt_transition(
            TaskAttemptStatus.CREATED,
            TaskAttemptStatus.QUEUED_WORKER,
        )


def test_public_transition_cannot_manually_run_queued_worker_attempt() -> None:
    with pytest.raises(StateTransitionError):
        assert_public_task_attempt_transition(
            TaskAttemptStatus.QUEUED_WORKER,
            TaskAttemptStatus.RUNNING_WORKER,
        )


def test_worker_run_created_can_enter_queued() -> None:
    assert_worker_run_transition(RecordStatus.CREATED, RecordStatus.QUEUED)


@pytest.mark.parametrize(
    "target",
    [
        RecordStatus.RUNNING,
        RecordStatus.FAILED,
        RecordStatus.CANCELLED,
        RecordStatus.SKIPPED,
    ],
)
def test_worker_run_queued_transitions(target: RecordStatus) -> None:
    assert_worker_run_transition(RecordStatus.QUEUED, target)


def test_worker_run_queued_cannot_succeed_without_running() -> None:
    with pytest.raises(StateTransitionError):
        assert_worker_run_transition(RecordStatus.QUEUED, RecordStatus.SUCCEEDED)
