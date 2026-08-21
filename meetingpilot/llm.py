"""Thin Gemini client wrapper. Both LLM layers use this module."""

from __future__ import annotations

import time
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from meetingpilot.config import get_settings

RETRYABLE_STATUS_CODES = {503, 429}
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


class LLMError(RuntimeError):
    """Raised when the model does not return a usable tool call."""


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a JSON Schema dict to Gemini's OpenAPI-subset Schema shape.

    Differences that matter here:
    - No `additionalProperties` support — dropped.
    - Nullable fields use JSON Schema's `type: [X, "null"]`; Gemini wants
      `type: X` plus a separate `nullable: true`.
    """
    if not isinstance(schema, dict):
        return schema

    out: dict[str, Any] = {}
    type_value = schema.get("type")
    if isinstance(type_value, list):
        non_null = [t for t in type_value if t != "null"]
        out["type"] = non_null[0] if non_null else "string"
        if "null" in type_value:
            out["nullable"] = True
    elif type_value is not None:
        out["type"] = type_value

    for key in ("description", "enum", "minimum", "maximum", "required"):
        if key in schema:
            out[key] = schema[key]

    if "properties" in schema:
        out["properties"] = {k: _to_gemini_schema(v) for k, v in schema["properties"].items()}
    if "items" in schema:
        out["items"] = _to_gemini_schema(schema["items"])

    return out


def call_tool(
    *,
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
    images: list[tuple[bytes, str]] | None = None,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    """Force a structured tool call and return the tool input JSON.

    `images` is an optional list of (raw_bytes, mime_type) pairs, sent as
    real image content blocks alongside the text — used by the multimodal
    extraction call for screenshots.
    """
    _, payload = call_tool_choice(
        system=system,
        user=user,
        tools=[
            {"name": tool_name, "description": tool_description, "schema": input_schema}
        ],
        images=images,
        max_tokens=max_tokens,
    )
    return payload


def call_tool_choice(
    *,
    system: str,
    user: str,
    tools: list[dict[str, Any]],
    images: list[tuple[bytes, str]] | None = None,
    max_tokens: int = 8192,
) -> tuple[str, dict[str, Any]]:
    """Force exactly one tool call, chosen by the model from several options.

    `tools` is a list of {"name", "description", "schema"} dicts. Returns
    (name_of_tool_called, tool_input_json) so the caller can branch on which
    one the model picked -- e.g. offering both "apply this structured edit"
    and "just reply in plain text" and letting the model decide which fits
    the user's message, rather than forcing every message through one
    schema.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMError(
            "GEMINI_API_KEY is missing. Copy .env.example to .env and add a key."
        )

    client = genai.Client(api_key=settings.gemini_api_key)
    function_declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=_to_gemini_schema(t["schema"]),
        )
        for t in tools
    ]
    tool = types.Tool(function_declarations=function_declarations)
    allowed_names = [t["name"] for t in tools]

    contents: Any = user
    if images:
        contents = [user] + [
            types.Part.from_bytes(data=data, mime_type=mime_type) for data, mime_type in images
        ]

    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        tools=[tool],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode="ANY",
                allowed_function_names=allowed_names,
            )
        ),
    )

    # Gemini's free tier returns transient 503 (overloaded) / 429 (rate
    # limit) fairly often — retry a few times with backoff rather than
    # letting one blip fail a live demo. Also retry when a *successful*
    # response is missing the tool call: observed in practice on large
    # multi-item planning payloads, most likely truncation before the
    # function call args finished — not an HTTP error, so it needs its
    # own retry path, not just the APIError one below.
    last_finish_reason = None
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=settings.gemini_model, contents=contents, config=config
            )
        except genai_errors.APIError as exc:
            status = getattr(exc, "code", None)
            if status not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
            continue

        for candidate in response.candidates or []:
            parts = candidate.content.parts if candidate.content else None
            for part in parts or []:
                fn_call = getattr(part, "function_call", None)
                if fn_call and fn_call.name in allowed_names:
                    return fn_call.name, (dict(fn_call.args) if fn_call.args else {})
            last_finish_reason = getattr(candidate, "finish_reason", None)

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

    raise LLMError(
        "Model response did not include the required tool call "
        f"after {MAX_RETRIES} attempts (last finish_reason: {last_finish_reason})."
    )
