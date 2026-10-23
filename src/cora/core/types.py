from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class NativeToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text as returned by the model
    extra_content: dict[str, Any] | None = field(default=None, hash=False)


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    tool_calls: tuple[NativeToolCall, ...] = ()
    tool_call_id: str | None = None
    extra_content: dict[str, Any] | None = field(default=None, hash=False)


DEFAULT_REACT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    messages: list[Message]
    max_tokens: int = DEFAULT_REACT_MAX_TOKENS
    temperature: float = 0.0
    stop: list[str] | None = None
    tools: list[dict] | None = None
    response_format: dict | None = None
    cache_prefix: bool = False


@dataclass(frozen=True)
class CompletionResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    tool_calls: tuple[NativeToolCall, ...] = ()
    cost_usd: float | None = None
    cached_input_tokens: int = 0
    extra_content: dict[str, Any] | None = field(default=None, hash=False)
    finish_reason: str | None = field(default=None, compare=False)
    replayed: bool = field(default=False, compare=False)


def estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def messages_tokens(messages: Sequence[Message]) -> int:
    return sum(
        estimate_tokens(m.content + "".join(c.name + c.arguments for c in m.tool_calls)) + 4
        for m in messages
    )
