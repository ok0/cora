from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest

from conftest import PY, act, with_gates_off
from cora.core.agent import Agent
from cora.core.tools import ApprovalPolicy

GOLDEN = Path(__file__).parent / "fixtures" / "m16c" / "baseline_prompts.json"
TASK = "make m.py"
M_CONTENT = "def f():\n    return 1\n"

RUN_VARYING = [
    re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)?"),
    re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"),
    re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
]


def _normalize(text: str, ws_dir: Path) -> str:
    text = text.replace(str(ws_dir.resolve()), "<ws>")
    text = text.replace(str(ws_dir), "<ws>")
    text = text.replace(sys.executable, "<PY>")
    for pattern in RUN_VARYING:
        text = pattern.sub("<VAR>", text)
    return text


def _run_scenario(scripted, cfg, ws_dir: Path, script: list) -> list:
    ws_dir.mkdir()
    scripted.calls.clear()
    scripted.script[:] = script
    asyncio.run(Agent(cfg, ws_dir, ApprovalPolicy("auto")).run(TASK))
    captured = [
        [{"role": m.role, "content": m.content} for m in call.messages]
        for call in scripted.calls
    ]
    return json.loads(_normalize(json.dumps(captured, ensure_ascii=False), ws_dir))


def test_prompts_byte_identical_with_new_keys_off(mock_config, scripted, ws):
    cfg = with_gates_off(mock_config, approval="auto")
    s1_script = [
        act("write_file", {"path": "m.py", "content": M_CONTENT}),
        act("run_shell", {"command": f'{PY} -c "import m; print(m.f())"'}),
        "Final Answer: done",
    ]
    s2_script = [
        act("write_file", {"path": "m.py", "content": M_CONTENT}),
        "Final Answer: done",
    ]
    observed = {
        "S1": _run_scenario(scripted, cfg, ws / "s1", s1_script),
        "S2": _run_scenario(scripted, cfg, ws / "s2", s2_script),
    }

    if os.environ.get("CORA_M16C_WRITE_BASELINE") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(
            json.dumps(observed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        pytest.skip("baseline written")

    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert observed == expected
