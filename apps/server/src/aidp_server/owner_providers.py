from dataclasses import dataclass
import json
from datetime import datetime, timezone
import re
import shlex
import subprocess

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidp_server.audit import record_audit_event
from aidp_server.config import Settings
from aidp_server.owner.context_builder import build_owner_context, summarize_owner_context
from aidp_server.owner.provider_events import (
    PROVIDER_EVENT_PROTOCOL_VERSION,
    OwnerProviderEventParseError,
    parse_structured_stdout,
)
from aidp_server.owner.provider_session import (
    OWNER_PROVIDER_SESSION_PROTOCOL_VERSION,
    OwnerProviderSessionArtifacts,
    OwnerProviderSessionStore,
)
from aidp_server.db.models import (
    AgentRun,
    AgentRunStatus,
    AgentRunStep,
    AgentRunStepType,
    ContentType,
    Message,
    MessageRole,
    RecordStatus,
)

SUPPORTED_OWNER_PROVIDER_KINDS = {"codex_cli", "openai_api", "local_ai", "fake"}
CODEX_USAGE_LIMIT_RESET_RE = re.compile(r"try again at\s+(.+?)(?:\.|\n|$)", re.IGNORECASE)


@dataclass(frozen=True)
class OwnerProviderError:
    error_code: str
    error_category: str
    user_message: str
    provider_message: str | None = None
    retry_after: str | None = None
    metadata: dict[str, object] | None = None


def codex_usage_limit_error(stderr: str) -> OwnerProviderError | None:
    if "usage limit" not in stderr.lower():
        return None

    match = CODEX_USAGE_LIMIT_RESET_RE.search(stderr)
    retry_after = match.group(1).strip() if match and match.group(1) else None
    user_message = (
        f"Owner provider quota exceeded. Try again at {retry_after}."
        if retry_after
        else "Owner provider quota exceeded. Try again later."
    )
    return OwnerProviderError(
        error_code="owner_provider_quota_exceeded",
        error_category="quota_exceeded",
        user_message=user_message,
        provider_message=stderr[:4000],
        retry_after=retry_after,
        metadata={"usage_limit": True},
    )


class OwnerRuntimeProvider:
    provider_kind: str

    def __init__(self, settings: Settings):
        self.settings = settings

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        raise NotImplementedError()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _metadata(self, metadata: dict[str, object] | None = None) -> dict[str, object]:
        return {"provider_kind": self.provider_kind, **(metadata or {})}

    def _mark_failed(
        self,
        session: Session,
        run: AgentRun,
        *,
        error_code: str,
        error_message: str,
        event_type: str,
        error_category: str = "provider_error",
        retry_after: str | None = None,
        provider_message: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        now = self._now()
        provider_metadata = self._metadata(metadata)
        if provider_message:
            provider_metadata["provider_message"] = provider_message

        run.provider_kind = self.provider_kind
        run.status = AgentRunStatus.FAILED
        run.started_at = run.started_at or now
        run.failed_at = now
        run.error_code = error_code
        run.error_category = error_category
        run.error_message = error_message
        run.retry_after = retry_after
        run.provider_metadata_json = provider_metadata

        record_audit_event(
            session,
            event_type=event_type,
            message=error_message,
            local_user_id=run.local_user_id,
            agent_run_id=run.id,
            conversation_id=run.conversation_id,
            project_id=run.project_id,
            metadata=provider_metadata,
        )

    def _complete_run(
        self,
        session: Session,
        run: AgentRun,
        *,
        event_type: str,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        now = self._now()
        provider_metadata = self._metadata(metadata)

        run.provider_kind = self.provider_kind
        run.status = AgentRunStatus.COMPLETED
        run.started_at = run.started_at or now
        run.completed_at = now
        run.failed_at = None
        run.error_code = None
        run.error_category = None
        run.error_message = None
        run.retry_after = None
        run.provider_metadata_json = provider_metadata

        record_audit_event(
            session,
            event_type=event_type,
            message=message,
            local_user_id=run.local_user_id,
            agent_run_id=run.id,
            conversation_id=run.conversation_id,
            project_id=run.project_id,
            metadata=provider_metadata,
        )

    def _next_step_index(self, session: Session, run: AgentRun) -> int:
        return (
            session.scalar(
                select(func.max(AgentRunStep.step_index)).where(AgentRunStep.agent_run_id == run.id)
            )
            or -1
        ) + 1

    def _record_completed_model_step(self, session: Session, run: AgentRun, summary: str) -> None:
        now = self._now()
        session.add(
            AgentRunStep(
                agent_run_id=run.id,
                step_index=self._next_step_index(session, run),
                step_type=AgentRunStepType.MODEL,
                status=RecordStatus.SUCCEEDED,
                summary=summary,
                started_at=now,
                completed_at=now,
            )
        )

    def _input_prompt(self, session: Session, run: AgentRun) -> str:
        if run.input_message_id:
            message = session.get(Message, run.input_message_id)
            if message is not None and message.local_user_id == run.local_user_id:
                return message.content
        return run.purpose

    def _append_assistant_message(self, session: Session, run: AgentRun, content: str) -> Message | None:
        if not run.conversation_id:
            return None
        message = Message(
            conversation_id=run.conversation_id,
            local_user_id=run.local_user_id,
            agent_run_id=run.id,
            role=MessageRole.ASSISTANT,
            content=content,
            content_type=ContentType.TEXT,
        )
        session.add(message)
        return message


class CodexCliOwnerProvider(OwnerRuntimeProvider):
    provider_kind = "codex_cli"

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        if not self.settings.allow_real_codex_owner_provider:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_not_connected",
                error_category="provider_not_connected",
                error_message="Owner runtime provider is not connected yet.",
                event_type="owner_runtime.skeleton_invoked",
                metadata={
                    "skeleton": True,
                    "bridge_spike": False,
                    "real_provider_execution": False,
                    "tool_loop_executed": False,
                    "task_side_effects_performed": False,
                    "worker_side_effects_performed": False,
                    "approval_side_effects_performed": False,
                    "reason": "Real Codex CLI owner bridge disabled by config.",
                },
            )
            return

        mode = self.settings.codex_cli_mode.strip().lower()
        if mode == "bridge_spike":
            self._run_bridge_spike(session, run)
            return
        if mode == "structured_stdout":
            self._run_structured_stdout(session, run)
            return
        if mode == "prompt":
            self._run_prompt(session, run)
            return

        self._mark_failed(
            session,
            run,
            error_code="owner_provider_invalid_mode",
            error_category="provider_configuration_error",
            error_message=f"Unsupported Owner provider mode: {self.settings.codex_cli_mode}",
            event_type="owner_runtime.invalid_mode",
            metadata={"mode": self.settings.codex_cli_mode},
        )

    def _run_bridge_spike(self, session: Session, run: AgentRun) -> None:
        run.started_at = self._now()
        cmd = [self.settings.codex_cli_command, "--version"]
        stdout_val = ""
        stderr_val = ""
        exit_code = -1
        codex_available = False

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            exit_code = result.returncode
            stdout_val = result.stdout[:500]
            stderr_val = result.stderr[:500]
            codex_available = exit_code == 0
        except FileNotFoundError:
            stderr_val = "codex command not found"
        except subprocess.TimeoutExpired:
            stderr_val = "timeout expired"
            exit_code = -2

        self._complete_run(
            session,
            run,
            event_type="owner_runtime.bridge_spike_invoked",
            message="Owner provider bridge spike invoked.",
            metadata={
                "bridge_spike": True,
                "real_provider_execution": False,
                "tool_loop_executed": False,
                "task_side_effects_performed": False,
                "worker_side_effects_performed": False,
                "approval_side_effects_performed": False,
                "codex_cli_command": self.settings.codex_cli_command,
                "codex_cli_available": codex_available,
                "codex_cli_version": stdout_val.strip() if codex_available else None,
                "exit_code": exit_code,
                "stdout_excerpt": stdout_val,
                "stderr_excerpt": stderr_val,
                "timeout_seconds": 10,
            },
        )

    def _structured_prompt(
        self,
        session: Session,
        run: AgentRun,
    ) -> tuple[str, dict[str, object], OwnerProviderSessionArtifacts]:
        owner_context = build_owner_context(session, run)
        context_summary = summarize_owner_context(owner_context)
        session_artifacts = OwnerProviderSessionStore(self.settings).start_session(
            run,
            provider_kind=self.provider_kind,
            owner_context=owner_context,
            context_summary=context_summary,
        )
        payload = {
            "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
            "session_protocol": OWNER_PROVIDER_SESSION_PROTOCOL_VERSION,
            "session": session_artifacts.as_prompt_context(),
            "instructions": [
                "Respond only with JSONL or a JSON object/array using this protocol.",
                "Use assistant_message for user-visible text.",
                "Use tool_request when platform side effects or platform reads are needed.",
                "Do not mutate files, git, worktrees, database rows, approvals, or workers directly.",
                "The platform will execute tool_request events through the Owner ToolCall bridge.",
                "The platform records provider events and tool results in the Owner provider session log.",
            ],
            "event_schemas": {
                "assistant_message": {
                    "type": "assistant_message",
                    "content": "text to show the user",
                },
                "tool_request": {
                    "type": "tool_request",
                    "tool_name": "task.create",
                    "arguments_json": {},
                    "provider_call_id": "optional stable provider id",
                },
                "error": {
                    "type": "error",
                    "error_code": "provider_reported_error",
                    "error_message": "provider-visible failure",
                    "error_category": "provider_reported_error",
                },
            },
            "owner_context": owner_context,
        }
        prompt = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return prompt, context_summary, session_artifacts

    def _run_structured_stdout(self, session: Session, run: AgentRun) -> None:
        from aidp_server.owner_tool_loop import OwnerToolRequest, request_tool_from_owner_provider

        prompt, context_summary, session_artifacts = self._structured_prompt(session, run)
        session_store = OwnerProviderSessionStore(self.settings)
        session_metadata = session_artifacts.as_metadata()
        args = shlex.split(self.settings.codex_cli_prompt_args)
        cmd = [self.settings.codex_cli_command, *args]
        run.started_at = self._now()

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.codex_cli_timeout_seconds,
            )
        except FileNotFoundError:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_command_not_found",
                error_category="provider_runtime_unavailable",
                error_message=f"Owner provider command not found: {self.settings.codex_cli_command}",
                event_type="owner_runtime.structured_command_not_found",
                metadata={
                    "command": self.settings.codex_cli_command,
                    "mode": "structured_stdout",
                    "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                    "owner_context": context_summary,
                    "owner_provider_session": session_metadata,
                },
            )
            return
        except subprocess.TimeoutExpired:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_timeout",
                error_category="timeout",
                error_message="Owner provider command timed out.",
                event_type="owner_runtime.structured_timeout",
                metadata={
                    "command": self.settings.codex_cli_command,
                    "mode": "structured_stdout",
                    "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                    "timeout_seconds": self.settings.codex_cli_timeout_seconds,
                    "owner_context": context_summary,
                    "owner_provider_session": session_metadata,
                },
            )
            return

        stdout_val = (result.stdout or "").strip()
        stderr_val = (result.stderr or "").strip()
        session_store.record_raw_output(
            session_artifacts,
            stdout=stdout_val,
            stderr=stderr_val,
        )

        if result.returncode != 0:
            quota_error = codex_usage_limit_error(stderr_val)
            if quota_error:
                self._mark_failed(
                    session,
                    run,
                    error_code=quota_error.error_code,
                    error_category=quota_error.error_category,
                    error_message=quota_error.user_message,
                    retry_after=quota_error.retry_after,
                    provider_message=quota_error.provider_message,
                    event_type="owner_runtime.structured_failed",
                    metadata={
                        "command": self.settings.codex_cli_command,
                        "args": args,
                        "exit_code": result.returncode,
                        "stdout_excerpt": stdout_val[:500],
                        "stderr_excerpt": stderr_val[:500],
                        "mode": "structured_stdout",
                        "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                        "owner_context": context_summary,
                    "owner_provider_session": session_metadata,
                        **(quota_error.metadata or {}),
                    },
                )
                return

            error_message = stderr_val[:4000] or f"Owner provider exited with code {result.returncode}."
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_failed",
                error_category="provider_error",
                error_message=error_message,
                provider_message=stderr_val[:4000] if stderr_val else None,
                event_type="owner_runtime.structured_failed",
                metadata={
                    "command": self.settings.codex_cli_command,
                    "args": args,
                    "exit_code": result.returncode,
                    "stdout_excerpt": stdout_val[:500],
                    "stderr_excerpt": stderr_val[:500],
                    "mode": "structured_stdout",
                    "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                    "owner_context": context_summary,
                    "owner_provider_session": session_metadata,
                    "usage_limit": False,
                },
            )
            return

        if not stdout_val:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_empty_response",
                error_category="empty_response",
                error_message="Owner provider completed without producing a structured response.",
                event_type="owner_runtime.structured_empty_response",
                metadata={
                    "command": self.settings.codex_cli_command,
                    "args": args,
                    "mode": "structured_stdout",
                    "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                    "owner_context": context_summary,
                    "owner_provider_session": session_metadata,
                },
            )
            return

        try:
            events = parse_structured_stdout(stdout_val)
        except OwnerProviderEventParseError as error:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_malformed_tool_output",
                error_category="malformed_tool_output",
                error_message="Owner provider produced malformed structured output.",
                provider_message=str(error),
                event_type="owner_runtime.structured_malformed_output",
                metadata={
                    "command": self.settings.codex_cli_command,
                    "args": args,
                    "mode": "structured_stdout",
                    "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                    "stdout_excerpt": stdout_val[:500],
                    "stderr_excerpt": stderr_val[:500],
                    "owner_context": context_summary,
                    "owner_provider_session": session_metadata,
                },
            )
            return

        tool_call_ids: list[str] = []
        assistant_message_count = 0
        task_side_effects_performed = False

        for index, event in enumerate(events):
            provider_request_id = session_store.append_provider_event(
                session_artifacts,
                event_index=index,
                provider_event=event,
            )
            if event.event_type == "assistant_message":
                self._append_assistant_message(session, run, event.content or "")
                self._record_completed_model_step(
                    session,
                    run,
                    "Owner provider produced a structured assistant message.",
                )
                assistant_message_count += 1
                continue

            if event.event_type == "error":
                self._mark_failed(
                    session,
                    run,
                    error_code=event.error_code or "owner_provider_reported_error",
                    error_category=event.error_category or "provider_reported_error",
                    error_message=event.error_message or "Owner provider reported an error.",
                    event_type="owner_runtime.structured_provider_error",
                    metadata={
                        "mode": "structured_stdout",
                        "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                        "event_index": index,
                        "provider_event_metadata": event.metadata,
                        "owner_context": context_summary,
                    "owner_provider_session": session_metadata,
                    },
                )
                return

            if event.event_type == "tool_request":
                call = request_tool_from_owner_provider(
                    session,
                    run,
                    provider_kind=self.provider_kind,
                    request=OwnerToolRequest(
                        tool_name=event.tool_name or "",
                        arguments_json=event.arguments_json,
                        provider_call_id=event.provider_call_id,
                        metadata={
                            "source": "codex_structured_stdout",
                            "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                            "event_index": index,
                            "provider_event_metadata": event.metadata,
                        },
                    ),
                )
                tool_call_ids.append(call.id)
                session_store.append_tool_result(
                    session_artifacts,
                    request_id=provider_request_id,
                    tool_call_id=call.id,
                    tool_name=event.tool_name or "",
                    tool_status=call.status.value,
                    result_json=call.result_json,
                    error_code=call.error_code,
                    error_message=call.error_message,
                )

                if call.status.value != "succeeded":
                    session_store.write_final_state(
                        session_artifacts,
                        status="failed",
                        metadata={
                            "error_code": call.error_code or "owner_tool_call_failed",
                            "tool_call_id": call.id,
                            "tool_name": event.tool_name,
                        },
                    )
                    self._mark_failed(
                        session,
                        run,
                        error_code=call.error_code or "owner_tool_call_failed",
                        error_category="tool_call_failed",
                        error_message=call.error_message or f"Owner tool call failed: {event.tool_name}",
                        event_type="owner_runtime.structured_tool_failed",
                        metadata={
                            "mode": "structured_stdout",
                            "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                            "event_index": index,
                            "tool_call_id": call.id,
                            "tool_name": event.tool_name,
                            "tool_status": call.status.value,
                            "owner_context": context_summary,
                    "owner_provider_session": session_metadata,
                        },
                    )
                    return

                if event.tool_name == "task.create":
                    task_side_effects_performed = True
                continue

        session_store.write_final_state(
            session_artifacts,
            status="completed",
            metadata={
                "event_count": len(events),
                "assistant_message_count": assistant_message_count,
                "tool_call_ids": tool_call_ids,
            },
        )
        self._complete_run(
            session,
            run,
            event_type="owner_runtime.structured_completed",
            message="Owner provider completed structured stdout execution.",
            metadata={
                "real_provider_execution": True,
                "mode": "structured_stdout",
                "protocol": PROVIDER_EVENT_PROTOCOL_VERSION,
                "event_count": len(events),
                "assistant_message_count": assistant_message_count,
                "tool_loop_executed": bool(tool_call_ids),
                "tool_call_ids": tool_call_ids,
                "task_side_effects_performed": task_side_effects_performed,
                "worker_side_effects_performed": False,
                "approval_side_effects_performed": False,
                "tool_result_delivery": "not_supported_by_structured_stdout_one_shot",
                "command": self.settings.codex_cli_command,
                "args": args,
                "exit_code": result.returncode,
                "stdout_excerpt": stdout_val[:500],
                "stderr_excerpt": stderr_val[:500],
                "owner_context": context_summary,
                "owner_provider_session": session_metadata,
            },
        )

    def _run_prompt(self, session: Session, run: AgentRun) -> None:
        prompt = self._input_prompt(session, run)
        args = shlex.split(self.settings.codex_cli_prompt_args)
        cmd = [self.settings.codex_cli_command, *args]
        run.started_at = self._now()

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.codex_cli_timeout_seconds,
            )
        except FileNotFoundError:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_command_not_found",
                error_category="provider_runtime_unavailable",
                error_message=f"Owner provider command not found: {self.settings.codex_cli_command}",
                event_type="owner_runtime.command_not_found",
                metadata={"command": self.settings.codex_cli_command, "mode": "prompt"},
            )
            return
        except subprocess.TimeoutExpired:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_timeout",
                error_category="timeout",
                error_message="Owner provider command timed out.",
                event_type="owner_runtime.timeout",
                metadata={"command": self.settings.codex_cli_command, "mode": "prompt"},
            )
            return

        stdout_val = result.stdout.strip()
        stderr_val = result.stderr.strip()
        if result.returncode != 0:
            quota_error = codex_usage_limit_error(stderr_val)
            if quota_error:
                metadata = {
                    "command": self.settings.codex_cli_command,
                    "args": args,
                    "exit_code": result.returncode,
                    "stdout_excerpt": stdout_val[:500],
                    "stderr_excerpt": stderr_val[:500],
                    "mode": "prompt",
                    **(quota_error.metadata or {}),
                }
                self._mark_failed(
                    session,
                    run,
                    error_code=quota_error.error_code,
                    error_category=quota_error.error_category,
                    error_message=quota_error.user_message,
                    retry_after=quota_error.retry_after,
                    provider_message=quota_error.provider_message,
                    event_type="owner_runtime.prompt_failed",
                    metadata=metadata,
                )
                return

            error_message = stderr_val[:4000] or f"Owner provider exited with code {result.returncode}."
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_failed",
                error_category="provider_error",
                error_message=error_message,
                provider_message=stderr_val[:4000] if stderr_val else None,
                event_type="owner_runtime.prompt_failed",
                metadata={
                    "command": self.settings.codex_cli_command,
                    "args": args,
                    "exit_code": result.returncode,
                    "stdout_excerpt": stdout_val[:500],
                    "stderr_excerpt": stderr_val[:500],
                    "mode": "prompt",
                    "usage_limit": False,
                },
            )
            return

        if not stdout_val:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_empty_response",
                error_category="empty_response",
                error_message="Owner provider completed without producing a response.",
                event_type="owner_runtime.empty_response",
                metadata={"command": self.settings.codex_cli_command, "args": args, "mode": "prompt"},
            )
            return

        self._append_assistant_message(session, run, stdout_val)
        self._record_completed_model_step(session, run, "Owner provider produced an assistant response.")
        self._complete_run(
            session,
            run,
            event_type="owner_runtime.prompt_completed",
            message="Owner provider completed prompt execution.",
            metadata={
                "real_provider_execution": True,
                "tool_loop_executed": False,
                "task_side_effects_performed": False,
                "worker_side_effects_performed": False,
                "approval_side_effects_performed": False,
                "command": self.settings.codex_cli_command,
                "args": args,
                "exit_code": result.returncode,
                "stdout_excerpt": stdout_val[:500],
                "stderr_excerpt": stderr_val[:500],
                "mode": "prompt",
            },
        )


class NotImplementedOwnerProvider(OwnerRuntimeProvider):
    provider_kind = "not_implemented"

    def __init__(self, settings: Settings, provider_kind: str):
        super().__init__(settings)
        self.provider_kind = provider_kind

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        self._mark_failed(
            session,
            run,
            error_code="owner_provider_not_implemented",
            error_category="provider_not_implemented",
            error_message=f"Owner provider is not implemented yet: {self.provider_kind}",
            event_type="owner_runtime.provider_not_implemented",
            metadata={"real_provider_execution": False},
        )


class FakeOwnerProvider(OwnerRuntimeProvider):
    provider_kind = "fake"

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        owner_context = build_owner_context(session, run)
        context_summary = summarize_owner_context(owner_context)

        scripted_request = (run.provider_metadata_json or {}).get("scripted_tool_request")
        if isinstance(scripted_request, dict):
            self._run_scripted_tool_request(session, run, scripted_request, context_summary)
            return

        self._complete_run(
            session,
            run,
            event_type="owner_runtime.started",
            message="Owner Runtime started (fake)",
            metadata={
                "fake": True,
                "tool_loop_executed": False,
                "task_side_effects_performed": False,
                "worker_side_effects_performed": False,
                "approval_side_effects_performed": False,
                "owner_context": context_summary,
            },
        )

    def _run_scripted_tool_request(
        self,
        session: Session,
        run: AgentRun,
        scripted_request: dict[str, object],
        context_summary: dict[str, object],
    ) -> None:
        from aidp_server.owner_tool_loop import OwnerToolRequest, request_tool_from_owner_provider

        tool_name = scripted_request.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            self._mark_failed(
                session,
                run,
                error_code="fake_provider_invalid_script",
                error_category="provider_configuration_error",
                error_message="Fake provider scripted_tool_request.tool_name is required.",
                event_type="owner_runtime.fake_script_invalid",
                metadata={
                    "fake": True,
                    "tool_loop_executed": False,
                    "owner_context": context_summary,
                },
            )
            return

        raw_arguments = scripted_request.get("arguments_json", {})
        if not isinstance(raw_arguments, dict):
            self._mark_failed(
                session,
                run,
                error_code="fake_provider_invalid_script",
                error_category="provider_configuration_error",
                error_message="Fake provider scripted_tool_request.arguments_json must be an object.",
                event_type="owner_runtime.fake_script_invalid",
                metadata={
                    "fake": True,
                    "tool_loop_executed": False,
                    "owner_context": context_summary,
                },
            )
            return

        provider_call_id = scripted_request.get("provider_call_id")
        if provider_call_id is not None and not isinstance(provider_call_id, str):
            provider_call_id = str(provider_call_id)

        call = request_tool_from_owner_provider(
            session,
            run,
            provider_kind=self.provider_kind,
            request=OwnerToolRequest(
                tool_name=tool_name,
                arguments_json=raw_arguments,
                provider_call_id=provider_call_id,
                metadata={
                    "source": "fake_scripted_provider",
                    "owner_context": context_summary,
                },
            ),
        )

        if call.status.value != "succeeded":
            self._mark_failed(
                session,
                run,
                error_code=call.error_code or "owner_tool_call_failed",
                error_category="tool_call_failed",
                error_message=call.error_message or f"Owner tool call failed: {tool_name}",
                event_type="owner_runtime.fake_script_failed",
                metadata={
                    "fake": True,
                    "tool_loop_executed": True,
                    "tool_call_id": call.id,
                    "tool_name": tool_name,
                    "tool_status": call.status.value,
                    "task_side_effects_performed": False,
                    "worker_side_effects_performed": False,
                    "approval_side_effects_performed": False,
                },
            )
            return

        result_json = call.result_json or {}
        self._complete_run(
            session,
            run,
            event_type="owner_runtime.fake_script_completed",
            message="Owner Runtime completed fake scripted tool request.",
            metadata={
                "fake": True,
                "tool_loop_executed": True,
                "tool_call_id": call.id,
                "tool_name": tool_name,
                "tool_status": call.status.value,
                "task_id": result_json.get("task_id"),
                "task_side_effects_performed": tool_name == "task.create",
                "worker_side_effects_performed": False,
                "approval_side_effects_performed": False,
                "owner_context": context_summary,
            },
        )


def get_owner_provider(provider_kind: str, settings: Settings) -> OwnerRuntimeProvider:
    if provider_kind == "codex_cli":
        return CodexCliOwnerProvider(settings)
    if provider_kind == "fake":
        return FakeOwnerProvider(settings)
    if provider_kind in {"openai_api", "local_ai"}:
        return NotImplementedOwnerProvider(settings, provider_kind)
    raise ValueError(f"Unknown owner provider kind: {provider_kind}")
