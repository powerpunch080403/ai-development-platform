from datetime import datetime, timezone
import re
import shlex
import subprocess

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidp_server.audit import record_audit_event
from aidp_server.config import Settings
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


def codex_usage_limit_message(stderr: str) -> str | None:
    if "usage limit" not in stderr.lower():
        return None
    match = CODEX_USAGE_LIMIT_RESET_RE.search(stderr)
    if match:
        reset_at = match.group(1).strip()
        return f"Codex usage limit reached. Try again at {reset_at}."
    return "Codex usage limit reached. Try again later."


class OwnerRuntimeProvider:
    provider_kind: str

    def __init__(self, settings: Settings):
        self.settings = settings

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        raise NotImplementedError()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _mark_failed(
        self,
        session: Session,
        run: AgentRun,
        *,
        error_code: str,
        error_message: str,
        event_type: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        now = self._now()
        run.status = AgentRunStatus.FAILED
        run.started_at = run.started_at or now
        run.failed_at = now
        run.error_code = error_code
        run.error_message = error_message
        record_audit_event(
            session,
            event_type=event_type,
            message=error_message,
            local_user_id=run.local_user_id,
            agent_run_id=run.id,
            conversation_id=run.conversation_id,
            project_id=run.project_id,
            metadata={"provider_kind": self.provider_kind, **(metadata or {})},
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
        run.status = AgentRunStatus.COMPLETED
        run.started_at = run.started_at or now
        run.completed_at = now
        run.failed_at = None
        run.error_code = None
        run.error_message = None
        record_audit_event(
            session,
            event_type=event_type,
            message=message,
            local_user_id=run.local_user_id,
            agent_run_id=run.id,
            conversation_id=run.conversation_id,
            project_id=run.project_id,
            metadata={"provider_kind": self.provider_kind, **(metadata or {})},
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
                error_message="Owner runtime is not connected yet. Codex CLI Owner bridge is disabled by config.",
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
        if mode == "prompt":
            self._run_prompt(session, run)
            return

        self._mark_failed(
            session,
            run,
            error_code="owner_provider_invalid_mode",
            error_message=f"Unsupported Codex CLI Owner mode: {self.settings.codex_cli_mode}",
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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
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
            message="Codex CLI owner provider bridge spike invoked.",
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
                timeout=self.settings.codex_cli_timeout_seconds,
            )
        except FileNotFoundError:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_command_not_found",
                error_message=f"Owner CLI command not found: {self.settings.codex_cli_command}",
                event_type="owner_runtime.command_not_found",
                metadata={"command": self.settings.codex_cli_command, "mode": "prompt"},
            )
            return
        except subprocess.TimeoutExpired:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_timeout",
                error_message="Owner CLI command timed out.",
                event_type="owner_runtime.timeout",
                metadata={"command": self.settings.codex_cli_command, "mode": "prompt"},
            )
            return

        stdout_val = result.stdout.strip()
        stderr_val = result.stderr.strip()
        if result.returncode != 0:
            usage_limit_message = codex_usage_limit_message(stderr_val)
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_usage_limit" if usage_limit_message else "owner_provider_failed",
                error_message=usage_limit_message
                or stderr_val[:4000]
                or f"Owner CLI exited with code {result.returncode}.",
                event_type="owner_runtime.prompt_failed",
                metadata={
                    "command": self.settings.codex_cli_command,
                    "args": args,
                    "exit_code": result.returncode,
                    "stdout_excerpt": stdout_val[:500],
                    "stderr_excerpt": stderr_val[:500],
                    "mode": "prompt",
                    "usage_limit": usage_limit_message is not None,
                },
            )
            return

        if not stdout_val:
            self._mark_failed(
                session,
                run,
                error_code="owner_provider_empty_response",
                error_message="Owner CLI completed without producing a response.",
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
            message="Owner CLI provider completed prompt execution.",
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
            error_message=f"Owner provider is not implemented yet: {self.provider_kind}",
            event_type="owner_runtime.provider_not_implemented",
            metadata={"real_provider_execution": False},
        )


class FakeOwnerProvider(OwnerRuntimeProvider):
    provider_kind = "fake"

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        self._complete_run(
            session,
            run,
            event_type="owner_runtime.started",
            message="Owner Runtime started (fake)",
            metadata={"fake": True},
        )


def get_owner_provider(provider_kind: str, settings: Settings) -> OwnerRuntimeProvider:
    if provider_kind == "codex_cli":
        return CodexCliOwnerProvider(settings)
    if provider_kind == "fake":
        return FakeOwnerProvider(settings)
    if provider_kind in {"openai_api", "local_ai"}:
        return NotImplementedOwnerProvider(settings, provider_kind)
    raise ValueError(f"Unknown owner provider kind: {provider_kind}")
