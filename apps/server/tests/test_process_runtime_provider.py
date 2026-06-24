import sys
import os
import asyncio

from aidp_server.process_runtime import get_process_runtime_provider
from aidp_server.db.models import ArtifactRef
from aidp_server.artifacts import read_text_artifact
from test_worktrees import auth
from conftest import AppHarness

def setup_repo_and_task(app_harness: AppHarness, project_name: str, repo_name: str):
    auth(app_harness)
    repo_dir = app_harness.settings.app_data_dir / repo_name
    repo_dir.mkdir(parents=True, exist_ok=True)
    import subprocess
    subprocess.run(["git", "init"], cwd=repo_dir, check=True)

    resp = app_harness.client.post("/projects", json={"name": project_name})
    project_id = resp.json()["id"]

    resp = app_harness.client.post(
        f"/projects/{project_id}/repositories",
        json={"repository_path": str(repo_dir)}
    )
    repo_id = resp.json()["id"]
    return repo_dir, project_id, repo_id


def test_provider_preserves_cwd_and_stdout_and_exit_code(app_harness: AppHarness):
    repo_dir, project_id, repo_id = setup_repo_and_task(app_harness, "cwd_test", "repo_cwd")

    provider = get_process_runtime_provider()

    with app_harness.session_factory() as session:
        # 1, 3, 4: Cwd, stdout, exit code
        run_record = asyncio.run(provider.run(
            session=session,
            settings=app_harness.settings,
            executable=sys.executable,
            arguments=["-c", "import os; print(os.getcwd())"],
            working_directory=str(repo_dir),
            timeout_seconds=5,
            project_id=project_id,
            repository_id=repo_id,
        ))

        assert run_record.status.value == "succeeded"
        assert run_record.exit_code == 0

        stdout_art = session.get(ArtifactRef, run_record.stdout_artifact_id)
        content = read_text_artifact(stdout_art, app_harness.settings)
        # Verify CWD (normalize case for Windows just in case)
        assert str(repo_dir.resolve(strict=False)).lower() in content.lower() or str(repo_dir).lower() in content.lower()


def test_provider_preserves_env_and_stderr(app_harness: AppHarness):
    repo_dir, project_id, repo_id = setup_repo_and_task(app_harness, "env_test", "repo_env")

    provider = get_process_runtime_provider()

    with app_harness.session_factory() as session:
        # 2, 3: env behavior, stderr capture
        run_record = asyncio.run(provider.run(
            session=session,
            settings=app_harness.settings,
            executable=sys.executable,
            arguments=["-c", "import os, sys; print(os.environ.get('TEST_VAR', 'missing'), file=sys.stderr); sys.exit(1)"],
            working_directory=str(repo_dir),
            timeout_seconds=5,
            project_id=project_id,
            repository_id=repo_id,
            environment={"TEST_VAR": "present"}
        ))

        # 4: exit code
        assert run_record.status.value == "failed"
        assert run_record.exit_code == 1

        # 2, 3: stderr, env filtering (TEST_VAR is not allowlisted, so it should be missing)
        stderr_art = session.get(ArtifactRef, run_record.stderr_artifact_id)
        content = read_text_artifact(stderr_art, app_harness.settings)
        assert "missing" in content

        # Now test with an allowlisted var
        run_record2 = asyncio.run(provider.run(
            session=session,
            settings=app_harness.settings,
            executable=sys.executable,
            arguments=["-c", "import os, sys; print(os.environ.get('LANG', 'missing'))"],
            working_directory=str(repo_dir),
            timeout_seconds=5,
            project_id=project_id,
            repository_id=repo_id,
            environment={"LANG": "en_US.UTF-8"}
        ))
        stdout_art = session.get(ArtifactRef, run_record2.stdout_artifact_id)
        content2 = read_text_artifact(stdout_art, app_harness.settings)
        assert "en_US.UTF-8" in content2


def test_provider_preserves_timeout_behavior(app_harness: AppHarness):
    repo_dir, project_id, repo_id = setup_repo_and_task(app_harness, "timeout_test", "repo_timeout")

    provider = get_process_runtime_provider()

    with app_harness.session_factory() as session:
        # 5: Timeout
        run_record = asyncio.run(provider.run(
            session=session,
            settings=app_harness.settings,
            executable=sys.executable,
            arguments=["-c", "import time; time.sleep(10)"],
            working_directory=str(repo_dir),
            timeout_seconds=1, # short timeout
            project_id=project_id,
            repository_id=repo_id,
        ))

        assert run_record.status.value == "timed_out"
        assert run_record.error_code == "TIMED_OUT"


def test_provider_preserves_scope_validation(app_harness: AppHarness):
    repo_dir, project_id, repo_id = setup_repo_and_task(app_harness, "scope_test", "repo_scope")

    provider = get_process_runtime_provider()

    with app_harness.session_factory() as session:
        # 6: Scope validation
        run_record = asyncio.run(provider.run(
            session=session,
            settings=app_harness.settings,
            executable=sys.executable,
            arguments=["-c", "print('hello')"],
            # Give an obviously out of scope working directory
            working_directory=os.path.abspath(os.sep),
            timeout_seconds=5,
            project_id=project_id,
            repository_id=repo_id,
        ))

        assert run_record.status.value == "blocked"
        assert run_record.error_code == "SCOPE_VALIDATION_FAILED"


def test_provider_preserves_artifact_generation(app_harness: AppHarness):
    repo_dir, project_id, repo_id = setup_repo_and_task(app_harness, "art_test", "repo_art")

    provider = get_process_runtime_provider()

    with app_harness.session_factory() as session:
        # 7: Artifact generation
        run_record = asyncio.run(provider.run(
            session=session,
            settings=app_harness.settings,
            executable=sys.executable,
            arguments=["-c", "import sys; print('stdout_text'); print('stderr_text', file=sys.stderr)"],
            working_directory=str(repo_dir),
            timeout_seconds=5,
            project_id=project_id,
            repository_id=repo_id,
        ))

        assert run_record.stdout_artifact_id is not None
        assert run_record.stderr_artifact_id is not None

        stdout_art = session.get(ArtifactRef, run_record.stdout_artifact_id)
        assert stdout_art.kind.value == "cli_transcript"

        stderr_art = session.get(ArtifactRef, run_record.stderr_artifact_id)
        assert stderr_art.kind.value == "error_log"


def test_provider_uses_fallback_error_message_for_empty_exception(app_harness: AppHarness, monkeypatch):
    repo_dir, project_id, repo_id = setup_repo_and_task(app_harness, "exec_error_test", "repo_exec_error")
    provider = get_process_runtime_provider()

    async def _raise_empty_exception(*args, **kwargs):
        raise RuntimeError("")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _raise_empty_exception)

    with app_harness.session_factory() as session:
        run_record = asyncio.run(provider.run(
            session=session,
            settings=app_harness.settings,
            executable=sys.executable,
            arguments=["-c", "print('hello')"],
            working_directory=str(repo_dir),
            timeout_seconds=5,
            project_id=project_id,
            repository_id=repo_id,
        ))

        assert run_record.status.value == "failed"
        assert run_record.error_code == "EXECUTION_ERROR"
        assert run_record.error_message == repr(RuntimeError(""))
        assert run_record.error_message
