"""Test-only launcher: registers an offline fake provider, then runs the real CLI.

Environment knobs (all optional):
- CORA_FAKE_SCRIPT: JSON file holding a list of replies; each call pops the first one.
- CORA_FAKE_DEFAULT: reply used once the script is empty (default "Final Answer: done").
- CORA_FAKE_DELAY: seconds to sleep inside each call (lets a test send a signal mid-run).
- CORA_FAKE_READY: file written with "ready" at the start of each call.
- CORA_FAKE_STRAY=1: every tool execution first prints a line to stdout.
- CORA_FAKE_LOG: file; each call appends one JSON line {"task": <first user message>}.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from cora.core.providers import register_provider
from cora.core.types import CompletionResponse, estimate_tokens, messages_tokens


def _next_reply() -> str:
    script = os.environ.get("CORA_FAKE_SCRIPT")
    if script:
        path = Path(script)
        items = json.loads(path.read_text(encoding="utf-8"))
        if items:
            reply = items.pop(0)
            path.write_text(json.dumps(items), encoding="utf-8")
            return reply
    return os.environ.get("CORA_FAKE_DEFAULT", "Final Answer: done")


@register_provider("headless_fake")
class HeadlessFake:
    def __init__(self, settings) -> None:
        pass

    async def complete(self, req):
        log = os.environ.get("CORA_FAKE_LOG")
        if log:
            task = next((m.content for m in req.messages if m.role == "user"), "")
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"task": task}) + "\n")
        ready = os.environ.get("CORA_FAKE_READY")
        if ready:
            Path(ready).write_text("ready", encoding="utf-8")
        delay = float(os.environ.get("CORA_FAKE_DELAY", "0") or 0)
        if delay > 0:
            await asyncio.sleep(delay)
        text = _next_reply()
        return CompletionResponse(
            text, messages_tokens(req.messages), estimate_tokens(text), req.model
        )


if os.environ.get("CORA_FAKE_STRAY") == "1":
    from cora.core.tools.registry import ToolRegistry

    _original_execute = ToolRegistry._execute_tool

    async def _noisy_execute(self, tool, name, args, ctx):
        print(f"STRAY-PRINT {name}")
        return await _original_execute(self, tool, name, args, ctx)

    ToolRegistry._execute_tool = _noisy_execute


if __name__ == "__main__":
    from cora.cli.main import app

    app(prog_name="cora")
