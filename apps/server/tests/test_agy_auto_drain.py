from pathlib import Path

import pytest
from sqlalchemy import select

from aidp_server.db.models import (
    AgentRun,
    LocalUser,
    RecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    ToolCall,
    ToolCallStatus,
    WorkerRun,
    utc_now,
)
from conftest import AppHarness
from test_external_cli_adapter_contract import authenticate, create_repository


def _agent_run(app_harness: AppHarness, project_id: str) -> AgentRun:
    with app_harness.session_factory() as session:
        local_user_id = session.scalars(select(LocalUser.id)).first()
        run = AgentRun(
            local_user_id=local_user_id,
            project_id=project_id,
            purpose="agy auto drain test",
        )
        session.add(run)
        session.commit()
        run_id = run.id
    with app_harness.session_factory() as session:
        loaded = session.get(AgentRun, run_id)
        assert loaded is not None
        return loaded


def _create_project_and_repository(app_harness: AppHarness, tmp_path: Path) -> tuple[str, str]:
    source = create_repository(tmp_path / "agy-auto-drain-source")
    project = app_harness.client.post("/projects", json={"name": "AGY Auto Drain"})
    assert project.status_code == 201, project.text
    project_id = str(project.json()["id"])
    repository = app_harness.client.post(
        f"/projects/{project_id}/repositories",
        json={"repository_path": str(source), "repository_role": "primary"},
    )
    assert repository.status_code == 201, repository.text
    return project_id, str(repository.json()["id"])


def _create_repo_task(app_harness: AppHarness, project_id: str, repository_id: str, title: str) -> str:
    response = app_harness.client.post(
        f"/projects/{project_id}/tasks",
        json={
            "repository_id": repository_id,
            "title": title,
            "instructions": f"Append the completion line for {title}.",
            "risk_level": "R1",
            "requested_worker_kind": "external_cli",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _start_agy_attempt(app_harness: AppHarness, run_id: str, task_id: str) -> dict[str, object]:
    response = app_harness.client.post(
        f"/agent-runs/{run_id}/tool-calls",
        json={
            "provider_kind": "codex_cli",
            "tool_name": "worker.start_task_attempt",
            "arguments_json": {"task_id": task_id, "worker_adapter": "agy"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == ToolCallStatus.SUCCEEDED.value
    return body["result_json"]


@pytest.mark.anyio
async def test_background_agy_runner_auto_drains_next_created_worker_run(
    monkeypatch, app_harness: AppHarness, tmp_path: Path
) -> None:
    from aidp_server import config, worker_execution

    authenticate(app_harness)
    app_harness.settings.allow_owner_agy_worker_run = True
    app_harness.settings.enable_experimental_antigravity_cli = True
    app_harness.settings.antigravity_cli_path = "fake-agy"
    monkeypatch.setattr(worker_execution, "get_session_factory", lambda: app_harness.session_factory)
    monkeypatch.setattr(worker_execution, "get_settings", lambda: app_harness.settings)
    monkeypatch.setattr(config, "get_settings", lambda: app_harness.settings)

    project_id, repository_id = _create_project_and_repository(app_harness, tmp_path)
    run = _agent_run(app_harness, project_id)
    task_one_id = _create_repo_task(app_harness, project_id, repository_id, "Attempt One")
    task_two_id = _create_repo_task(app_harness, project_id, repository_id, "Attempt Two")
    first = _start_agy_attempt(app_harness, run.id, task_one_id)
    second = _start_agy_attempt(app_harness, run.id, task_two_id)

    with app_harness.session_factory() as session:
        first_attempt = session.get(TaskAttempt, first["task_attempt_id"])
        first_run = session.get(WorkerRun, first["worker_run_id"])
        assert first_attempt is not None
        assert first_run is not None
        first_attempt.status = TaskAttemptStatus.RUNNING_WORKER
        first_run.status = RecordStatus.RUNNING
        session.commit()

    calls: list[str] = []

    async def fake_run_existing_agy_worker_run(session, settings, worker_run, mode="task_instructions"):
        calls.append(worker_run.id)
        attempt = session.get(TaskAttempt, worker_run.task_attempt_id)
        assert attempt is not None
        worker_run.status = RecordStatus.SUCCEEDED
        worker_run.completed_at = utc_now()
        worker_run.summary = f"Fake AGY completed {worker_run.id}"
        attempt.status = TaskAttemptStatus.COMMITTED
        attempt.completed_at = utc_now()
        attempt.result_summary = f"Fake AGY completed {worker_run.id}"
        session.flush()
        return {"status": "succeeded", "worker_run_id": worker_run.id}

    monkeypatch.setattr(
        worker_execution,
        "run_existing_agy_worker_run",
        fake_run_existing_agy_worker_run,
    )

    await worker_execution.background_agy_runner(str(first["worker_run_id"]))

    assert calls == [first["worker_run_id"], second["worker_run_id"]]
    with app_harness.session_factory() as session:
        first_attempt = session.get(TaskAttempt, first["task_attempt_id"])
        second_attempt = session.get(TaskAttempt, second["task_attempt_id"])
        first_run = session.get(WorkerRun, first["worker_run_id"])
        second_run = session.get(WorkerRun, second["worker_run_id"])
        assert first_attempt is not None
        assert second_attempt is not None
        assert first_run is not None
        assert second_run is not None
        assert first_attempt.status == TaskAttemptStatus.COMMITTED
        assert second_attempt.status == TaskAttemptStatus.COMMITTED
        assert first_run.status == RecordStatus.SUCCEEDED
        assert second_run.status == RecordStatus.SUCCEEDED
        drain_calls = session.scalars(
            select(ToolCall).where(ToolCall.tool_name == "worker.drain_queue")
        ).all()
        assert [call.status for call in drain_calls] == [
            ToolCallStatus.SUCCEEDED,
            ToolCallStatus.SUCCEEDED,
        ]
        assert drain_calls[0].result_json["status"] == "handoff_started"
        assert drain_calls[0].result_json["worker_run_id"] == second["worker_run_id"]
        assert drain_calls[1].result_json["status"] == "idle"
