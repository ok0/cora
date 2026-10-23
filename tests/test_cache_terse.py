from __future__ import annotations

import json

from cora.core.delegation import DelegateTool
from cora.core.tools.base import ToolResult
from cora.core.tools.builtin import default_tools
from cora.core.tools.mcp import McpTool
from cora.core.tools.plan import SubmitPlanTool
from cora.core.tools.registry import FALLBACK_PARAMETERS, ToolRegistry, terse_text
from cora.core.types import estimate_tokens


async def _dummy(task: str) -> ToolResult:
    return ToolResult(False, "unused")


ALL = [*default_tools(), SubmitPlanTool(), DelegateTool(_dummy)]


def _old_schema_description(t) -> str:
    return getattr(t, "native_description", None) or f"{t.description} Args: {t.args_doc}"


def test_every_builtin_has_short_terse():
    for t in ALL:
        terse = getattr(t, "terse_description", None)
        assert terse, t.name
        assert len(terse) <= 60, t.name
        assert len(terse) < len(t.description), t.name


def test_full_identical_to_pre_m6():
    reg = ToolRegistry(ALL)
    assert reg.describe() == "\n".join(
        f"- {t.name}: {t.description} Args: {t.args_doc}" for t in ALL
    )
    assert reg.schemas() == [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": _old_schema_description(t),
                "parameters": getattr(t, "parameters", None) or FALLBACK_PARAMETERS,
            },
        }
        for t in ALL
    ]


def test_terse_paths():
    reg = ToolRegistry(ALL)
    full = reg.schemas()
    terse = reg.schemas(terse=True)
    assert len(terse) == len(full)
    for f, s in zip(full, terse, strict=True):
        assert len(s["function"]["description"]) <= 60
        assert s["function"]["name"] == f["function"]["name"]
        assert s["function"]["parameters"] == f["function"]["parameters"]
    lines = reg.describe(terse=True).split("\n")
    assert len(lines) == len(ALL)
    for t, line in zip(ALL, lines, strict=True):
        assert line == f"- {t.name}: {terse_text(t)} Args: {t.args_doc}"


def test_terse_tokens_lower():
    reg = ToolRegistry(ALL)
    assert estimate_tokens(reg.describe(terse=True)) < estimate_tokens(reg.describe())
    assert estimate_tokens(json.dumps(reg.schemas(terse=True))) < estimate_tokens(
        json.dumps(reg.schemas())
    )


def test_mcp_truncated():
    mcp = McpTool(None, "srv", "t", "mcp_srv_t", "D" * 200, {"type": "object", "properties": {}})
    reg = ToolRegistry([mcp])
    terse_desc = reg.schemas(terse=True)[0]["function"]["description"]
    assert len(terse_desc) <= 60
    assert terse_desc.endswith("…")
    assert terse_text(mcp).endswith("…")
    assert len(terse_text(mcp)) <= 60
    assert reg.describe(terse=True).startswith("- mcp_srv_t: " + terse_text(mcp))
    assert reg.schemas()[0]["function"]["description"] == "D" * 200
