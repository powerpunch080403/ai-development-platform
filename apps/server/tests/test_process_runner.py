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


def test_process_environment_allowlist():
    from aidp_server.process_environment import build_process_environment, is_sensitive_env_key
    import os
    
    # 1. is_sensitive_env_key
    assert is_sensitive_env_key("API_KEY") is True
    assert is_sensitive_env_key("my_api_key_for_test") is True
    assert is_sensitive_env_key("SESSION_TOKEN") is True
    assert is_sensitive_env_key("GITHUB_TOKEN") is True
    assert is_sensitive_env_key("some_credential_val") is True
    assert is_sensitive_env_key("MY_APP_PASSWORD") is True
    assert is_sensitive_env_key("NORMAL_VAR") is False
    assert is_sensitive_env_key("PATH") is False

    # 2. build_process_environment
    os.environ["FAKE_SECRET_TOKEN"] = "hidden123"
    os.environ["AIDP_TEST_VISIBLE_ENV"] = "should_not_show"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    
    # extra_env has both safe and unsafe
    extra = {
        "ANOTHER_SECRET": "hide_me",
        "LANG": "en_US.UTF-8",  # Allowlisted
        "RANDOM_SAFE": "block_me" # Not allowlisted
    }
    
    env = build_process_environment(extra)
    
    # Safe allowed keys should be present
    assert "PYTHONIOENCODING" in env
    assert "PATH" in env
    
    # Safe extra allowed keys should be present
    assert env.get("LANG") == "en_US.UTF-8"
    
    # Sensitive or unlisted keys must not be present
    assert "FAKE_SECRET_TOKEN" not in env
    assert "AIDP_TEST_VISIBLE_ENV" not in env
    assert "ANOTHER_SECRET" not in env
    assert "RANDOM_SAFE" not in env
    
    # Cleanup os.environ
    del os.environ["FAKE_SECRET_TOKEN"]
    del os.environ["AIDP_TEST_VISIBLE_ENV"]
    del os.environ["PYTHONIOENCODING"]

def test_process_runner_does_not_leak_env(app_harness: AppHarness):
    import os
    import asyncio
    from aidp_server.process_runner import execute_process_async
    from test_worktrees import auth
    
    os.environ["SUPER_SECRET_DB_PASS"] = "pwned"
    
    auth(app_harness)
    
    # Create project & repo for scope via API
    repo_dir = app_harness.settings.app_data_dir / "testrepo_env"
    repo_dir.mkdir(parents=True, exist_ok=True)
    import subprocess
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)
    
    resp = app_harness.client.post("/projects", json={"name": "env test project"})
    project_id = resp.json()["id"]
    
    resp = app_harness.client.post(
        f"/projects/{project_id}/repositories",
        json={"repository_path": str(repo_dir)}
    )
    repo_id = resp.json()["id"]
    
    # We will test execution using execute_process_async directly
    with app_harness.session_factory() as session:
        args = ["-c", "import os; print('ENV_TEST:', os.environ.get('SUPER_SECRET_DB_PASS', 'missing'))"]
    
        run_record = asyncio.run(execute_process_async(
            session=session,
            settings=app_harness.settings,
            executable=sys.executable,
            arguments=args,
            working_directory=str(repo_dir),
            timeout_seconds=5,
            repository_id=repo_id,
        ))
        
        assert run_record.status.value == "succeeded"
        assert run_record.exit_code == 0
        
        from aidp_server.db.models import ArtifactRef
        from aidp_server.artifacts import read_text_artifact
        
        stdout_art = session.get(ArtifactRef, run_record.stdout_artifact_id)
        assert stdout_art is not None
        
        content = read_text_artifact(stdout_art, app_harness.settings)
        # The secret must be missing from the subprocess env
        assert "ENV_TEST: missing" in content
        # Also ensure the raw secret didn't leak into the output directly
        assert "pwned" not in content

    # Cleanup
    del os.environ["SUPER_SECRET_DB_PASS"]

