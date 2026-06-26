import sys

from sqlalchemy import select

from aidp_server.db.models import ApprovalRequest, AgentRun, AuditEvent, Message, Task, WorkerRun
from conftest import AppHarness
from test_conversations_and_tools import authenticate, create_conversation, create_project


def test_start_queued_agent_run_invokes_fake_provider(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_fake_owner_provider = True
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

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

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "fake"},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "running_model"

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "completed"
        assert run.provider_kind == "fake"
        assert run.started_at is not None
        assert run.completed_at is not None


def test_fake_provider_rejected_by_default(app_harness: AppHarness) -> None:
    authenticate(app_harness)
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
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "fake"},
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
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "unknown_provider"},
    )
    assert start_resp.status_code == 400
    assert "Unknown owner provider kind" in start_resp.json()["detail"]


def test_future_provider_kinds_fail_as_not_implemented(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Test local provider stub",
        },
    )
    run_id = run_resp.json()["id"]

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "local_ai"},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "running_model"

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "failed"
        assert run.provider_kind == "local_ai"
        assert run.error_code == "owner_provider_not_implemented"
        assert run.error_category == "provider_not_implemented"


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

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "running_model"

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "failed"
        assert run.started_at is not None
        assert run.failed_at is not None
        assert run.completed_at is None
        assert run.provider_kind == "codex_cli"
        assert run.error_code == "owner_provider_not_connected"
        assert run.error_category == "provider_not_connected"

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
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "codex_cli"},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "running_model"

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "completed"
        assert run.provider_kind == "codex_cli"
        assert run.started_at is not None
        assert run.completed_at is not None
        assert run.failed_at is None
        assert run.error_code is None
        assert run.error_category is None

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
        assert audit.metadata_json["codex_cli_command"] == "codex"


def test_codex_cli_prompt_mode_appends_assistant_message(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_real_codex_owner_provider = True
    app_harness.settings.codex_cli_mode = "prompt"
    app_harness.settings.codex_cli_command = sys.executable
    app_harness.settings.codex_cli_prompt_args = (
        "-c \"import sys; data=sys.stdin.read().strip(); print('Owner echo: ' + data)\""
    )

    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])
    message_resp = app_harness.client.post(
        f"/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "hello owner", "content_type": "text"},
    )
    assert message_resp.status_code == 201
    message_id = message_resp.json()["id"]

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Prompt mode test",
            "input_message_id": message_id,
        },
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "codex_cli"},
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "running_model"

    with app_harness.session_factory() as session:
        assistant_message = session.scalar(
            select(Message).where(Message.agent_run_id == run_id, Message.role == "assistant")
        )
        assert assistant_message is not None
        assert assistant_message.content == "Owner echo: hello owner"


def test_codex_cli_prompt_mode_maps_usage_limit_failure(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_real_codex_owner_provider = True
    app_harness.settings.codex_cli_mode = "prompt"
    app_harness.settings.codex_cli_command = sys.executable
    app_harness.settings.codex_cli_prompt_args = (
        "-c \"import sys; sys.stderr.write('ERROR: You have hit your usage limit. "
        "Try again at Jun 28th, 2026 8:09 PM.'); sys.exit(1)\""
    )

    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])
    message_resp = app_harness.client.post(
        f"/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "hello owner", "content_type": "text"},
    )
    assert message_resp.status_code == 201
    message_id = message_resp.json()["id"]

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": "Usage limit test",
            "input_message_id": message_id,
        },
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    start_resp = app_harness.client.post(
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "codex_cli"},
    )
    assert start_resp.status_code == 200
    body = start_resp.json()
    assert body["status"] == "running_model"
    expected_error_message = (
        "Owner provider quota exceeded. Try again at Jun 28th, 2026 8:09 PM."
    )

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.provider_kind == "codex_cli"
        assert run.error_code == "owner_provider_quota_exceeded"
        assert run.error_category == "quota_exceeded"
        assert run.error_message == expected_error_message
        assert run.retry_after == "Jun 28th, 2026 8:09 PM"
        assert run.provider_metadata_json is not None
        assert run.provider_metadata_json["provider_kind"] == "codex_cli"
        assert run.provider_metadata_json["usage_limit"] is True
        assert "usage limit" in str(run.provider_metadata_json["provider_message"]).lower()

        assistant_message = session.scalar(
            select(Message).where(Message.agent_run_id == run_id, Message.role == "assistant")
        )
        assert assistant_message is None

        audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "owner_runtime.prompt_failed",
                AuditEvent.agent_run_id == run_id,
            )
        )
        assert audit is not None
        assert audit.metadata_json["usage_limit"] is True


def test_keyword_routing_is_prohibited_during_start(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_fake_owner_provider = True
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    for keyword in ["이어서 해줘", "정리해줘", "고쳐줘"]:
        message_resp = app_harness.client.post(
            f"/conversations/{conversation_id}/messages",
            json={"role": "user", "content": keyword, "content_type": "text"},
        )
        assert message_resp.status_code == 201
        message_id = message_resp.json()["id"]

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

        start_resp = app_harness.client.post(
            f"/agent-runs/{run_id}/start",
            json={"provider_kind": "fake"},
        )
        assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        tasks = session.scalars(select(Task).where(Task.project_id == project_id)).all()
        assert len(tasks) == 0

        worker_runs = session.scalars(select(WorkerRun).where(WorkerRun.project_id == project_id)).all()
        assert len(worker_runs) == 0

        approvals = session.scalars(select(ApprovalRequest).where(ApprovalRequest.project_id == project_id)).all()
        assert len(approvals) == 0
