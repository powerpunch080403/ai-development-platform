import json
import sys
import textwrap
from pathlib import Path

from aidp_server.db.models import ProcessRun, WorkerRun, TaskAttempt, Task, GitWorktree
from test_external_cli_adapter_contract import (
    authenticate,
    create_repository,
    setup_claimed_attempt,
    git,
)
from conftest import AppHarness


def test_antigravity_cli_endpoints_require_auth(app_harness: AppHarness) -> None:
    assert app_harness.client.get("/external-cli/antigravity/status").status_code == 401
    response = app_harness.client.post(
        "/task-attempts/missing/external-cli/antigravity/run-experimental",
        json={"adapter_kind": "antigravity_cli", "worker_id": "missing"},
    )
    assert response.status_code == 401


def test_antigravity_cli_disabled_by_default(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    
    # Check status
    response = app_harness.client.get("/external-cli/antigravity/status")
    assert response.status_code == 200
    assert response.json() == {"status": "disabled"}

    source = create_repository(tmp_path / "disabled-source")
    attempt_id, worker_id, _, _, _ = setup_claimed_attempt(app_harness, source)

    # Attempt to run should fail 403
    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/antigravity/run-experimental",
        json={"adapter_kind": "antigravity_cli", "worker_id": worker_id},
    )
    assert response.status_code == 403


def test_antigravity_cli_not_configured_fails_safely(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    app_harness.settings.enable_experimental_antigravity_cli = True
    app_harness.settings.antigravity_cli_path = None

    response = app_harness.client.get("/external-cli/antigravity/status")
    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"

    source = create_repository(tmp_path / "not-configured-source")
    attempt_id, worker_id, _, _, _ = setup_claimed_attempt(app_harness, source)

    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/antigravity/run-experimental",
        json={"adapter_kind": "antigravity_cli", "worker_id": worker_id},
    )
    assert response.status_code == 503
    assert "not set in configuration" in response.text


def test_antigravity_cli_rejects_arbitrary_args(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    app_harness.settings.enable_experimental_antigravity_cli = True
    app_harness.settings.antigravity_cli_path = sys.executable

    source = create_repository(tmp_path / "args-source")
    attempt_id, worker_id, _, _, _ = setup_claimed_attempt(app_harness, source)

    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/antigravity/run-experimental",
        json={
            "adapter_kind": "antigravity_cli",
            "worker_id": worker_id,
            "executable": "bash",
            "args": ["-c", "echo hacked"]
        },
    )
    assert response.status_code == 422


def test_antigravity_cli_fake_shim_no_change(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    app_harness.settings.enable_experimental_antigravity_cli = True

    shim = tmp_path / "fake_shim.py"
    shim.write_text("print('Did nothing')", encoding="utf-8")
    
    bat_shim = tmp_path / "fake_shim.bat"
    bat_shim.write_text(f'"{sys.executable}" "{shim}"', encoding="utf-8")
    app_harness.settings.antigravity_cli_path = str(bat_shim)

    source = create_repository(tmp_path / "no-change-source")
    attempt_id, worker_id, _, _, _ = setup_claimed_attempt(app_harness, source)

    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/antigravity/run-experimental",
        json={"adapter_kind": "antigravity_cli", "worker_id": worker_id},
    )
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "succeeded"
    
    with app_harness.session_factory() as session:
        attempt = session.get(TaskAttempt, attempt_id)
        assert attempt.status.value == "running_worker"
        from aidp_server.db.models import ArtifactRef
        report_ref = session.get(ArtifactRef, res["report_artifact_id"])
        from aidp_server.artifacts import read_text_artifact
        report = json.loads(read_text_artifact(report_ref, app_harness.settings))
        assert report["files_modified"] is False
        assert report["result_commit_created"] is False


def test_antigravity_cli_fake_shim_modifies_file(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    app_harness.settings.enable_experimental_antigravity_cli = True

    shim = tmp_path / "fake_shim.py"
    shim.write_text(textwrap.dedent("""
        import os
        with open("README.md", "a") as f:
            f.write("Modified by shim\\n")
    """), encoding="utf-8")
    
    bat_shim = tmp_path / "fake_shim.bat"
    bat_shim.write_text(f'"{sys.executable}" "{shim}"', encoding="utf-8")
    app_harness.settings.antigravity_cli_path = str(bat_shim)

    source = create_repository(tmp_path / "modifies-source")
    source_head_before = git(source, "rev-parse", "HEAD")
    attempt_id, worker_id, _, _, _ = setup_claimed_attempt(app_harness, source)

    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/antigravity/run-experimental",
        json={"adapter_kind": "antigravity_cli", "worker_id": worker_id},
    )
    assert response.status_code == 200, response.text
    res = response.json()
    assert res["status"] == "succeeded"

    with app_harness.session_factory() as session:
        from aidp_server.db.models import ArtifactRef
        report_ref = session.get(ArtifactRef, res["report_artifact_id"])
        from aidp_server.artifacts import read_text_artifact
        report = json.loads(read_text_artifact(report_ref, app_harness.settings))
        assert report["files_modified"] is True
        assert report["result_commit_created"] is True

    # Check source repo remains unchanged
    assert git(source, "rev-parse", "HEAD") == source_head_before

    with app_harness.session_factory() as session:
        worktree = session.query(GitWorktree).filter_by(task_attempt_id=attempt_id).first()
        assert worktree.result_commit_sha is not None


def test_antigravity_cli_fake_shim_write_scope_violation(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    app_harness.settings.enable_experimental_antigravity_cli = True

    shim = tmp_path / "fake_shim.py"
    shim.write_text(textwrap.dedent("""
        import os
        with open("FORBIDDEN.md", "w") as f:
            f.write("I should not be here\\n")
    """), encoding="utf-8")
    
    bat_shim = tmp_path / "fake_shim.bat"
    bat_shim.write_text(f'"{sys.executable}" "{shim}"', encoding="utf-8")
    app_harness.settings.antigravity_cli_path = str(bat_shim)

    source = create_repository(tmp_path / "violation-source")
    attempt_id, worker_id, _, task_id, _ = setup_claimed_attempt(app_harness, source)
    
    # Restrict write scope to just README.md
    with app_harness.session_factory() as session:
        task = session.get(Task, task_id)
        task.write_scope_json = {"mode": "paths", "paths": ["README.md"], "allow_new_files": False}
        session.commit()

    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/antigravity/run-experimental",
        json={"adapter_kind": "antigravity_cli", "worker_id": worker_id},
    )
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "failed"

    with app_harness.session_factory() as session:
        from aidp_server.db.models import ArtifactRef
        report_ref = session.get(ArtifactRef, res["report_artifact_id"])
        from aidp_server.artifacts import read_text_artifact
        report = json.loads(read_text_artifact(report_ref, app_harness.settings))
        assert report["files_modified"] is True
        assert report["result_commit_created"] is False
    assert res["error_code"] == "WRITE_SCOPE_VIOLATION"


def test_antigravity_cli_active_run_guard(app_harness: AppHarness, tmp_path: Path) -> None:
    authenticate(app_harness)
    app_harness.settings.enable_experimental_antigravity_cli = True

    shim = tmp_path / "fake_shim.py"
    shim.write_text("print('test')", encoding="utf-8")
    bat_shim = tmp_path / "fake_shim.bat"
    bat_shim.write_text(f'"{sys.executable}" "{shim}"', encoding="utf-8")
    app_harness.settings.antigravity_cli_path = str(bat_shim)

    source = create_repository(tmp_path / "guard-source")
    attempt_id, worker_id, _, _, _ = setup_claimed_attempt(app_harness, source)

    # Insert a dummy running WorkerRun of external_cli_dry_run
    with app_harness.session_factory() as session:
        from aidp_server.db.models import RecordStatus, utc_now
        wr = WorkerRun(
            local_user_id="test", project_id="test", task_id="test",
            task_attempt_id=attempt_id, worker_id=worker_id,
            adapter_kind="external_cli_dry_run",
            status=RecordStatus.RUNNING, started_at=utc_now()
        )
        session.add(wr)
        session.commit()

    response = app_harness.client.post(
        f"/task-attempts/{attempt_id}/external-cli/antigravity/run-experimental",
        json={"adapter_kind": "antigravity_cli", "worker_id": worker_id},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ACTIVE_EXTERNAL_CLI_RUN_EXISTS"
