from sqlalchemy import select

from aidp_server.db.models import Task, WorkerRun, ApprovalRequest, AgentRun
from conftest import AppHarness
from test_conversations_and_tools import authenticate, create_conversation, create_project


def test_start_queued_agent_run_invokes_fake_provider(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_fake_owner_provider = True
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    # Create AgentRun
    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Test fake provider",
        },
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    # Start AgentRun with fake provider
    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start", json={"provider_kind": "fake"}
    )
    assert start_resp.status_code == 200

    # Verify status transition
    assert start_resp.json()["status"] == "completed"

    # Verify DB state
    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "completed"
        assert run.started_at is not None
        assert run.completed_at is not None


def test_fake_provider_rejected_by_default(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    # allow_fake_owner_provider is False by default
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Test fake provider rejection",
        },
    )
    run_id = run_resp.json()["id"]

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start", json={"provider_kind": "fake"}
    )
    assert start_resp.status_code == 403
    assert start_resp.json()["detail"] == "Fake owner provider is not allowed"


def test_unknown_provider_rejected(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Test unknown provider rejection",
        },
    )
    run_id = run_resp.json()["id"]

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start", json={"provider_kind": "unknown_provider"}
    )
    assert start_resp.status_code == 400
    assert "Unknown owner provider kind" in start_resp.json()["detail"]


def test_codex_cli_provider_skeleton_basic(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Test codex cli skeleton",
        },
    )
    run_id = run_resp.json()["id"]

    # Start with default provider
    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={},  # should default to codex_cli
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "completed"

    with app_harness.session_factory() as session:
        from aidp_server.db.models import AuditEvent

        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "owner_runtime.skeleton_invoked",
                AuditEvent.agent_run_id == run_id,
            )
        )
        assert audit is not None
        assert audit.metadata_json["skeleton"] is True
        assert audit.metadata_json.get("bridge_spike", False) is False
        assert audit.metadata_json["real_provider_execution"] is False
        assert audit.metadata_json["tool_loop_executed"] is False
        assert audit.metadata_json["task_side_effects_performed"] is False
        assert audit.metadata_json["worker_side_effects_performed"] is False
        assert audit.metadata_json["approval_side_effects_performed"] is False


def test_codex_cli_provider_bridge_spike_safe_invocation(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_real_codex_owner_provider = True

    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Test codex cli bridge spike",
        },
    )
    run_id = run_resp.json()["id"]

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start", json={"provider_kind": "codex_cli"}
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "completed"

    with app_harness.session_factory() as session:
        from aidp_server.db.models import AuditEvent

        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "owner_runtime.bridge_spike_invoked",
                AuditEvent.agent_run_id == run_id,
            )
        )
        assert audit is not None
        assert audit.metadata_json["bridge_spike"] is True
        assert audit.metadata_json["real_provider_execution"] is False
        assert audit.metadata_json["tool_loop_executed"] is False
        assert audit.metadata_json["task_side_effects_performed"] is False
        assert audit.metadata_json["worker_side_effects_performed"] is False
        assert audit.metadata_json["approval_side_effects_performed"] is False

        # Verify it attempted to run `codex --version`
        assert audit.metadata_json["codex_cli_command"] == "codex"


def test_keyword_routing_is_prohibited_during_start(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_fake_owner_provider = True
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    for keyword in ["이어서 해줘", "정리해줘", "고쳐줘"]:
        # Send a keyword-like message
        message_resp = app_harness.client.post(
            f"/conversations/{conversation_id}/messages",
            json={"role": "user", "content": keyword, "content_type": "text"},
        )
        assert message_resp.status_code == 201
        message_id = message_resp.json()["id"]

        # Create AgentRun
        run_resp = app_harness.client.post(
            "/agent-runs",
            json={
                "conversation_id": conversation_id,
                "project_id": project_id,
                "purpose": keyword,
                "input_message_id": message_id,
            },
        )
        assert run_resp.status_code == 201
        run_id = run_resp.json()["id"]

        # Start AgentRun
        start_resp = app_harness.client.post(
            f"/agent-runs/{run_id}/start", json={"provider_kind": "fake"}
        )
        assert start_resp.status_code == 200

    # Verify that no Tasks, WorkerRuns or Approvals were created
    with app_harness.session_factory() as session:
        tasks = session.scalars(select(Task).where(Task.project_id == project_id)).all()
        assert len(tasks) == 0

        worker_runs = session.scalars(
            select(WorkerRun).where(WorkerRun.project_id == project_id)
        ).all()
        assert len(worker_runs) == 0

        approvals = session.scalars(
            select(ApprovalRequest).where(ApprovalRequest.project_id == project_id)
        ).all()
        assert len(approvals) == 0
