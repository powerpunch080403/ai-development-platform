from datetime import datetime, timezone
from sqlalchemy.orm import Session
from aidp_server.db.models import AgentRun, AgentRunStatus
from aidp_server.audit import record_audit_event

class OwnerRuntimeProvider:
    provider_kind: str

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        raise NotImplementedError()

class CodexCliOwnerProvider(OwnerRuntimeProvider):
    provider_kind = "codex_cli"

    def start_agent_run(self, session: Session, run: AgentRun) -> None:
        # MVP Skeleton: Record invocation but do not actually execute Codex CLI loop yet.
        # Ensure it doesn't bypass any boundaries.
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
                "real_provider_execution": False,
                "tool_loop_executed": False,
                "reason": "Codex CLI owner provider skeleton invoked; real bridge not implemented yet."
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

def get_owner_provider(provider_kind: str) -> OwnerRuntimeProvider:
    if provider_kind == "codex_cli":
        return CodexCliOwnerProvider()
    elif provider_kind == "fake":
        return FakeOwnerProvider()
    else:
        raise ValueError(f"Unknown owner provider kind: {provider_kind}")
