from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from conftest import ScriptedProvider, act
from cora.core.agent import Agent
from cora.core.config import CoraConfig, parse_config
from cora.core.tools import ApprovalPolicy

FIXTURE = Path(__file__).parent / "fixtures" / "m17_off_prompts.json"
# The fixture matches a 61-char interpreter path. Eviction summary lines are cut at
# 160 chars (src/cora/core/memory.py:604), so a real path longer than 70 chars was cut
# before norm() (M20d (e)6). The scripted command therefore runs the interpreter
# through a fixed-length alias.
PY_ALIAS_NAME = ".m17py" + "_" * 53
PY_ALIAS = "./" + PY_ALIAS_NAME


def link_python(ws: Path) -> str:
    link = ws / PY_ALIAS_NAME
    if not link.is_symlink():
        link.symlink_to(sys.executable)
    return PY_ALIAS


def _config(memory_extra: dict) -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "scripted",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                },
                {
                    "id": "mock/strong",
                    "provider": "scripted",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                },
            ],
            "agent": {"approval": "auto", "max_iterations": 40},
            "memory": {
                "context_budget_tokens": 3000,
                "keep_last_messages": 4,
                "max_observation_chars": 4000,
                **memory_extra,
            },
        }
    )


def capture(root: Path, memory_extra: dict | None = None) -> list[list[dict]]:
    ScriptedProvider.script.clear()
    ScriptedProvider.calls.clear()
    os.environ.pop("CORA_RECORD_MODE", None)
    os.environ.pop("CORA_RECORD_DIR", None)
    ws = root / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    py = link_python(ws)
    (ws / "big.txt").write_text(
        "\n".join(f"line {i} " + "x" * 60 for i in range(5000)) + "\n",
        encoding="utf-8",
    )
    (ws / "a.py").write_text("x = 0\n", encoding="utf-8")
    ScriptedProvider.script[:] = [
        act("write_file", {"path": "a.py", "content": "x = 1\n"}),
        act("run_shell", {"command": f"{py} -c \"raise SystemExit(1)\""}),
        *[act("read_file", {"path": "big.txt", "start_line": 1 + 50 * i}) for i in range(20)],
        "Final Answer: done",
    ]
    asyncio.run(
        Agent(_config(memory_extra or {}), ws, ApprovalPolicy("auto")).run(
            "edit a.py then read big.txt"
        )
    )

    def norm(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        text = text.replace(PY_ALIAS, "<PYTHON>")
        text = text.replace(sys.executable, "<PYTHON>")
        for token in (str(ws.resolve()), str(ws), str(root)):
            text = text.replace(token, "<WS>")
        return text

    return [
        [
            {"role": m.role, "content": norm(m.content), "tool_call_id": m.tool_call_id}
            for m in req.messages
        ]
        for req in ScriptedProvider.calls
    ]


def test_off_prompts_match_baseline(tmp_path):
    assert capture(tmp_path) == json.loads(FIXTURE.read_text("utf-8"))


def test_explicit_off_keys_match_baseline(tmp_path):
    result = capture(
        tmp_path,
        memory_extra={"ledger": False, "ledger_max_chars": 1500, "summarize": "off"},
    )
    assert result == json.loads(FIXTURE.read_text("utf-8"))


def test_python_alias_fixed_length(tmp_path):
    assert len(PY_ALIAS) == 61
    link_python(tmp_path)
    assert subprocess.run(
        [str(tmp_path / PY_ALIAS_NAME), "-c", "raise SystemExit(3)"]
    ).returncode == 3


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        result = capture(Path(d))
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
