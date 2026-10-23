from __future__ import annotations

import asyncio

from cora.core.agent import Agent
from cora.core.config import parse_config
from cora.core.providers import register_provider, registered_providers
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy
from cora.core.types import CompletionRequest, CompletionResponse


@register_provider("echo-mock")
class EchoMockProvider:
    def __init__(self, settings):
        pass

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse("Thought: easy\nFinal Answer: echo-ok", 1, 1, request.model)


def test_new_provider_without_core_changes(tmp_path):
    cfg = parse_config(
        {
            "models": [
                {
                    "id": "echo/cheap",
                    "provider": "echo-mock",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 1.0,
                },
                {
                    "id": "echo/strong",
                    "provider": "echo-mock",
                    "tier": "strong",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 1.0,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )
    r = asyncio.run(Agent(cfg, tmp_path, ApprovalPolicy("auto")).run("say hi"))
    assert r.answer == "echo-ok"
    assert r.stop_reason == StopReason.FINAL_ANSWER
    assert "echo-mock" in registered_providers()
