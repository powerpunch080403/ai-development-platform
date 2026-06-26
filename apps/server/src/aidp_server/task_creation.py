from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.orm import Session

from aidp_server.db.models import (
    AgentRun,
    Conversation,
    Project,
    ProjectRepository,
    RiskLevel,
    Task,
    TaskStatus,
    WorkItem,
    WorkerKind,
)
from aidp_server.write_scope import normalize_write_scope


class TaskCreationError(ValueError):
    """Domain-level task creation failure shared by HTTP and Owner tool paths."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


@dataclass(frozen=True)
class TaskCreationRequest:
    local_user_id: str
    project_id: str | None
    title: str
    instructions: str
    repository_id: str | None = None
    work_item_id: str | None = None
    conversation_id: str | None = None
    agent_run_id: str | None = None
    created_by_session_id: str | None = None
    write_scope: Mapping[str, object] | None = None
    risk_level: RiskLevel | str = RiskLevel.R1
    requested_worker_kind: WorkerKind | str | None = None


def _owned(session: Session, model: type, object_id: str, user_id: str) -> Any:
    value = session.get(model, object_id)
    if value is None or getattr(value, "local_user_id", None) != user_id:
        raise TaskCreationError(
            "not_found",
            f"{model.__name__} not found",
            status_code=404,
        )
    return value


def _assert_same_project(value: Any, project_id: str, model_name: str) -> None:
    linked_project_id = getattr(value, "project_id", project_id)
    if linked_project_id != project_id:
        raise TaskCreationError(
            "project_mismatch",
            f"{model_name} belongs to another project",
        )


def _clean_required_text(value: str, field_name: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise TaskCreationError("invalid_arguments", f"{field_name} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise TaskCreationError("invalid_arguments", f"{field_name} is required")
    if len(cleaned) > max_length:
        raise TaskCreationError("invalid_arguments", f"{field_name} is too long")
    return cleaned


def _coerce_risk_level(value: RiskLevel | str) -> RiskLevel:
    if isinstance(value, RiskLevel):
        return value
    try:
        return RiskLevel(value)
    except ValueError:
        raise TaskCreationError("invalid_arguments", f"Unsupported risk_level: {value}")


def _coerce_worker_kind(value: WorkerKind | str | None) -> WorkerKind | None:
    if value is None or isinstance(value, WorkerKind):
        return value
    try:
        return WorkerKind(value)
    except ValueError:
        raise TaskCreationError(
            "invalid_arguments",
            f"Unsupported requested_worker_kind: {value}",
        )


def create_task_from_platform_request(
    session: Session,
    request: TaskCreationRequest,
) -> Task:
    """Create a Draft Task through the platform-owned Task creation boundary.

    This service is intentionally shared by the public HTTP API and Owner ToolCall
    execution so Owner providers cannot create a weaker Task path.
    """

    if not request.project_id:
        raise TaskCreationError("invalid_arguments", "project_id is required")

    project = _owned(session, Project, request.project_id, request.local_user_id)
    project_id = project.id

    title = _clean_required_text(request.title, "title", max_length=300)
    instructions = _clean_required_text(
        request.instructions,
        "instructions",
        max_length=100_000,
    )
    write_scope = normalize_write_scope(request.write_scope)

    for model, oid in (
        (ProjectRepository, request.repository_id),
        (WorkItem, request.work_item_id),
        (Conversation, request.conversation_id),
        (AgentRun, request.agent_run_id),
    ):
        if oid:
            linked = _owned(session, model, oid, request.local_user_id)
            _assert_same_project(linked, project_id, model.__name__)

    task = Task(
        local_user_id=request.local_user_id,
        project_id=project_id,
        repository_id=request.repository_id,
        work_item_id=request.work_item_id,
        conversation_id=request.conversation_id,
        agent_run_id=request.agent_run_id,
        created_by_session_id=request.created_by_session_id,
        title=title,
        instructions=instructions,
        write_scope_json=write_scope,
        status=TaskStatus.DRAFT,
        risk_level=_coerce_risk_level(request.risk_level),
        requested_worker_kind=_coerce_worker_kind(request.requested_worker_kind),
    )
    session.add(task)
    session.flush()
    return task
