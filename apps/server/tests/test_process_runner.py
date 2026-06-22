import sys
import pytest
from uuid import uuid4

from conftest import AppHarness
from test_worktrees import auth

def test_process_run_scope_validation(app_harness: AppHarness):
    auth(app_harness)
    
    # Create project & repo
    repo_dir = app_harness.settings.app_data_dir / "testrepo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    import subprocess
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    
    resp = app_harness.client.post("/projects", json={"name": "test project"})
    project_id = resp.json()["id"]
    
    resp = app_harness.client.post(
        f"/projects/{project_id}/repositories",
        json={"repository_path": str(repo_dir)}
    )
    repo_id = resp.json()["id"]
    
    # Create Task & Attempt
    resp = app_harness.client.post(
        f"/projects/{project_id}/tasks",
        json={
            "title": "test task",
            "instructions": "run process",
            "repository_id": repo_id,
            "risk_level": "R1"
        }
    )
    task_id = resp.json()["id"]
    
    resp = app_harness.client.post(f"/tasks/{task_id}/attempts", json={})
    assert resp.status_code == 201, resp.text
    attempt_id = resp.json()["id"]

    # The test-command endpoint uses the repo_id's path
    resp = app_harness.client.post(f"/task-attempts/{attempt_id}/process-runs/test-command", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "succeeded", data
    assert data["exit_code"] == 0, data
    assert data["command_display"].startswith(sys.executable), data
    print("RUN DATA:", data)

def test_redaction_logic():
    from aidp_server.redaction import redact_text, redact_args
    
    raw = "Here is my TOKEN=12345 and api_key: secret123"
    redacted = redact_text(raw)
    assert "12345" not in redacted
    assert "secret123" not in redacted
    assert "TOKEN=[REDACTED]" in redacted
    assert "api_key=[REDACTED]" in redacted
    
    bearer = "Authorization: Bearer my-jwt-token-xyz"
    redacted_bearer = redact_text(bearer)
    assert "my-jwt-token-xyz" not in redacted_bearer
    assert "Bearer [REDACTED]" in redacted_bearer

    args = redact_args(["--token=secret", "--password=pass"])
    assert args[0] == "--token=[REDACTED]"
    assert args[1] == "--password=[REDACTED]"
