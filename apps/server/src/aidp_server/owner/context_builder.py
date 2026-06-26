from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidp_server.action_policy import ACTION_CATALOG
from aidp_server.db.models import (
    AgentRun,
    Conversation,
    Message,
    Project,
    ProjectRepository,
    Task,
    TaskAttempt,
)


CONTEXT_VERSION = "owner_context.v1"
MAX_CONTEXT_MESSAGES = 12
MAX_CONTEXT_TASKS = 20
MAX_CONTEXT_ATTEMPTS_PER_TASK = 3
MAX_CONTEXT_REPOSITORIES = 20


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


def _message_view(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": _enum_value(message.role),
        "content": message.content,
        "content_type": _enum_value(message.content_type),
        "created_at": _iso(message.created_at),
        "agent_run_id": message.agent_run_id,
    }


def _project_view(project: Project | None) -> dict[str, Any] | None:
    if project is None:
        return None
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": _enum_value(project.status),
        "created_at": _iso(project.created_at),
        "updated_at": _iso(project.updated_at),
        "archived_at": _iso(project.archived_at),
    }


def _repository_view(repository: ProjectRepository) -> dict[str, Any]:
    return {
        "id": repository.id,
        "project_id": repository.project_id,
        "repository_name": repository.repository_name,
        "repository_path": repository.repository_path,
        "repository_role": _enum_value(repository.repository_role),
        "vcs_type": _enum_value(repository.vcs_type),
        "default_branch": repository.default_branch,
        "current_branch": repository.current_branch,
        "last_commit_sha": repository.last_commit_sha,
        "is_dirty": repository.is_dirty,
        "last_status_checked_at": _iso(repository.last_status_checked_at),
    }


def _attempt_view(attempt: TaskAttempt) -> dict[str, Any]:
    return {
        "id": attempt.id,
        "task_id": attempt.task_id,
        "project_id": attempt.project_id,
        "repository_id": attempt.repository_id,
        "status": _enum_value(attempt.status),
        "attempt_number": attempt.attempt_number,
        "claimed_by_worker_id": attempt.claimed_by_worker_id,
        "result_summary": attempt.result_summary,
        "error_code": attempt.error_code,
        "created_at": _iso(attempt.created_at),
        "updated_at": _iso(attempt.updated_at),
    }


def _task_view(session: Session, task: Task) -> dict[str, Any]:
    attempts = session.scalars(
        select(TaskAttempt)
        .where(TaskAttempt.task_id == task.id)
        .order_by(TaskAttempt.attempt_number.desc())
        .limit(MAX_CONTEXT_ATTEMPTS_PER_TASK)
    ).all()
    return {
        "id": task.id,
        "project_id": task.project_id,
        "repository_id": task.repository_id,
        "work_item_id": task.work_item_id,
        "conversation_id": task.conversation_id,
        "agent_run_id": task.agent_run_id,
        "title": task.title,
        "instructions": task.instructions,
        "write_scope": task.write_scope_json,
        "status": _enum_value(task.status),
        "risk_level": _enum_value(task.risk_level),
        "requested_worker_kind": _enum_value(task.requested_worker_kind),
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
        "attempts": [_attempt_view(attempt) for attempt in attempts],
    }


def _tool_definitions() -> list[dict[str, Any]]:
    from aidp_server.owner_tools import ALLOWED_OWNER_TOOLS, READ_ONLY_OWNER_TOOLS

    definitions: list[dict[str, Any]] = []
    for action in ACTION_CATALOG:
        if not action.enabled_in_tool_registry or action.action_type not in ALLOWED_OWNER_TOOLS:
            continue
        definitions.append(
            {
                "tool_name": action.action_type,
                "risk_level": action.risk_level,
                "description": action.description,
                "has_side_effect": action.action_type not in READ_ONLY_OWNER_TOOLS,
                "approval_behavior": (
                    "approval_required" if action.requires_approval else "policy"
                ),
            }
        )
    return sorted(definitions, key=lambda item: item["tool_name"])


def _conversation_context(session: Session, run: AgentRun) -> dict[str, Any] | None:
    if not run.conversation_id:
        return None
    conversation = session.get(Conversation, run.conversation_id)
    if conversation is None or conversation.local_user_id != run.local_user_id:
        return None

    messages_desc = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .where(Message.local_user_id == run.local_user_id)
        .order_by(Message.created_at.desc())
        .limit(MAX_CONTEXT_MESSAGES)
    ).all()
    messages = list(reversed(messages_desc))

    return {
        "id": conversation.id,
        "project_id": conversation.project_id,
        "title": conversation.title,
        "status": _enum_value(conversation.status),
        "created_at": _iso(conversation.created_at),
        "updated_at": _iso(conversation.updated_at),
        "latest_messages": [_message_view(message) for message in messages],
    }


def _repositories_context(session: Session, run: AgentRun) -> list[dict[str, Any]]:
    query = (
        select(ProjectRepository)
        .where(ProjectRepository.local_user_id == run.local_user_id)
        .where(ProjectRepository.archived_at.is_(None))
    )
    if run.project_id:
        query = query.where(ProjectRepository.project_id == run.project_id)
    repositories = session.scalars(
        query.order_by(ProjectRepository.created_at.asc()).limit(MAX_CONTEXT_REPOSITORIES)
    ).all()
    return [_repository_view(repository) for repository in repositories]


def _tasks_context(session: Session, run: AgentRun) -> list[dict[str, Any]]:
    query = select(Task).where(Task.local_user_id == run.local_user_id)
    if run.project_id:
        query = query.where(Task.project_id == run.project_id)
    tasks = session.scalars(query.order_by(Task.created_at.desc()).limit(MAX_CONTEXT_TASKS)).all()
    return [_task_view(session, task) for task in tasks]


def _authority_summary() -> dict[str, Any]:
    return {
        "mode": "personal",
        "owner_judgment_replaced": False,
        "tool_call_authority_envelope_required": True,
        "autonomy_profile": "not_configured",
        "approval_modes_planned": [
            "ask_for_approval",
            "approve_on_my_behalf",
            "full_access",
            "custom",
        ],
    }


def build_owner_context(session: Session, run: AgentRun) -> dict[str, Any]:
    project = None
    if run.project_id:
        candidate = session.get(Project, run.project_id)
        if candidate is not None and candidate.local_user_id == run.local_user_id:
            project = candidate

    return {
        "context_version": CONTEXT_VERSION,
        "provider_agnostic": True,
        "agent_run": {
            "id": run.id,
            "conversation_id": run.conversation_id,
            "project_id": run.project_id,
            "local_user_id": run.local_user_id,
            "purpose": run.purpose,
            "status": _enum_value(run.status),
            "input_message_id": run.input_message_id,
            "provider_kind": run.provider_kind,
        },
        "project": _project_view(project),
        "conversation": _conversation_context(session, run),
        "repositories": _repositories_context(session, run),
        "tasks": _tasks_context(session, run),
        "tool_definitions": _tool_definitions(),
        "authority": _authority_summary(),
    }


def summarize_owner_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "context_version": context.get("context_version"),
        "provider_agnostic": context.get("provider_agnostic"),
        "project_id": (context.get("project") or {}).get("id"),
        "conversation_id": (context.get("conversation") or {}).get("id"),
        "repository_count": len(context.get("repositories") or []),
        "task_count": len(context.get("tasks") or []),
        "tool_count": len(context.get("tool_definitions") or []),
        "authority_mode": (context.get("authority") or {}).get("mode"),
    }
