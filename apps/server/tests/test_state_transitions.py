import pytest

from aidp_server.db.models import GitWorktreeStatus, RecordStatus
from aidp_server.state_transitions import (
    StateTransitionError,
    assert_git_worktree_transition,
    assert_worker_run_transition,
)
from conftest import AppHarness
from test_work_and_workers import authenticate, project, task, worker


def test_task_creation_ignores_client_status(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    response = app_harness.client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "Guard task creation",
            "instructions": "Remain a draft.",
            "risk_level": "R1",
            "status": "completed",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "draft"


def test_attempt_creation_ignores_client_status(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    created_task = task(app_harness, project_id)
    response = app_harness.client.post(
        f"/tasks/{created_task['id']}/attempts", json={"status": "merged"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "created"


def test_generic_task_endpoint_cannot_complete_task(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    created_task = task(app_harness, project_id)
    response = app_harness.client.post(
        f"/tasks/{created_task['id']}/status", json={"status": "completed"}
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == {
        "code": "STATE_TRANSITION_NOT_ALLOWED",
        "entity": "task",
        "from": "draft",
        "to": "completed",
    }
    assert app_harness.client.get(f"/tasks/{created_task['id']}").json()["status"] == "draft"


@pytest.mark.parametrize("target", ["committed", "merged"])
def test_generic_attempt_endpoint_cannot_set_protected_state(
    app_harness: AppHarness, target: str
) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    created_task = task(app_harness, project_id)
    attempt = app_harness.client.post(f"/tasks/{created_task['id']}/attempts", json={}).json()
    response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/status", json={"status": target}
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "STATE_TRANSITION_NOT_ALLOWED"
    assert response.json()["detail"]["to"] == target
    assert app_harness.client.get(f"/task-attempts/{attempt['id']}").json()["status"] == "created"
    events = app_harness.client.get("/audit-events").json()
    assert any(event["event_type"] == "state_transition.denied" for event in events)


def test_worker_claim_uses_internal_transition(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = project(app_harness)
    created_task = task(app_harness, project_id)
    attempt = app_harness.client.post(f"/tasks/{created_task['id']}/attempts", json={}).json()
    registered_worker = worker(app_harness, "Transition Worker")
    response = app_harness.client.post(
        f"/workers/{registered_worker['id']}/claim",
        json={"task_attempt_id": attempt["id"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "running_worker"
    assert app_harness.client.get(f"/tasks/{created_task['id']}").json()["status"] == "running"


def test_terminal_internal_status_maps_reject_reopening() -> None:
    with pytest.raises(StateTransitionError):
        assert_git_worktree_transition(GitWorktreeStatus.CLEANED, GitWorktreeStatus.READY)
    with pytest.raises(StateTransitionError):
        assert_worker_run_transition(RecordStatus.SUCCEEDED, RecordStatus.RUNNING)
