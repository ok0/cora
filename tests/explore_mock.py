from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, ClassVar

from conftest import CFG_TOML, act
from cora.core.config import CoraConfig, parse_config
from cora.core.providers import register_provider
from cora.core.types import CompletionRequest, CompletionResponse, estimate_tokens, messages_tokens


@register_provider("explore_mock")
class ExploreMock:
    main: ClassVar[list] = []
    subs: ClassVar[dict[str, list]] = {}
    delays: ClassVar[dict[str, float]] = {}
    calls: ClassVar[list[CompletionRequest]] = []
    log: ClassVar[list[tuple[str, str]]] = []
    active: ClassVar[int] = 0
    peak: ClassVar[int] = 0
    usage: ClassVar[tuple[int, int] | None] = None

    def __init__(self, settings: Any) -> None:
        pass

    @classmethod
    def reset(cls) -> None:
        cls.main = []
        cls.subs = {}
        cls.delays = {}
        cls.calls = []
        cls.log = []
        cls.active = 0
        cls.peak = 0
        cls.usage = None

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        ExploreMock.calls.append(req)
        first = req.messages[1].content if len(req.messages) > 1 else ""
        task = first[len("Task: ") :] if first.startswith("Task: ") else None
        if task is not None and task in ExploreMock.subs:
            ExploreMock.active += 1
            ExploreMock.peak = max(ExploreMock.peak, ExploreMock.active)
            ExploreMock.log.append(("start", task))
            try:
                await asyncio.sleep(ExploreMock.delays.get(task, 0))
                queue = ExploreMock.subs[task]
                item = queue.pop(0) if queue else "Final Answer: (sub exhausted)"
            finally:
                ExploreMock.active -= 1
                ExploreMock.log.append(("end", task))
        else:
            item = ExploreMock.main.pop(0) if ExploreMock.main else "Final Answer: (main exhausted)"
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, CompletionResponse):
            resp = item
        else:
            resp = CompletionResponse(
                item, messages_tokens(req.messages), estimate_tokens(item), req.model
            )
        if ExploreMock.usage is not None:
            resp = dataclasses.replace(
                resp, input_tokens=ExploreMock.usage[0], output_tokens=ExploreMock.usage[1]
            )
        return resp


EXPLORE_TOML = CFG_TOML.replace('provider = "scripted"', 'provider = "explore_mock"')


def explore_config(
    delegation: dict | None = None,
    agent: dict | None = None,
    enabled: bool = True,
) -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "explore_mock",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "supports_tools": True,
                },
                {
                    "id": "mock/strong",
                    "provider": "explore_mock",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                    "supports_tools": True,
                },
            ],
            "agent": {"approval": "auto", **(agent or {})},
            "delegation": {"enabled": enabled, **(delegation or {})},
        }
    )


def explore(task: str) -> str:
    return act("delegate", {"task": task, "mode": "explore"})


def turn(*tasks: str) -> str:
    return "\n".join(explore(t) for t in tasks)
