from types import SimpleNamespace
import json
from pathlib import Path

from aidp_server.config import Settings
from aidp_server.owner.provider_session import (
    OWNER_PROVIDER_RPC_VERSION,
    OWNER_PROVIDER_SESSION_PROTOCOL_VERSION,
    OwnerProviderSessionStore,
    json_rpc_notification,
    json_rpc_request,
    json_rpc_result,
)


def test_json_rpc_envelope_helpers_are_transport_neutral() -> None:
    request = json_rpc_request("req-1", "owner.tool.request", {"tool_name": "task.create"})
    notification = json_rpc_notification("owner.assistant.message", {"content": "hello"})
    result = json_rpc_result("req-1", {"tool_status": "succeeded"})

    assert request == {
        "jsonrpc": OWNER_PROVIDER_RPC_VERSION,
        "id": "req-1",
        "method": "owner.tool.request",
        "params": {"tool_name": "task.create"},
    }
    assert notification == {
        "jsonrpc": OWNER_PROVIDER_RPC_VERSION,
        "method": "owner.assistant.message",
        "params": {"content": "hello"},
    }
    assert result == {
        "jsonrpc": OWNER_PROVIDER_RPC_VERSION,
        "id": "req-1",
        "result": {"tool_status": "succeeded"},
    }


def test_owner_provider_session_store_writes_replayable_artifacts(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, app_data_dir=tmp_path)  # type: ignore[call-arg]
    run = SimpleNamespace(
        id="run-1",
        conversation_id="conversation-1",
        project_id="project-1",
        local_user_id="user-1",
    )
    store = OwnerProviderSessionStore(settings)

    artifacts = store.start_session(
        run,
        provider_kind="codex_cli",
        owner_context={"context_version": "owner_context.v1"},
        context_summary={"tool_count": 4},
    )
    store.append_event(
        artifacts,
        json_rpc_notification("owner.assistant.message", {"content": "hello"}),
    )
    store.append_tool_result(
        artifacts,
        request_id="req-1",
        tool_call_id="tool-call-1",
        tool_name="task.create",
        tool_status="succeeded",
        result_json={"task_id": "task-1"},
    )
    store.record_raw_output(artifacts, stdout="provider stdout", stderr="provider stderr")
    store.write_final_state(artifacts, status="completed", metadata={"ok": True})

    session_json = json.loads(Path(artifacts.session_json_path).read_text(encoding="utf-8"))
    input_context = json.loads(Path(artifacts.input_context_path).read_text(encoding="utf-8"))
    event_lines = Path(artifacts.events_jsonl_path).read_text(encoding="utf-8").splitlines()
    tool_result_lines = Path(artifacts.tool_results_jsonl_path).read_text(encoding="utf-8").splitlines()
    final_state = json.loads(Path(artifacts.final_state_path).read_text(encoding="utf-8"))

    assert session_json["protocol"] == OWNER_PROVIDER_SESSION_PROTOCOL_VERSION
    assert session_json["agent_run_id"] == "run-1"
    assert input_context["owner_context"]["context_version"] == "owner_context.v1"
    assert len(event_lines) == 2
    assert json.loads(event_lines[0])["method"] == "owner.assistant.message"
    assert json.loads(event_lines[1])["method"] == "owner.tool.result"
    assert len(tool_result_lines) == 1
    assert json.loads(tool_result_lines[0])["result"]["tool_call_id"] == "tool-call-1"
    assert Path(artifacts.stdout_log_path).read_text(encoding="utf-8") == "provider stdout"
    assert Path(artifacts.stderr_log_path).read_text(encoding="utf-8") == "provider stderr"
    assert final_state["status"] == "completed"
