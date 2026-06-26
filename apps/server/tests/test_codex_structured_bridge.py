import sys

from sqlalchemy import select

from aidp_server.db.models import AgentRun, Message, Task, ToolCall
from conftest import AppHarness
from test_conversations_and_tools import authenticate, create_conversation, create_project


def _configure_structured_stdout(app_harness: AppHarness, script: str, timeout: float = 120) -> None:
    app_harness.settings.allow_real_codex_owner_provider = True
    app_harness.settings.codex_cli_mode = "structured_stdout"
    app_harness.settings.codex_cli_command = sys.executable
    app_harness.settings.codex_cli_prompt_args = f'-c "{script}"'
    app_harness.settings.codex_cli_timeout_seconds = timeout


def _create_run(app_harness: AppHarness, *, purpose: str = "Structured bridge test") -> tuple[str, str, str]:
    authenticate(app_harness)
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    conversation_id = str(conversation["id"])

    message_resp = app_harness.client.post(
        f"/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "Please use structured events", "content_type": "text"},
    )
    assert message_resp.status_code == 201

    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation_id,
            "project_id": project_id,
            "purpose": purpose,
            "input_message_id": message_resp.json()["id"],
        },
    )
    assert run_resp.status_code == 201
    return project_id, conversation_id, str(run_resp.json()["id"])


def test_codex_structured_stdout_appends_assistant_message(app_harness: AppHarness) -> None:
    script = (
        "import json; "
        "print(json.dumps({'type':'assistant_message','content':'Structured hello'}))"
    )
    _configure_structured_stdout(app_harness, script)
    _project_id, _conversation_id, run_id = _create_run(app_harness)

    start_resp = app_harness.client.post(f"/agent-runs/{run_id}/start", json={"provider_kind": "codex_cli"})
    assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "completed"
        assert run.provider_metadata_json["mode"] == "structured_stdout"
        assert run.provider_metadata_json["protocol"] == "owner_provider_events.v1"
        assert run.provider_metadata_json["assistant_message_count"] == 1
        assert run.provider_metadata_json["tool_loop_executed"] is False

        message = session.scalar(select(Message).where(Message.agent_run_id == run_id, Message.role == "assistant"))
        assert message is not None
        assert message.content == "Structured hello"


def test_codex_structured_stdout_tool_request_creates_task_through_owner_loop(
    app_harness: AppHarness,
) -> None:
    script = (
        "import json; "
        "event={'type':'tool_request','tool_name':'task.create',"
        "'provider_call_id':'structured-task-create',"
        "'arguments_json':{'title':'Structured Task','instructions':'Created through structured tool request',"
        "'write_scope':{'mode':'paths','paths':['apps/server/'],'allow_new_files':True}}}; "
        "print(json.dumps(event))"
    )
    _configure_structured_stdout(app_harness, script)
    project_id, _conversation_id, run_id = _create_run(app_harness)

    start_resp = app_harness.client.post(f"/agent-runs/{run_id}/start", json={"provider_kind": "codex_cli"})
    assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "completed"
        assert run.provider_metadata_json["tool_loop_executed"] is True
        assert run.provider_metadata_json["task_side_effects_performed"] is True
        assert run.provider_metadata_json["worker_side_effects_performed"] is False
        assert run.provider_metadata_json["approval_side_effects_performed"] is False

        task = session.scalar(select(Task).where(Task.project_id == project_id, Task.title == "Structured Task"))
        assert task is not None
        assert task.agent_run_id == run_id

        call = session.scalar(
            select(ToolCall).where(
                ToolCall.agent_run_id == run_id,
                ToolCall.tool_name == "task.create",
            )
        )
        assert call is not None
        assert call.status.value == "succeeded"
        assert call.caller_id == "codex_cli"
        assert call.correlation_id == "structured-task-create"
        assert call.result_json["task_id"] == task.id


def test_codex_structured_stdout_maps_malformed_output(app_harness: AppHarness) -> None:
    _configure_structured_stdout(app_harness, "print('not json')")
    _project_id, _conversation_id, run_id = _create_run(app_harness)

    start_resp = app_harness.client.post(f"/agent-runs/{run_id}/start", json={"provider_kind": "codex_cli"})
    assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "failed"
        assert run.error_code == "owner_provider_malformed_tool_output"
        assert run.error_category == "malformed_tool_output"
        assert "not valid JSON" in run.provider_metadata_json["provider_message"]


def test_codex_structured_stdout_maps_empty_response(app_harness: AppHarness) -> None:
    _configure_structured_stdout(app_harness, "")
    _project_id, _conversation_id, run_id = _create_run(app_harness)

    start_resp = app_harness.client.post(f"/agent-runs/{run_id}/start", json={"provider_kind": "codex_cli"})
    assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "failed"
        assert run.error_code == "owner_provider_empty_response"
        assert run.error_category == "empty_response"


def test_codex_structured_stdout_maps_command_not_found(app_harness: AppHarness) -> None:
    authenticate(app_harness)
    app_harness.settings.allow_real_codex_owner_provider = True
    app_harness.settings.codex_cli_mode = "structured_stdout"
    app_harness.settings.codex_cli_command = "aidp-codex-command-that-does-not-exist"
    project_id = create_project(app_harness)
    conversation = create_conversation(app_harness, project_id)
    run_resp = app_harness.client.post(
        "/agent-runs",
        json={
            "conversation_id": conversation["id"],
            "project_id": project_id,
            "purpose": "Command not found",
        },
    )
    run_id = str(run_resp.json()["id"])

    start_resp = app_harness.client.post(f"/agent-runs/{run_id}/start", json={"provider_kind": "codex_cli"})
    assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "failed"
        assert run.error_code == "owner_provider_command_not_found"
        assert run.error_category == "provider_runtime_unavailable"


def test_codex_structured_stdout_maps_timeout(app_harness: AppHarness) -> None:
    _configure_structured_stdout(app_harness, "import time; time.sleep(2)", timeout=0.01)
    _project_id, _conversation_id, run_id = _create_run(app_harness)

    start_resp = app_harness.client.post(f"/agent-runs/{run_id}/start", json={"provider_kind": "codex_cli"})
    assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "failed"
        assert run.error_code == "owner_provider_timeout"
        assert run.error_category == "timeout"


def test_codex_structured_stdout_maps_usage_limit_failure(app_harness: AppHarness) -> None:
    script = (
        "import sys; "
        "sys.stderr.write('ERROR: You have hit your usage limit. Try again at Jun 28th, 2026 8:09 PM.'); "
        "sys.exit(1)"
    )
    _configure_structured_stdout(app_harness, script)
    _project_id, _conversation_id, run_id = _create_run(app_harness)

    start_resp = app_harness.client.post(f"/agent-runs/{run_id}/start", json={"provider_kind": "codex_cli"})
    assert start_resp.status_code == 200

    with app_harness.session_factory() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status.value == "failed"
        assert run.error_code == "owner_provider_quota_exceeded"
        assert run.error_category == "quota_exceeded"
        assert run.retry_after == "Jun 28th, 2026 8:09 PM"
        assert run.provider_metadata_json["usage_limit"] is True
