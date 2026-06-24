import pytest

from aidp_server.db.models import WorkerRun


@pytest.mark.anyio
async def test_background_agy_runner_uses_default_task_prompt(monkeypatch, app_harness) -> None:
    from aidp_server import worker_execution

    captured = {}

    async def fake_run_existing_agy_worker_run(session, settings, worker_run, mode="task_instructions"):
        captured["worker_run_id"] = worker_run.id
        captured["mode"] = mode
        return {"status": "succeeded"}

    monkeypatch.setattr(
        worker_execution,
        "run_existing_agy_worker_run",
        fake_run_existing_agy_worker_run,
    )

    with app_harness.session_factory() as session:
        worker_run = WorkerRun(
            local_user_id="user",
            project_id="project",
            task_id="task",
            task_attempt_id="attempt",
            worker_id="worker",
            adapter_kind="agy",
        )
        session.add(worker_run)
        session.commit()
        worker_run_id = worker_run.id

    await worker_execution.background_agy_runner(worker_run_id)

    assert captured == {"worker_run_id": worker_run_id, "mode": "task_instructions"}
