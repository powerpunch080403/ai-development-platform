from sqlalchemy import select

from aidp_server.db.models import Task, WorkerRun, ApprovalRequest, AgentRun
from conftest import AppHarness
from test_conversations_and_tools import authenticate, create_conversation, create_project


def test_start_queued_agent_run_invokes_fake_provider(app_harness: AppHarness) -> None:
    authenticate(app_harness)
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
        f"/agent-runs/{run_id}/start",
        json={"provider_kind": "fake"}
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
        json={"provider_kind": "codex_cli"}
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "completed"


def test_keyword_routing_is_prohibited_during_start(
    app_harness: AppHarness,
) -> None:
    authenticate(app_harness)
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
            f"/agent-runs/{run_id}/start",
            json={"provider_kind": "fake"}
        )
        assert start_resp.status_code == 200

    # Verify that no Tasks, WorkerRuns or Approvals were created
    with app_harness.session_factory() as session:
        tasks = session.scalars(select(Task).where(Task.project_id == project_id)).all()
        assert len(tasks) == 0

        worker_runs = session.scalars(select(WorkerRun).where(WorkerRun.project_id == project_id)).all()
        assert len(worker_runs) == 0
        
        approvals = session.scalars(select(ApprovalRequest).where(ApprovalRequest.project_id == project_id)).all()
        assert len(approvals) == 0
