"""Thin Anthropic client wrapper. Both LLM layers use this module."""

from __future__ import annotations

import json
from typing import Any

from anthropic import Anthropic

from meetingpilot.config import get_settings


class LLMError(RuntimeError):
    """Raised when the model does not return a usable tool call."""


def call_tool(
    *,
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Force a structured tool call and return the tool input JSON."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise LLMError(
            "ANTHROPIC_API_KEY is missing. Copy .env.example to .env and add a key."
        )

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system,
        tools=[
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user}],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            payload = block.input
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, dict):
                raise LLMError("Tool payload was not a JSON object.")
            return payload

    raise LLMError("Model response did not include the required tool call.")
