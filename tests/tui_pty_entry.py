"""Test-only launcher: registers an offline fake provider, then runs the real CLI."""
from __future__ import annotations

from cora.core.providers import register_provider
from cora.core.types import CompletionResponse, estimate_tokens, messages_tokens


@register_provider("pty_fake")
class PtyFakeProvider:
    def __init__(self, settings) -> None:
        pass

    async def complete(self, req):
        n = sum(1 for m in req.messages if m.role == "user"
                and m.content.startswith(("Task: ", "New request: ")))
        text = f"Final Answer: pong{n}"
        return CompletionResponse(
            text, messages_tokens(req.messages), estimate_tokens(text), req.model
        )


if __name__ == "__main__":
    from cora.cli.main import app

    app(prog_name="cora")
