"""Gemini wrapper: schema conversion and tool-call response parsing.

These don't hit the real API (no key required to run the suite) — they
cover the exact bug classes hit while building this: nullable JSON Schema
types, a candidate with no content (safety filter / truncation), and a
missing function call in the response.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from google.genai import errors as genai_errors

from meetingpilot.extraction import EXTRACT_SCHEMA
from meetingpilot.llm import LLMError, _to_gemini_schema, call_tool
from meetingpilot.planning import PLAN_SCHEMA


def _server_error(status_code: int) -> genai_errors.ServerError:
    return genai_errors.ServerError(status_code, {"error": {"message": "unavailable"}})


def test_to_gemini_schema_converts_nullable_union_type():
    schema = {"type": ["string", "null"], "description": "maybe a string"}
    out = _to_gemini_schema(schema)
    assert out["type"] == "string"
    assert out["nullable"] is True


def test_to_gemini_schema_drops_additional_properties():
    schema = {"type": "object", "additionalProperties": False, "properties": {}}
    out = _to_gemini_schema(schema)
    assert "additionalProperties" not in out


def test_to_gemini_schema_handles_real_extract_schema():
    # The actual production schema — nested object -> array -> object with
    # several nullable ("type": [X, "null"]) fields.
    out = _to_gemini_schema(EXTRACT_SCHEMA)
    item_schema = out["properties"]["items"]["items"]
    assert item_schema["properties"]["owner"]["type"] == "string"
    assert item_schema["properties"]["owner"]["nullable"] is True
    assert "additionalProperties" not in item_schema


def test_to_gemini_schema_handles_real_plan_schema():
    out = _to_gemini_schema(PLAN_SCHEMA)
    item_schema = out["properties"]["items"]["items"]
    assert item_schema["properties"]["due_date_iso"]["nullable"] is True
    assert item_schema["properties"]["rank"]["type"] == "integer"


def _fake_response(candidates):
    return SimpleNamespace(candidates=candidates)


def _fake_function_call_part(name: str, args: dict):
    return SimpleNamespace(function_call=SimpleNamespace(name=name, args=args))


@patch("meetingpilot.llm.get_settings")
@patch("meetingpilot.llm.genai.Client")
def test_call_tool_returns_function_call_args(mock_client_cls, mock_get_settings):
    mock_get_settings.return_value = SimpleNamespace(
        gemini_api_key="fake-key", gemini_model="gemini-3.6-flash"
    )
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[_fake_function_call_part("my_tool", {"items": []})])
    )
    mock_client_cls.return_value.models.generate_content.return_value = _fake_response([candidate])

    result = call_tool(
        system="sys",
        user="user",
        tool_name="my_tool",
        tool_description="desc",
        input_schema={"type": "object", "properties": {}},
    )
    assert result == {"items": []}


@patch("meetingpilot.llm.time.sleep")
@patch("meetingpilot.llm.get_settings")
@patch("meetingpilot.llm.genai.Client")
def test_call_tool_raises_when_candidate_has_no_content(mock_client_cls, mock_get_settings, mock_sleep):
    """Regression: a safety-filtered or truncated response has content=None,
    which must not crash with AttributeError before LLMError can be raised.
    Also covers the retry-then-give-up path since this counts as a missing
    tool call, which now retries before raising."""
    mock_get_settings.return_value = SimpleNamespace(
        gemini_api_key="fake-key", gemini_model="gemini-3.6-flash"
    )
    candidate = SimpleNamespace(content=None)
    mock_client_cls.return_value.models.generate_content.return_value = _fake_response([candidate])

    with pytest.raises(LLMError, match="did not include the required tool call"):
        call_tool(
            system="sys",
            user="user",
            tool_name="my_tool",
            tool_description="desc",
            input_schema={"type": "object", "properties": {}},
        )
    assert mock_client_cls.return_value.models.generate_content.call_count == 3


@patch("meetingpilot.llm.time.sleep")
@patch("meetingpilot.llm.get_settings")
@patch("meetingpilot.llm.genai.Client")
def test_call_tool_raises_when_no_matching_function_call(mock_client_cls, mock_get_settings, mock_sleep):
    mock_get_settings.return_value = SimpleNamespace(
        gemini_api_key="fake-key", gemini_model="gemini-3.6-flash"
    )
    mock_client_cls.return_value.models.generate_content.return_value = _fake_response([])

    with pytest.raises(LLMError, match="did not include the required tool call"):
        call_tool(
            system="sys",
            user="user",
            tool_name="my_tool",
            tool_description="desc",
            input_schema={"type": "object", "properties": {}},
        )


@patch("meetingpilot.llm.time.sleep")
@patch("meetingpilot.llm.get_settings")
@patch("meetingpilot.llm.genai.Client")
def test_call_tool_retries_missing_function_call_then_succeeds(mock_client_cls, mock_get_settings, mock_sleep):
    """Regression for a real failure hit during testing: Gemini returned a
    successful response with no tool call on a large multi-item planning
    payload (likely truncation), not caught by the HTTP-error retry path."""
    mock_get_settings.return_value = SimpleNamespace(
        gemini_api_key="fake-key", gemini_model="gemini-3.6-flash"
    )
    good_candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[_fake_function_call_part("my_tool", {"ok": True})])
    )
    mock_client_cls.return_value.models.generate_content.side_effect = [
        _fake_response([SimpleNamespace(content=None)]),
        _fake_response([good_candidate]),
    ]

    result = call_tool(
        system="sys",
        user="user",
        tool_name="my_tool",
        tool_description="desc",
        input_schema={"type": "object", "properties": {}},
    )
    assert result == {"ok": True}
    assert mock_sleep.call_count == 1


@patch("meetingpilot.llm.get_settings")
def test_call_tool_raises_without_api_key(mock_get_settings):
    mock_get_settings.return_value = SimpleNamespace(gemini_api_key="", gemini_model="gemini-3.6-flash")

    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        call_tool(
            system="sys",
            user="user",
            tool_name="my_tool",
            tool_description="desc",
            input_schema={"type": "object", "properties": {}},
        )


@patch("meetingpilot.llm.time.sleep")
@patch("meetingpilot.llm.get_settings")
@patch("meetingpilot.llm.genai.Client")
def test_call_tool_retries_on_503_then_succeeds(mock_client_cls, mock_get_settings, mock_sleep):
    mock_get_settings.return_value = SimpleNamespace(
        gemini_api_key="fake-key", gemini_model="gemini-3.6-flash"
    )
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[_fake_function_call_part("my_tool", {"ok": True})])
    )
    mock_client_cls.return_value.models.generate_content.side_effect = [
        _server_error(503),
        _fake_response([candidate]),
    ]

    result = call_tool(
        system="sys",
        user="user",
        tool_name="my_tool",
        tool_description="desc",
        input_schema={"type": "object", "properties": {}},
    )
    assert result == {"ok": True}
    assert mock_sleep.call_count == 1


@patch("meetingpilot.llm.time.sleep")
@patch("meetingpilot.llm.get_settings")
@patch("meetingpilot.llm.genai.Client")
def test_call_tool_gives_up_after_max_retries(mock_client_cls, mock_get_settings, mock_sleep):
    mock_get_settings.return_value = SimpleNamespace(
        gemini_api_key="fake-key", gemini_model="gemini-3.6-flash"
    )
    mock_client_cls.return_value.models.generate_content.side_effect = _server_error(503)

    with pytest.raises(genai_errors.ServerError):
        call_tool(
            system="sys",
            user="user",
            tool_name="my_tool",
            tool_description="desc",
            input_schema={"type": "object", "properties": {}},
        )


@patch("meetingpilot.llm.time.sleep")
@patch("meetingpilot.llm.get_settings")
@patch("meetingpilot.llm.genai.Client")
def test_call_tool_does_not_retry_non_retryable_errors(mock_client_cls, mock_get_settings, mock_sleep):
    mock_get_settings.return_value = SimpleNamespace(
        gemini_api_key="fake-key", gemini_model="gemini-3.6-flash"
    )
    mock_client_cls.return_value.models.generate_content.side_effect = _server_error(500)

    with pytest.raises(genai_errors.ServerError):
        call_tool(
            system="sys",
            user="user",
            tool_name="my_tool",
            tool_description="desc",
            input_schema={"type": "object", "properties": {}},
        )
    assert mock_sleep.call_count == 0
