from pathlib import Path
from aidp_server.db.models import ApprovalRequest
from aidp_server.policy import evaluate_action
from conftest import AppHarness
from test_reviews import committed
from test_worktrees import auth, git


def test_policy_evaluator() -> None:
    # Test R1-R4
    decision, risk = evaluate_action("worktree.commit_result")
    assert decision.value == "allow"
    assert risk.value == "R1"

    decision, risk = evaluate_action("review.approve")
    assert decision.value == "allow"
    assert risk.value == "R2"

    decision, risk = evaluate_action("merge.perform_squash")
    assert decision.value == "approval_required"
    assert risk.value == "R3"

    decision, risk = evaluate_action("some.unknown.action")
    assert decision.value == "deny"
    assert risk.value == "R4"


def test_prepare_returns_policy(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    source, wt, aid, task_id = committed(app_harness, tmp_path, "pol_prepare")

    resp = app_harness.client.post(f"/task-attempts/{aid}/merge/prepare")
    assert resp.status_code == 200
    data = resp.json()
    assert data["policy_decision"] == "approval_required"
    assert data["approval_status"] == "pending"


def test_squash_blocked_without_approval(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    source, wt, aid, task_id = committed(app_harness, tmp_path, "pol_block")

    resp = app_harness.client.post(
        f"/task-attempts/{aid}/merge/squash", json={"commit_message": "test"}
    )
    assert resp.status_code == 409
    assert "Explicit approval is required" in resp.json()["detail"]


def test_approve_generates_approval_and_policy(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    source, wt, aid, task_id = committed(app_harness, tmp_path, "pol_approve")

    app_harness.client.post(f"/task-attempts/{aid}/review/approve", json={"review_summary": "LGTM"})

    approvals = app_harness.client.get("/approval-requests").json()
    assert len(approvals) > 0
    assert approvals[0]["task_attempt_id"] == aid
    assert approvals[0]["status"] == "approved"
    assert approvals[0]["action_type"] == "merge.perform_squash"

    decisions = app_harness.client.get("/policy-decisions").json()
    assert len(decisions) > 0
    assert decisions[0]["action_type"] == "review.approve"
    assert decisions[0]["decision"] == "allow"

    resp = app_harness.client.post(f"/task-attempts/{aid}/merge/prepare")
    assert resp.json()["approval_status"] == "approved"


def test_stale_fingerprint_blocks_merge(app_harness: AppHarness, tmp_path: Path) -> None:
    auth(app_harness)
    source, wt, aid, task_id = committed(app_harness, tmp_path, "pol_stale")

    # Approve
    app_harness.client.post(f"/task-attempts/{aid}/review/approve", json={"review_summary": "LGTM"})

    # Mutate source to change base commit
    (source / "surprise.txt").write_text("hello", encoding="utf-8")
    git(source, "add", "surprise.txt")
    git(source, "commit", "-m", "surprise base update")

    # Try to squash
    resp = app_harness.client.post(
        f"/task-attempts/{aid}/merge/squash", json={"commit_message": "test"}
    )
    assert resp.status_code == 409
    assert "stale" in resp.json()["detail"].lower()

    # Also verify approval status changed to stale
    with app_harness.session_factory() as s:
        reqs = s.query(ApprovalRequest).filter_by(task_attempt_id=aid).all()
        assert any(r.status.value == "stale" for r in reqs)


def test_squash_with_changed_commit_message_marks_stale(
    app_harness: AppHarness, tmp_path: Path
) -> None:
    auth(app_harness)
    source, wt, aid, task_id = committed(app_harness, tmp_path, "pol_msg_stale")

    # Approve
    app_harness.client.post(f"/task-attempts/{aid}/review/approve", json={"review_summary": "LGTM"})

    # Try to squash with different message
    resp = app_harness.client.post(
        f"/task-attempts/{aid}/merge/squash", json={"commit_message": "Different message"}
    )
    assert resp.status_code == 409
    assert "stale" in resp.json()["detail"].lower()

    with app_harness.session_factory() as s:
        reqs = s.query(ApprovalRequest).filter_by(task_attempt_id=aid).all()
        assert any(r.status.value == "stale" for r in reqs)


def test_arguments_hash_is_deterministic() -> None:
    from aidp_server.approvals import build_approval_arguments_hash

    hash1 = build_approval_arguments_hash("test", {"a": 1, "b": 2})
    hash2 = build_approval_arguments_hash("test", {"b": 2, "a": 1})
    assert hash1 == hash2
    assert hash1 is not None

    hash3 = build_approval_arguments_hash("test", None)
    assert hash3 is None
