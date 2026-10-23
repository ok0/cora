from __future__ import annotations

import asyncio
import filecmp
import inspect
import json
import re
from pathlib import Path

import pytest

import test_m17_off_identity as m17
from conftest import CFG_TOML, ScriptedProvider, with_agent, with_gates_off
from cora.core.agent import Agent
from cora.core.config import ConfigError, parse_config
from cora.core.react import INPUT_ERROR
from cora.core.tools import ApprovalPolicy
from cora.core.tools.builtin import EditFileTool, WriteFileTool, locate_mismatch
from test_headless import base, run_cli, write_cfg

ROOT = Path(__file__).resolve().parents[1]
TOMLS = (ROOT / "cora.toml", ROOT / "src" / "cora" / "data" / "cora.toml")
KEYS = ("raw_file_body", "repeat_breaker", "located_errors")
FIX = json.loads((Path(__file__).parent / "fixtures" / "m17b" / "replies.json").read_text("utf-8"))
OLD_MSG = (
    "edit_file failed: 'old' text not found in md2html.py. It must match the file exactly, "
    "including whitespace and indentation. Re-read the file with read_file and copy the exact "
    "lines without the line-number prefix."
)
TASK = "make the program"
DOC_TOKENS = (
    "raw_file_body",
    "repeat_breaker",
    "located_errors",
    "<<<CONTENT",
    "CONTENT>>>",
    "<<<OLD",
    "<<<NEW",
    "repeat_detected",
    "0.7",
)


def FA(name: str) -> str:
    return "path"


def events(r, kind: str | None = None) -> list[dict]:
    rows = [json.loads(x) for x in r.log_path.read_text(encoding="utf-8").splitlines()]
    return [e for e in rows if kind is None or e["type"] == kind]


def run(cfg, ws: Path, task: str = TASK):
    return asyncio.run(Agent(cfg, ws, ApprovalPolicy("auto")).run(task))


def cfg_on(mock_config, key: str):
    return with_gates_off(mock_config, approval="auto", json_string_repair=True, **{key: True})


def write_block(path, content):
    return (
        f'Thought: write\nAction: write_file\nAction Input: {{"path": "{path}"}}\n'
        f"<<<CONTENT\n{content}\nCONTENT>>>"
    )


def _model_list() -> list[dict]:
    return [
        {
            "id": "mock/cheap",
            "provider": "scripted",
            "tier": "cheap",
            "input_usd_per_mtok": 1.0,
            "output_usd_per_mtok": 2.0,
        }
    ]


ORIG_CONFIG = m17._config
PAD_CHAR = "~"


def _swap(requests: list[list[dict]], mapping: dict[str, str]) -> list[list[dict]]:
    out = []
    for msgs in requests:
        fixed = []
        for m in msgs:
            content = m["content"]
            if isinstance(content, str):
                for old, new in mapping.items():
                    content = content.replace(old, new)
            fixed.append({**m, "content": content})
        out.append(fixed)
    return out


def _pads() -> dict[type, str]:
    pads = {}
    for cls in (EditFileTool, WriteFileTool):
        assert len(cls.raw_args_doc) > len(cls.args_doc)
        pads[cls] = cls.args_doc + PAD_CHAR * (len(cls.raw_args_doc) - len(cls.args_doc))
    return pads


def _capture_with(
    root: Path,
    monkeypatch,
    overrides: dict,
    *,
    pad: bool = False,
    memory_extra: dict | None = None,
):
    with monkeypatch.context() as mp:
        mp.setattr(
            m17,
            "_config",
            lambda extra: with_agent(ORIG_CONFIG(extra), **({k: False for k in KEYS} | overrides)),
        )
        if pad:
            for cls, doc in _pads().items():
                mp.setattr(cls, "args_doc", doc)
        root.mkdir(parents=True)
        return m17.capture(root, memory_extra)


def test_toml_copies_have_write_keys_false():
    for p in TOMLS:
        text = p.read_text(encoding="utf-8")
        for key in KEYS:
            assert re.search(rf"^{key} = false", text, re.M), (p, key)
    assert filecmp.cmp(TOMLS[0], TOMLS[1], shallow=False)


def test_write_keys_default_false_and_invalid():
    cfg = parse_config({"models": _model_list()})
    for key in KEYS:
        assert getattr(cfg.agent, key) is False
    for key in KEYS:
        for bad in ("yes", 1):
            with pytest.raises(ConfigError, match=key):
                parse_config({"models": _model_list(), "agent": {key: bad}})


@pytest.mark.parametrize("key", KEYS)
def test_write_key_invalid_exit_2(ws, tmp_path, key):
    cfg = write_cfg(tmp_path, CFG_TOML + f'\n[agent]\n{key} = "yes"\n')
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    assert result.exit_code == 2
    assert key in result.stdout


def test_unknown_agent_key_exit_2(ws, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML + "\n[agent]\nraw_file_bodies = true\n")
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    assert result.exit_code == 2


def test_all_off_prompts_match_m17_baseline(tmp_path, monkeypatch):
    orig = m17._config
    monkeypatch.setattr(
        m17,
        "_config",
        lambda extra: with_agent(
            orig(extra), raw_file_body=False, repeat_breaker=False, located_errors=False
        ),
    )
    assert m17.capture(tmp_path) == json.loads(m17.FIXTURE.read_text("utf-8"))
    assert all(c.temperature == 0.0 for c in ScriptedProvider.calls)


@pytest.mark.parametrize("key", KEYS)
def test_single_key_independent(key, tmp_path, monkeypatch, mock_config, scripted):
    got = _capture_with(tmp_path / "cap_on", monkeypatch, {key: True})
    baseline = json.loads(m17.FIXTURE.read_text("utf-8"))
    if key != "raw_file_body":
        assert got == baseline
    else:
        pads = _pads()
        ctl = _capture_with(tmp_path / "cap_ctl", monkeypatch, {}, pad=True)
        assert _swap(got, {c.raw_args_doc: pads[c] for c in (EditFileTool, WriteFileTool)}) == ctl
        un = _swap(got, {c.raw_args_doc: c.args_doc for c in (EditFileTool, WriteFileTool)})
        assert len(un) == len(baseline)
        assert [r[0] for r in un] == [r[0] for r in baseline]

    a = FIX["write_escape"]["reply"]
    ws = tmp_path / "ws_a"
    ws.mkdir()
    scripted.calls.clear()
    scripted.script[:] = [a, "Final Answer: done"]
    run(cfg_on(mock_config, key), ws)
    obs = scripted.calls[1].messages[-1].content
    if key == "located_errors":
        assert obs != "Observation: " + INPUT_ERROR
        assert obs.startswith("Observation: " + INPUT_ERROR)
    else:
        assert obs == "Observation: " + INPUT_ERROR

    ws = tmp_path / "ws_b"
    ws.mkdir()
    (ws / "md2html.py").write_text(FIX["edit_backslash"]["file"], encoding="utf-8")
    scripted.calls.clear()
    scripted.script[:] = [FIX["edit_backslash"]["reply"], "Final Answer: done"]
    run(cfg_on(mock_config, key), ws)
    obs = scripted.calls[1].messages[-1].content
    if key == "located_errors":
        assert obs != "Observation: " + OLD_MSG
        assert obs.startswith("Observation: " + OLD_MSG)
    else:
        assert obs == "Observation: " + OLD_MSG

    ws = tmp_path / "ws_c"
    ws.mkdir()
    scripted.calls.clear()
    scripted.script[:] = [a, a, a, "Final Answer: done"]
    r = run(cfg_on(mock_config, key), ws)
    assert bool(events(r, "repeat_detected")) == (key == "repeat_breaker")
    assert any(c.temperature == 0.7 for c in scripted.calls) == (key == "repeat_breaker")

    ws = tmp_path / "ws_d"
    ws.mkdir()
    scripted.calls.clear()
    scripted.script[:] = [write_block("made.py", "x = 1\n"), "Final Answer: done"]
    run(cfg_on(mock_config, key), ws)
    assert (ws / "made.py").exists() == (key == "raw_file_body")


def test_raw_budget_shift_is_hint_length_only(tmp_path, monkeypatch):
    pads = _pads()
    to_doc_on = {c.raw_args_doc: c.args_doc for c in (EditFileTool, WriteFileTool)}
    to_doc_ctl = {pads[c]: c.args_doc for c in (EditFileTool, WriteFileTool)}
    on = _capture_with(tmp_path / "on", monkeypatch, {"raw_file_body": True})
    ctl = _capture_with(tmp_path / "ctl", monkeypatch, {}, pad=True)
    baseline = json.loads(m17.FIXTURE.read_text("utf-8"))
    assert _swap(ctl, to_doc_ctl) != baseline
    assert _swap(ctl, to_doc_ctl) == _swap(on, to_doc_on)
    big = {"context_budget_tokens": 1_000_000}
    on_big = _capture_with(
        tmp_path / "on_big", monkeypatch, {"raw_file_body": True}, memory_extra=big
    )
    off_big = _capture_with(tmp_path / "off_big", monkeypatch, {}, memory_extra=big)
    assert _swap(on_big, to_doc_on) == off_big
    assert not any(
        m["content"].startswith("Summary of earlier steps:")
        for r in off_big
        for m in r
        if isinstance(m["content"], str)
    )


def test_no_task_specifics_m17b():
    core = ROOT / "src" / "cora" / "core"
    forbidden = [
        "md_to_html",
        "md2html",
        "markdown",
        "href",
        "todo",
        "rest_notes",
        "text_stats",
        "e2e_",
        "?!",
    ]
    for path in (
        core / "react.py",
        core / "repeat.py",
        core / "tools" / "registry.py",
        core / "config.py",
        core / "prompts.py",
    ):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text, (path.name, token)
    for obj in (EditFileTool, WriteFileTool, locate_mismatch):
        src = inspect.getsource(obj).lower()
        for token in forbidden:
            assert token not in src, (obj.__name__, token)
    agent_text = (core / "agent.py").read_text(encoding="utf-8").lower()
    for token in ("md2html", "md_to_html", "markdown", "href"):
        assert token not in agent_text, token


def test_repeat_event_fields_only(mock_config, scripted, ws):
    a = FIX["write_escape"]["reply"]
    scripted.script[:] = [a, a, a, "Final Answer: done"]
    r = run(cfg_on(mock_config, "repeat_breaker"), ws)
    evs = events(r, "repeat_detected")
    assert evs
    for e in evs:
        assert set(e) == {"ts", "type", "iteration", "kind", "count"}


def test_usage_m17b():
    text = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    for token in DOC_TOKENS:
        assert token in text, token


ARCH_SYMBOLS = {
    "core/react.py": (
        "_split_raw_blocks",
        "_attach_blocks",
        "located_input_error",
        "RAW_UNCLOSED_ERROR",
        "RAW_STRAY_ERROR",
        "RAW_ACTION_ERROR",
        "_owner_mismatch",
        "RAW_RULES",
        "_marker_lines",
        "truncated_error",
    ),
    "core/tools/registry.py": (
        "ToolRegistry",
        "describe",
        "raw_blocks",
        "args_doc",
        "raw_args_doc",
    ),
    "core/tools/builtin.py": (
        "locate_mismatch",
        "EditFileTool",
        "WriteFileTool",
        "raw_args_doc",
        "_raw_marker_refusal",
    ),
    "core/tools/base.py": ("ToolContext", "located_errors", "raw_file_body"),
    "core/repeat.py": ("RepeatTracker", "RepeatSignal", "boost"),
    "core/prompts.py": ("repeat_feedback", "SYSTEM_TEMPLATE"),
    "agent.py": ("call_model", "temperature", "raw_file_body"),
    "config.py": ("WRITE_KEYS", "raw_file_body", "repeat_breaker", "located_errors"),
}


def _has(symbol: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(symbol)}(?!\w)", text) is not None


def _src_of(token: str) -> Path:
    base = ROOT / "src" / "cora"
    return base / token if token.startswith("core/") else base / "core" / token


def _arch_m17b_section() -> str:
    text = (ROOT / ".docs" / "architecture.md").read_text(encoding="utf-8")
    return text.split("## M17b", 1)[1].split("\n## ", 1)[0]


def test_arch_m17b():
    text = (ROOT / ".docs" / "architecture.md").read_text(encoding="utf-8")
    for token in DOC_TOKENS:
        assert token in text, token
    section = _arch_m17b_section()
    for token, symbols in ARCH_SYMBOLS.items():
        doc_line = "\n".join(ln for ln in section.splitlines() if f"`{token}`" in ln)
        assert doc_line, token
        src = _src_of(token).read_text(encoding="utf-8")
        for sym in symbols:
            assert _has(sym, src), (token, sym, "not in source")
            assert _has(sym, doc_line), (token, sym, "not in doc bullet")
    builtin_src = _src_of("core/tools/builtin.py").read_text(encoding="utf-8")
    base_src = _src_of("core/tools/base.py").read_text(encoding="utf-8")
    assert _has("raw_args_doc", builtin_src)
    assert not _has("raw_args_doc", base_src)
    assert _has("located_errors", base_src)
    agent_src = _src_of("core/agent.py").read_text(encoding="utf-8")
    assert "located_input_error(" in agent_src
    assert "truncated_error(" in agent_src
    react_line = "\n".join(ln for ln in section.splitlines() if "`core/react.py`" in ln)
    assert "`agent.py`" in react_line and "잘림 분기" in react_line
    assert "parse_turn 경로에서만" not in section
    assert "모두 `parse_turn" not in section


def _render_raw_rules() -> list[str]:
    from cora.core.react import (
        RAW_ACTIONS,
        RAW_ATTACH_RULES,
        RAW_LINE_CLASSES,
        RAW_RULES,
        RAW_STATES,
        RAW_WEAK_NEXT,
    )

    rows = ["| state | line | action |", "|---|---|---|"]
    rows += [f"| {s} | {c} | {a} |" for (s, c), a in RAW_RULES.items()]
    rows += [f"- state `{k}`: {v}" for k, v in RAW_STATES.items()]
    rows += [f"- line `{k}`: {v}" for k, v in RAW_LINE_CLASSES.items()]
    rows += [f"- action `{k}`: {v}" for k, v in RAW_ACTIONS.items()]
    rows += [f"- weak close: {v}" for v in RAW_WEAK_NEXT]
    rows += [f"- attach: {v}" for v in RAW_ATTACH_RULES]
    return rows


def test_raw_rules_documented():
    usage = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    usage_part = usage.split("#### 원문 쓰기 채널, 반복 차단, 위치 있는 오류 (M17b)", 1)[1]
    usage_part = usage_part.split("\n### ", 1)[0]
    stale = (
        "최대 2줄",
        "정확한 닫기가 없을 때만",
        "본문 안의 `Observation:` 줄은 자르지 않습니다",
        "그 전의 `>>>` 줄은 본문",
        "`submitted_plan`만 부모",
    )
    for part in (usage_part, _arch_m17b_section()):
        lines = {ln.strip() for ln in part.splitlines()}
        for row in _render_raw_rules():
            assert row in lines, row
        for s in stale:
            assert s not in part, s
