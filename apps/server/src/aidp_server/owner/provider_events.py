from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


PROVIDER_EVENT_PROTOCOL_VERSION = "owner_provider_events.v1"


class OwnerProviderEventParseError(ValueError):
    """Raised when provider structured output cannot be mapped to platform events."""


@dataclass(frozen=True)
class OwnerProviderEvent:
    event_type: str
    content: str | None = None
    tool_name: str | None = None
    arguments_json: dict[str, Any] = field(default_factory=dict)
    provider_call_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_category: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _event_type(raw: dict[str, Any], index: int) -> str:
    value = raw.get("type") or raw.get("event_type")
    if not isinstance(value, str) or not value.strip():
        raise OwnerProviderEventParseError(f"event[{index}] is missing type")
    return value.strip()


def _object(value: Any, *, field_name: str, index: int) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise OwnerProviderEventParseError(f"event[{index}].{field_name} must be an object")
    return dict(value)


def _normalise_event(raw: Any, index: int) -> OwnerProviderEvent:
    if not isinstance(raw, dict):
        raise OwnerProviderEventParseError(f"event[{index}] must be an object")

    event_type = _event_type(raw, index)
    metadata = _object(raw.get("metadata"), field_name="metadata", index=index)

    if event_type == "assistant_message":
        content = raw.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OwnerProviderEventParseError(
                f"event[{index}].content is required for assistant_message"
            )
        return OwnerProviderEvent(
            event_type=event_type,
            content=content,
            metadata=metadata,
        )

    if event_type == "tool_request":
        tool_name = raw.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise OwnerProviderEventParseError(
                f"event[{index}].tool_name is required for tool_request"
            )

        arguments = raw.get("arguments_json", raw.get("arguments", {}))
        arguments_json = _object(arguments, field_name="arguments_json", index=index)

        provider_call_id = raw.get("provider_call_id")
        if provider_call_id is not None and not isinstance(provider_call_id, str):
            provider_call_id = str(provider_call_id)

        return OwnerProviderEvent(
            event_type=event_type,
            tool_name=tool_name.strip(),
            arguments_json=arguments_json,
            provider_call_id=provider_call_id,
            metadata=metadata,
        )

    if event_type == "error":
        error_message = raw.get("error_message") or raw.get("message")
        if not isinstance(error_message, str) or not error_message.strip():
            raise OwnerProviderEventParseError(
                f"event[{index}].error_message is required for error"
            )

        error_code = raw.get("error_code")
        if error_code is not None and not isinstance(error_code, str):
            error_code = str(error_code)

        error_category = raw.get("error_category")
        if error_category is not None and not isinstance(error_category, str):
            error_category = str(error_category)

        return OwnerProviderEvent(
            event_type=event_type,
            error_code=error_code or "owner_provider_reported_error",
            error_message=error_message,
            error_category=error_category or "provider_reported_error",
            metadata=metadata,
        )

    raise OwnerProviderEventParseError(f"unsupported provider event type: {event_type}")


def _load_structured_payload(text: str) -> list[Any]:
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        events: list[Any] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError as error:
                raise OwnerProviderEventParseError(
                    f"line {line_number} is not valid JSON: {error.msg}"
                ) from error
        return events

    if isinstance(loaded, dict) and isinstance(loaded.get("events"), list):
        return list(loaded["events"])
    if isinstance(loaded, list):
        return loaded
    if isinstance(loaded, dict):
        return [loaded]

    raise OwnerProviderEventParseError("structured output must be an object, array, or JSONL")


def parse_structured_stdout(stdout: str) -> list[OwnerProviderEvent]:
    text = stdout.strip()
    if not text:
        raise OwnerProviderEventParseError("structured output is empty")

    raw_events = _load_structured_payload(text)
    if not raw_events:
        raise OwnerProviderEventParseError("structured output contains no events")

    return [_normalise_event(raw_event, index) for index, raw_event in enumerate(raw_events)]
