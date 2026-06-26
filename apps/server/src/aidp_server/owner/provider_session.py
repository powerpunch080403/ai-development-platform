from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from aidp_server.config import Settings


OWNER_PROVIDER_SESSION_PROTOCOL_VERSION = "owner_provider_session.v1"
OWNER_PROVIDER_RPC_VERSION = "2.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_rpc_request(
    request_id: str,
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "jsonrpc": OWNER_PROVIDER_RPC_VERSION,
        "id": request_id,
        "method": method,
    }
    if params is not None:
        envelope["params"] = params
    return envelope


def json_rpc_notification(
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "jsonrpc": OWNER_PROVIDER_RPC_VERSION,
        "method": method,
    }
    if params is not None:
        envelope["params"] = params
    return envelope


def json_rpc_result(request_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": OWNER_PROVIDER_RPC_VERSION,
        "id": request_id,
        "result": result,
    }


def json_rpc_error(
    request_id: str | None,
    *,
    code: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "jsonrpc": OWNER_PROVIDER_RPC_VERSION,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if request_id is not None:
        envelope["id"] = request_id
    if data is not None:
        envelope["error"]["data"] = data
    return envelope


@dataclass(frozen=True)
class OwnerProviderSessionArtifacts:
    session_id: str
    session_dir: str
    session_json_path: str
    input_context_path: str
    events_jsonl_path: str
    tool_results_jsonl_path: str
    stdout_log_path: str
    stderr_log_path: str
    final_state_path: str

    def as_metadata(self) -> dict[str, str]:
        return {
            "protocol": OWNER_PROVIDER_SESSION_PROTOCOL_VERSION,
            "rpc_version": OWNER_PROVIDER_RPC_VERSION,
            "session_id": self.session_id,
            "session_dir": self.session_dir,
            "session_json_path": self.session_json_path,
            "input_context_path": self.input_context_path,
            "events_jsonl_path": self.events_jsonl_path,
            "tool_results_jsonl_path": self.tool_results_jsonl_path,
            "stdout_log_path": self.stdout_log_path,
            "stderr_log_path": self.stderr_log_path,
            "final_state_path": self.final_state_path,
        }

    def as_prompt_context(self) -> dict[str, object]:
        return {
            "protocol": OWNER_PROVIDER_SESSION_PROTOCOL_VERSION,
            "rpc_version": OWNER_PROVIDER_RPC_VERSION,
            "session_id": self.session_id,
            "artifacts": {
                "events_jsonl": self.events_jsonl_path,
                "tool_results_jsonl": self.tool_results_jsonl_path,
                "stdout_log": self.stdout_log_path,
                "stderr_log": self.stderr_log_path,
            },
        }


class OwnerProviderSessionStore:
    def __init__(self, settings: Settings):
        self.settings = settings

    def artifacts_for(self, run: Any) -> OwnerProviderSessionArtifacts:
        session_id = f"owner-run-{run.id}"
        session_dir = self.settings.app_data_dir_path / "owner-sessions" / str(run.id)
        return OwnerProviderSessionArtifacts(
            session_id=session_id,
            session_dir=str(session_dir),
            session_json_path=str(session_dir / "session.json"),
            input_context_path=str(session_dir / "input_context.json"),
            events_jsonl_path=str(session_dir / "events.jsonl"),
            tool_results_jsonl_path=str(session_dir / "tool_results.jsonl"),
            stdout_log_path=str(session_dir / "provider_stdout.log"),
            stderr_log_path=str(session_dir / "provider_stderr.log"),
            final_state_path=str(session_dir / "final_state.json"),
        )

    def start_session(
        self,
        run: Any,
        *,
        provider_kind: str,
        owner_context: dict[str, Any],
        context_summary: dict[str, Any],
    ) -> OwnerProviderSessionArtifacts:
        artifacts = self.artifacts_for(run)
        session_dir = Path(artifacts.session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)

        self._write_json(
            Path(artifacts.session_json_path),
            {
                "protocol": OWNER_PROVIDER_SESSION_PROTOCOL_VERSION,
                "rpc_version": OWNER_PROVIDER_RPC_VERSION,
                "session_id": artifacts.session_id,
                "agent_run_id": run.id,
                "conversation_id": run.conversation_id,
                "project_id": run.project_id,
                "local_user_id": run.local_user_id,
                "provider_kind": provider_kind,
                "created_at": _utc_now_iso(),
                "context_summary": context_summary,
                "artifacts": artifacts.as_metadata(),
            },
        )
        self._write_json(
            Path(artifacts.input_context_path),
            {
                "protocol": OWNER_PROVIDER_SESSION_PROTOCOL_VERSION,
                "session_id": artifacts.session_id,
                "owner_context": owner_context,
            },
        )

        Path(artifacts.events_jsonl_path).touch()
        Path(artifacts.tool_results_jsonl_path).touch()
        Path(artifacts.stdout_log_path).touch()
        Path(artifacts.stderr_log_path).touch()
        return artifacts

    def append_event(self, artifacts: OwnerProviderSessionArtifacts, envelope: dict[str, Any]) -> None:
        self._append_json_line(Path(artifacts.events_jsonl_path), envelope)

    def append_provider_event(
        self,
        artifacts: OwnerProviderSessionArtifacts,
        *,
        event_index: int,
        provider_event: Any,
    ) -> str:
        request_id = provider_event.provider_call_id or f"provider-event-{event_index}"
        if provider_event.event_type == "assistant_message":
            envelope = json_rpc_notification(
                "owner.assistant.message",
                {
                    "event_index": event_index,
                    "content": provider_event.content,
                    "metadata": provider_event.metadata,
                },
            )
        elif provider_event.event_type == "tool_request":
            envelope = json_rpc_request(
                request_id,
                "owner.tool.request",
                {
                    "event_index": event_index,
                    "tool_name": provider_event.tool_name,
                    "arguments_json": provider_event.arguments_json,
                    "provider_call_id": provider_event.provider_call_id,
                    "metadata": provider_event.metadata,
                },
            )
        elif provider_event.event_type == "error":
            envelope = json_rpc_error(
                request_id,
                code=provider_event.error_code or "owner_provider_reported_error",
                message=provider_event.error_message or "Owner provider reported an error.",
                data={
                    "event_index": event_index,
                    "error_category": provider_event.error_category,
                    "metadata": provider_event.metadata,
                },
            )
        else:
            envelope = json_rpc_notification(
                "owner.provider.unknown_event",
                {
                    "event_index": event_index,
                    "event_type": provider_event.event_type,
                },
            )

        self.append_event(artifacts, envelope)
        return request_id

    def append_tool_result(
        self,
        artifacts: OwnerProviderSessionArtifacts,
        *,
        request_id: str,
        tool_call_id: str,
        tool_name: str,
        tool_status: str,
        result_json: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        result = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tool_status": tool_status,
            "result_json": result_json or {},
            "error_code": error_code,
            "error_message": error_message,
        }
        envelope = json_rpc_result(request_id, result)
        self._append_json_line(Path(artifacts.tool_results_jsonl_path), envelope)
        self.append_event(
            artifacts,
            json_rpc_notification(
                "owner.tool.result",
                {
                    "request_id": request_id,
                    **result,
                },
            ),
        )

    def record_raw_output(
        self,
        artifacts: OwnerProviderSessionArtifacts,
        *,
        stdout: str,
        stderr: str,
    ) -> None:
        Path(artifacts.stdout_log_path).write_text(stdout, encoding="utf-8")
        Path(artifacts.stderr_log_path).write_text(stderr, encoding="utf-8")

    def write_final_state(
        self,
        artifacts: OwnerProviderSessionArtifacts,
        *,
        status: str,
        metadata: dict[str, Any],
    ) -> None:
        self._write_json(
            Path(artifacts.final_state_path),
            {
                "protocol": OWNER_PROVIDER_SESSION_PROTOCOL_VERSION,
                "session_id": artifacts.session_id,
                "status": status,
                "completed_at": _utc_now_iso(),
                "metadata": metadata,
            },
        )

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )

    def _append_json_line(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
