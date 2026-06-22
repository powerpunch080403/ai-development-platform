from typing import Any

from sqlalchemy.orm import Session

from aidp_server.db.models import AuditEvent, AuditSeverity


def record_audit_event(
    session: Session,
    *,
    event_type: str,
    message: str,
    local_user_id: str | None,
    device_id: str | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    repository_id: str | None = None,
    conversation_id: str | None = None,
    agent_run_id: str | None = None,
    tool_call_id: str | None = None,
    severity: AuditSeverity = AuditSeverity.INFO,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        local_user_id=local_user_id,
        device_id=device_id,
        session_id=session_id,
        project_id=project_id,
        repository_id=repository_id,
        conversation_id=conversation_id,
        agent_run_id=agent_run_id,
        tool_call_id=tool_call_id,
        event_type=event_type,
        severity=severity,
        message=message,
        metadata_json=metadata,
    )
    session.add(event)
    return event
