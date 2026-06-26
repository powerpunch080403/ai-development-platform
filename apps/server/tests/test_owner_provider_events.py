import pytest

from aidp_server.owner.provider_events import (
    OwnerProviderEventParseError,
    parse_structured_stdout,
)


def test_parse_structured_stdout_accepts_single_object() -> None:
    events = parse_structured_stdout(
        '{"type":"assistant_message","content":"hello","metadata":{"source":"unit"}}'
    )

    assert len(events) == 1
    assert events[0].event_type == "assistant_message"
    assert events[0].content == "hello"
    assert events[0].metadata == {"source": "unit"}


def test_parse_structured_stdout_accepts_jsonl_tool_request() -> None:
    events = parse_structured_stdout(
        '{"type":"assistant_message","content":"planning"}\n'
        '{"type":"tool_request","tool_name":"task.create","arguments_json":{"title":"T"},"provider_call_id":"call-1"}'
    )

    assert [event.event_type for event in events] == ["assistant_message", "tool_request"]
    assert events[1].tool_name == "task.create"
    assert events[1].arguments_json == {"title": "T"}
    assert events[1].provider_call_id == "call-1"


def test_parse_structured_stdout_accepts_events_envelope() -> None:
    events = parse_structured_stdout(
        '{"events":[{"type":"error","error_code":"x","error_message":"bad"}]}'
    )

    assert len(events) == 1
    assert events[0].event_type == "error"
    assert events[0].error_code == "x"
    assert events[0].error_message == "bad"
    assert events[0].error_category == "provider_reported_error"


def test_parse_structured_stdout_rejects_malformed_jsonl() -> None:
    with pytest.raises(OwnerProviderEventParseError, match="not valid JSON"):
        parse_structured_stdout("not json")


def test_parse_structured_stdout_rejects_unknown_event_type() -> None:
    with pytest.raises(OwnerProviderEventParseError, match="unsupported provider event type"):
        parse_structured_stdout('{"type":"side_effect","path":"README.md"}')


def test_parse_structured_stdout_requires_tool_name_for_tool_request() -> None:
    with pytest.raises(OwnerProviderEventParseError, match="tool_name is required"):
        parse_structured_stdout('{"type":"tool_request","arguments_json":{}}')
