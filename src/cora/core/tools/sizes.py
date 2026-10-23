from __future__ import annotations

import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from cora.core.toolgroups import (
    GROUPS,
    OPTIONAL_GROUPS,
    auto_hidden_groups,
    excluded_tools,
    group_of,
)
from cora.core.tools.builtin import default_tools
from cora.core.tools.plan import SubmitPlanTool
from cora.core.tools.registry import ToolRegistry

SIMPLE_SAMPLE = "list the files here"


@dataclass(frozen=True)
class PromptSize:
    describe_chars: int
    schema_chars: int

    @property
    def describe_tokens(self) -> int:
        return self.describe_chars // 4

    @property
    def schema_tokens(self) -> int:
        return self.schema_chars // 4


def measure(registry: ToolRegistry, exclude: Collection[str] = frozenset()) -> PromptSize:
    return PromptSize(
        len(registry.describe(exclude)),
        len(json.dumps(registry.schemas(exclude))),
    )


def group_sizes(
    registry: ToolRegistry, groups: Sequence[str] = GROUPS
) -> dict[str, tuple[list[str], PromptSize]]:
    names = registry.names()
    out: dict[str, tuple[list[str], PromptSize]] = {}
    for g in groups:
        members = [n for n in names if group_of(n) == g]
        if members:
            size = measure(registry, {n for n in names if n not in members})
        else:
            size = PromptSize(0, 0)
        out[g] = (members, size)
    return out


def size_report() -> list[tuple[str, PromptSize]]:
    reg = ToolRegistry([*default_tools(), SubmitPlanTool()])
    names = reg.names()
    hidden = auto_hidden_groups(
        auto_simple=True,
        grade="simple",
        text=SIMPLE_SAMPLE,
        has_attachments=False,
        plan_mode=False,
        keep=(),
    )
    return [
        ("all groups + submit_plan (spec baseline)", measure(reg)),
        ("all groups, plan mode off", measure(reg, {"submit_plan"})),
        ("core only", measure(reg, excluded_tools(names, OPTIONAL_GROUPS))),
        ("simple auto rule, no signals", measure(reg, excluded_tools(names, hidden))),
    ]


def format_size_report(rows: list[tuple[str, PromptSize]]) -> str:
    base = rows[0][1]
    lines = [
        "| config | react tool chars | ~tokens | native schema chars | ~tokens "
        "| react saved | schema saved |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, (label, s) in enumerate(rows):
        if i == 0:
            react_saved = schema_saved = "-"
        else:
            d = base.describe_chars - s.describe_chars
            c = base.schema_chars - s.schema_chars
            react_saved = f"{d} ({d / base.describe_chars * 100:.1f}%, ~{d // 4} tok)"
            schema_saved = f"{c} ({c / base.schema_chars * 100:.1f}%, ~{c // 4} tok)"
        lines.append(
            f"| {label} | {s.describe_chars} | {s.describe_tokens} | {s.schema_chars} "
            f"| {s.schema_tokens} | {react_saved} | {schema_saved} |"
        )
    lines.append("")
    lines.append(
        "tokens are estimated as chars/4; delegate adds its tool only when delegation is enabled"
    )
    return "\n".join(lines)
