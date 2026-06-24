import asyncio
import sys

from aidp_server.artifacts import read_text_artifact
from aidp_server.db.models import ArtifactRef
from aidp_server.process_runtime import get_process_runtime_provider
from conftest import AppHarness
from test_process_runtime_provider import setup_repo_and_task


def test_provider_falls_back_to_threaded_subprocess_when_asyncio_subprocess_unsupported(
    app_harness: AppHarness, monkeypatch
):
    repo_dir, project_id, repo_id = setup_repo_and_task(
        app_harness,
        "threaded_fallback_test",
        "repo_threaded_fallback",
    )
    provider = get_process_runtime_provider()

    async def _raise_not_implemented(*args, **kwargs):
        raise NotImplementedError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _raise_not_implemented)

    with app_harness.session_factory() as session:
        run_record = asyncio.run(
            provider.run(
                session=session,
                settings=app_harness.settings,
                executable=sys.executable,
                arguments=["-c", "print('threaded fallback ok')"],
                working_directory=str(repo_dir),
                timeout_seconds=5,
                project_id=project_id,
                repository_id=repo_id,
            )
        )

        assert run_record.status.value == "succeeded"
        assert run_record.exit_code == 0
        assert run_record.stdout_artifact_id is not None

        stdout_art = session.get(ArtifactRef, run_record.stdout_artifact_id)
        content = read_text_artifact(stdout_art, app_harness.settings)
        assert "threaded fallback ok" in content
