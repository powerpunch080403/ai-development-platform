import os
import pytest

from test_external_cli_adapter_contract import (
    authenticate,
    create_repository,
    setup_claimed_attempt,
    git,
)
from aidp_server.db.models import Task, GitWorktree, TaskAttempt, WorkerRun, ProcessRun


def test_real_agy_timeout_is_failed_safely(app_harness, tmp_path) -> None:
    if os.environ.get("AIDP_RUN_REAL_AGY_TESTS") != "true":
        pytest.skip("Skipping real agy test. Set AIDP_RUN_REAL_AGY_TESTS=true to run.")

    authenticate(app_harness)
    app_harness.settings.enable_experimental_antigravity_cli = True
    # Explicitly set a very short timeout to force a timeout failure
    app_harness.settings.antigravity_cli_timeout_seconds = 2

    # Use a temporary repository
    source = create_repository(tmp_path / "real-agy-source-timeout")
    (source / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    git(source, "add", "README.md")
    git(source, "commit", "-m", "Initial commit")
    source_head_before = git(source, "rev-parse", "HEAD")

    attempt_id, worker_id, _, task_id, _ = setup_claimed_attempt(app_harness, source)

    with app_harness.session_factory() as session:
        task = session.get(Task, task_id)
        # Restrict write_scope
        task.write_scope_json = {"mode": "paths", "paths": ["README.md"], "allow_new_files": False}
        session.commit()

    # Invoke the controlled endpoint with the timeout test mode
    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/antigravity/run-experimental",
        json={
            "adapter_kind": "antigravity_cli",
            "worker_id": worker_id,
            "mode": "controlled_timeout_test",
        },
    )
    assert response.status_code == 200, response.text
    res = response.json()

    # Worker run fails due to timeout
    assert res["status"] in ("failed", "timed_out")
    error_code = res.get("error_code", "")
    assert error_code == "TIMED_OUT" or "time" in error_code.lower()

    # Verify state in DB
    with app_harness.session_factory() as session:
        worktree = session.query(GitWorktree).filter_by(task_attempt_id=attempt_id).first()
        # No result commit should have been created
        assert worktree.result_commit_sha is None

        attempt = session.get(TaskAttempt, attempt_id)
        assert attempt.status.value != "committed"

        task = session.get(Task, task_id)
        assert task.status.value != "waiting_for_review"

        worker_run = session.query(WorkerRun).filter_by(task_attempt_id=attempt_id).first()
        assert worker_run.status.value in ("failed", "timed_out")

        process_run = session.get(ProcessRun, res["process_run_id"])
        assert process_run.status.value in ("failed", "timed_out")
        # For a timeout, the process was killed, so it shouldn't have a success exit code.
        # ProcessRunner usually records TIMED_OUT status and perhaps an error code like TIMED_OUT.
        assert process_run.error_code == "TIMED_OUT"

    # Verify git repository heads are unchanged
    assert git(source, "rev-parse", "HEAD") == source_head_before
