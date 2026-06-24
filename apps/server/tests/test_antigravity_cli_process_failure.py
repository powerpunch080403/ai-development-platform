import sys

from aidp_server.db.models import (
    ProcessRun,
    ProcessRunStatus,
    RecordStatus,
    TaskAttempt,
    TaskAttemptStatus,
    WorkerRun,
    utc_now,
)
from conftest import AppHarness
from test_external_cli_adapter_contract import (
    authenticate,
    create_repository,
    setup_claimed_attempt,
)


def test_antigravity_cli_process_failure_fails_attempt(
    app_harness: AppHarness, tmp_path, monkeypatch
) -> None:
    authenticate(app_harness)
    app_harness.settings.enable_experimental_antigravity_cli = True
    app_harness.settings.antigravity_cli_path = sys.executable

    source = create_repository(tmp_path / "process-failure-source")
    attempt_id, worker_id, _, _, _ = setup_claimed_attempt(app_harness, source)

    class FailedProcessProvider:
        async def run(
            self,
            *,
            session,
            executable,
            arguments,
            working_directory,
            timeout_seconds,
            **kwargs,
        ):
            process_run = ProcessRun(
                local_user_id=kwargs.get("local_user_id"),
                project_id=kwargs.get("project_id"),
                repository_id=kwargs.get("repository_id"),
                task_id=kwargs.get("task_id"),
                task_attempt_id=kwargs.get("task_attempt_id"),
                worker_id=kwargs.get("worker_id"),
                worker_run_id=kwargs.get("worker_run_id"),
                command_display=f"{executable} <redacted>",
                executable=executable,
                arguments_json={"arguments": arguments},
                working_directory=working_directory,
                timeout_seconds=timeout_seconds,
                status=ProcessRunStatus.FAILED,
                error_code="EXECUTION_ERROR",
                error_message="NotImplementedError()",
                failed_at=utc_now(),
            )
            session.add(process_run)
            session.flush()
            return process_run

    import aidp_server.process_runtime as process_runtime

    monkeypatch.setattr(
        process_runtime, "get_process_runtime_provider", lambda: FailedProcessProvider()
    )

    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/antigravity/run-experimental",
        json={
            "adapter_kind": "antigravity_cli",
            "worker_id": worker_id,
            "mode": "controlled_readme_test",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "failed"
    assert result["error_code"] == "EXECUTION_ERROR"
    assert result["error_message"] == "NotImplementedError()"

    with app_harness.session_factory() as session:
        worker_run = session.get(WorkerRun, result["worker_run_id"])
        assert worker_run.status == RecordStatus.FAILED
        assert worker_run.error_message == "NotImplementedError()"

        attempt = session.get(TaskAttempt, attempt_id)
        assert attempt.status == TaskAttemptStatus.FAILED
        assert attempt.error_code == "EXECUTION_ERROR"
        assert attempt.error_message == "NotImplementedError()"
