from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from cora.core.types import Message

NATIVE_EMPTY_REPLY = (
    "Observation: empty response. Call a tool, or reply with your final answer as plain text."
)


def decode_arguments(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    if not raw.strip():
        return {}, None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON arguments ({e.msg} at char {e.pos})"
    if not isinstance(obj, dict):
        return None, "arguments must be a JSON object"
    return obj, None


def flatten_tool_messages(messages: Sequence[Message]) -> list[Message]:
    out: list[Message] = []
    for m in messages:
        if m.role == "tool":
            out.append(Message("user", f"Observation: {m.content}"))
        elif m.tool_calls:
            parts = ([m.content] if m.content else []) + [
                f"Action: {c.name}\nAction Input: {c.arguments or '{}'}" for c in m.tool_calls
            ]
            out.append(Message("assistant", "\n".join(parts), extra_content=m.extra_content))
        else:
            out.append(m)
    return out
