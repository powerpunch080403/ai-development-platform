from datetime import datetime, timezone
from sqlalchemy.orm import Session
from aidp_server.config import Settings
from aidp_server.db.models import AgentRun, AgentRunStatus
from aidp_server.audit import record_audit_event
import subprocess

class OwnerRuntimeProvider:
    provider_kind: str

    def __init__(self, settings: Settings):
        self.settings = settings

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        raise NotImplementedError()

class CodexCliOwnerProvider(OwnerRuntimeProvider):
    provider_kind = "codex_cli"

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        if not self.settings.allow_real_codex_owner_provider:
            # MVP Skeleton: Record invocation but do not actually execute Codex CLI loop yet.
            now = datetime.now(timezone.utc)
            run.status = AgentRunStatus.COMPLETED
            run.started_at = now
            run.completed_at = now

            record_audit_event(
                session,
                event_type="owner_runtime.skeleton_invoked",
                message="Codex CLI owner provider skeleton invoked; real bridge not implemented yet.",
                local_user_id=run.local_user_id,
                agent_run_id=run.id,
                project_id=run.project_id,
                metadata={
                    "provider_kind": self.provider_kind,
                    "skeleton": True,
                    "bridge_spike": False,
                    "real_provider_execution": False,
                    "tool_loop_executed": False,
                    "task_side_effects_performed": False,
                    "worker_side_effects_performed": False,
                    "approval_side_effects_performed": False,
                    "reason": "Real Codex CLI owner bridge disabled by config."
                }
            )
            return

        # Bridge Spike invocation
        now = datetime.now(timezone.utc)
        run.started_at = now
        
        # We will attempt a safe capability check
        # We don't send the user's prompt. We just run `codex --version` or `--help`.
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
            if exit_code == 0:
                codex_available = True
        except FileNotFoundError:
            stderr_val = "codex command not found"
        except subprocess.TimeoutExpired:
            stderr_val = "timeout expired"
            exit_code = -2

        now_completed = datetime.now(timezone.utc)
        run.completed_at = now_completed
        run.status = AgentRunStatus.COMPLETED

        record_audit_event(
            session,
            event_type="owner_runtime.bridge_spike_invoked",
            message="Codex CLI owner provider bridge spike invoked.",
            local_user_id=run.local_user_id,
            agent_run_id=run.id,
            project_id=run.project_id,
            metadata={
                "provider_kind": self.provider_kind,
                "bridge_spike": True,
                "real_provider_execution": False, # it's just a spike check
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
                "timeout_seconds": 10
            }
        )

class FakeOwnerProvider(OwnerRuntimeProvider):
    provider_kind = "fake"

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        now = datetime.now(timezone.utc)
        run.status = AgentRunStatus.COMPLETED
        run.started_at = now
        run.completed_at = now
        
        record_audit_event(
            session,
            event_type="owner_runtime.started",
            message="Owner Runtime started (fake)",
            local_user_id=run.local_user_id,
            agent_run_id=run.id,
            project_id=run.project_id,
            metadata={"provider_kind": self.provider_kind}
        )

def get_owner_provider(provider_kind: str, settings: Settings) -> OwnerRuntimeProvider:
    if provider_kind == "codex_cli":
        return CodexCliOwnerProvider(settings)
    elif provider_kind == "fake":
        return FakeOwnerProvider(settings)
    else:
        raise ValueError(f"Unknown owner provider kind: {provider_kind}")
