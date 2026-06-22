import os
import subprocess
from pathlib import Path

import pytest

from aidp_server.db.models import GitWorktree, Task, TaskAttempt
from conftest import AppHarness
from test_external_cli_adapter_contract import authenticate, create_repository, git

REQUIRED_REAL_AGY_ENV = {
    "AIDP_RUN_REAL_AGY_TESTS": "true",
    "AIDP_ENABLE_EXPERIMENTAL_ANTIGRAVITY_CLI": "true",
    "AIDP_ANTIGRAVITY_CLI_ALLOW_DANGEROUS_SKIP_PERMISSIONS": "true",
}


def real_agy_review_merge_enabled() -> bool:
    return all(
        os.environ.get(name) == value for name, value in REQUIRED_REAL_AGY_ENV.items()
    ) and bool(os.environ.get("AIDP_ANTIGRAVITY_CLI_PATH"))


@pytest.mark.skipif(
    not real_agy_review_merge_enabled(),
    reason="Set all real AGY opt-in environment variables to run this temporary-repository E2E.",
)
def test_real_agy_controlled_result_can_be_reviewed_and_squash_merged(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    implementation_repository = Path(__file__).resolve().parents[3]
    implementation_head_before = git(implementation_repository, "rev-parse", "HEAD")

    source = create_repository(tmp_path / "real-agy-review-merge-source")
    source_head_before = git(source, "rev-parse", "HEAD")
    assert git(source, "rev-list", "--count", "main") == "1"

    authenticate(app_harness)
    assert app_harness.settings.enable_experimental_antigravity_cli is True
    assert app_harness.settings.antigravity_cli_allow_dangerous_skip_permissions is True
    assert app_harness.settings.antigravity_cli_path == os.environ["AIDP_ANTIGRAVITY_CLI_PATH"]

    project = app_harness.client.post("/projects", json={"name": "Real AGY Review E2E"}).json()
    repository = app_harness.client.post(
        f"/projects/{project['id']}/repositories",
        json={"repository_path": str(source), "repository_role": "primary"},
    ).json()
    work_item = app_harness.client.post(
        f"/projects/{project['id']}/work-items",
        json={"title": "Controlled README update", "work_item_type": "improvement"},
    ).json()
    task = app_harness.client.post(
        f"/projects/{project['id']}/tasks",
        json={
            "repository_id": repository["id"],
            "work_item_id": work_item["id"],
            "title": "Run controlled AGY README edit",
            "instructions": "Use only the controlled Antigravity README test mode.",
            "write_scope": {
                "mode": "paths",
                "paths": ["README.md"],
                "allow_new_files": False,
            },
            "risk_level": "R1",
            "requested_worker_kind": "external_cli",
        },
    ).json()
    attempt = app_harness.client.post(f"/tasks/{task['id']}/attempts", json={}).json()
    worker = app_harness.client.post(
        "/workers", json={"display_name": "Real AGY E2E", "worker_kind": "external_cli"}
    ).json()
    claim = app_harness.client.post(
        f"/workers/{worker['id']}/claim", json={"task_attempt_id": attempt["id"]}
    )
    assert claim.status_code == 200, claim.text
    worktree = app_harness.client.post(f"/task-attempts/{attempt['id']}/worktree").json()

    agy_response = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/external-cli/antigravity/run-experimental",
        json={
            "adapter_kind": "antigravity_cli",
            "worker_id": worker["id"],
            "mode": "controlled_readme_test",
        },
    )
    assert agy_response.status_code == 200, agy_response.text
    agy_result = agy_response.json()
    assert agy_result["status"] == "succeeded"
    assert agy_result["files_modified"] is True
    assert agy_result["result_commit_created"] is True

    with app_harness.session_factory() as session:
        stored_attempt = session.get(TaskAttempt, str(attempt["id"]))
        stored_task = session.get(Task, str(task["id"]))
        stored_worktree = session.get(GitWorktree, str(worktree["id"]))
        assert stored_attempt is not None and stored_attempt.status.value == "committed"
        assert stored_task is not None and stored_task.status.value == "waiting_for_review"
        assert stored_worktree is not None and stored_worktree.result_commit_sha is not None
        result_commit_sha = stored_worktree.result_commit_sha

    assert git(source, "rev-parse", "HEAD") == source_head_before
    assert (
        subprocess.run(
            ["git", "-C", str(source), "merge-base", "--is-ancestor", result_commit_sha, "main"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        ).returncode
        == 1
    )

    review = app_harness.client.get(f"/task-attempts/{attempt['id']}/review")
    assert review.status_code == 200, review.text
    review_data = review.json()
    assert review_data["base_commit_sha"] == source_head_before
    assert review_data["result_commit_sha"] == result_commit_sha
    assert "Controlled AGY worker test completed." in review_data["diff"]

    merge_without_approval = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/merge/squash", json={}
    )
    assert merge_without_approval.status_code == 409
    assert "approval" in merge_without_approval.text.lower()

    approved = app_harness.client.post(
        f"/task-attempts/{attempt['id']}/review/approve",
        json={"review_summary": "Controlled AGY README diff reviewed."},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["review_status"] == "approved"
    assert approved.json()["approval_status"] == "approved"

    prepared = app_harness.client.post(f"/task-attempts/{attempt['id']}/merge/prepare")
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["merge_possible"] is True
    assert prepared.json()["approval_status"] == "approved"

    merged = app_harness.client.post(f"/task-attempts/{attempt['id']}/merge/squash", json={})
    assert merged.status_code == 200, merged.text
    merge_commit_sha = merged.json()["merge_commit_sha"]
    assert merge_commit_sha
    assert "Controlled AGY worker test completed." in (source / "README.md").read_text(
        encoding="utf-8"
    )
    assert git(source, "rev-list", "--count", "main") == "2"
    assert git(source, "rev-parse", f"{merge_commit_sha}^") == source_head_before
    assert (
        subprocess.run(
            ["git", "-C", str(source), "merge-base", "--is-ancestor", result_commit_sha, "main"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        ).returncode
        == 1
    )
    assert app_harness.client.get(f"/tasks/{task['id']}").json()["status"] == "completed"
    assert app_harness.client.get(f"/task-attempts/{attempt['id']}").json()["status"] == "merged"
    assert (
        app_harness.client.get(f"/worktrees/{worktree['id']}").json()["status"] == "cleanup_pending"
    )
    assert Path(str(worktree["worktree_path"])).exists()
    assert git(implementation_repository, "rev-parse", "HEAD") == implementation_head_before
