from __future__ import annotations

import asyncio
import filecmp
from pathlib import Path

import pytest

import cora.core.agent
from conftest import CFG_TOML, act, with_agent
from cora.core.agent import Agent
from cora.core.config import load_config, parse_config
from cora.core.observability import read_events
from cora.core.react import INPUT_ERROR
from cora.core.tools import ApprovalPolicy
from cora.core.types import CompletionRequest, CompletionResponse
from test_headless import base, doc, run_cli, write_cfg

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "m15b"
STRONG_MD_CUT = (FIXTURES / "strong_md_to_html_cut.txt").read_text(encoding="utf-8")
EDIT_CUT = 'Thought: t\nAction: edit_file\nAction Input: {"path": "a.py", "old": "", "new": "x = 1'


def _truncated_reply(
    text: str, output_tokens: int, finish_reason: str | None
) -> CompletionResponse:
    return CompletionResponse(
        text=text,
        input_tokens=10,
        output_tokens=output_tokens,
        model="mock/cheap",
        finish_reason=finish_reason,
    )


def _run(config, tmp_path):
    return asyncio.run(Agent(config, tmp_path, ApprovalPolicy("auto")).run("q"))


def _user_messages(req: CompletionRequest) -> list[str]:
    return [m.content for m in req.messages if m.role == "user"]


def test_toml_key_present_and_identical():
    assert "react_max_tokens = 4096" in (ROOT / "cora.toml").read_text(encoding="utf-8")
    assert "react_max_tokens = 4096" in (
        ROOT / "src/cora/data/cora.toml"
    ).read_text(encoding="utf-8")
    assert filecmp.cmp(ROOT / "cora.toml", ROOT / "src/cora/data/cora.toml", shallow=False)
    assert load_config(ROOT / "cora.toml").agent.react_max_tokens == 4096


@pytest.mark.parametrize("v", ["255", "32769", '"4096"', "4096.5"])
def test_invalid_react_max_tokens_exit_2(tmp_path, ws, v):
    cfg = write_cfg(tmp_path, CFG_TOML + f"\n[agent]\nreact_max_tokens = {v}\n")
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    d = doc(result)
    assert result.exit_code == 2
    assert d["ok"] is False
    assert "react_max_tokens" in d["errors"][0]


def test_bounds_accepted():
    for v in (256, 32768):
        cfg = parse_config(
            {
                "models": [
                    {
                        "id": "mock/cheap",
                        "provider": "scripted",
                        "tier": "cheap",
                        "input_usd_per_mtok": 1.0,
                        "output_usd_per_mtok": 2.0,
                    }
                ],
                "agent": {"react_max_tokens": v},
            }
        )
        assert cfg.agent.react_max_tokens == v


def test_request_carries_cap(scripted, mock_config, tmp_path):
    scripted.script[:] = ["Final Answer: x"]
    _run(mock_config, tmp_path)
    assert scripted.calls[0].max_tokens == 4096

    scripted.script[:] = ["Final Answer: x"]
    scripted.calls.clear()
    _run(with_agent(mock_config, react_max_tokens=2000), tmp_path)
    assert scripted.calls[0].max_tokens == 2000


def test_no_hardcoded_1024():
    assert CompletionRequest("m", []).max_tokens == 4096
    assert not hasattr(cora.core.agent, "REACT_MAX_TOKENS")


def test_truncated_length_gives_message(scripted, mock_config, tmp_path):
    scripted.script[:] = [
        _truncated_reply(STRONG_MD_CUT, 900, "length"),
        "Final Answer: done",
    ]
    r = _run(mock_config, tmp_path)
    events = read_events(r.log_path)
    truncated = [e for e in events if e["type"] == "reply_truncated"]
    assert len(truncated) == 1
    assert truncated[0]["iteration"] == 1
    assert truncated[0]["output_tokens"] == 900
    assert truncated[0]["max_tokens"] == 4096

    msgs = _user_messages(scripted.calls[1])
    last = msgs[-1]
    assert "4096" in last
    assert "no tool ran" in last
    assert "write_file" in last
    assert "append=true" in last
    assert not any(INPUT_ERROR in m for m in msgs)
    assert not any(e["type"] == "tool_call" for e in events)


def test_truncated_by_token_count(scripted, mock_config, tmp_path):
    scripted.script[:] = [
        _truncated_reply(EDIT_CUT, 4096, None),
        "Final Answer: done",
    ]
    r = _run(mock_config, tmp_path)
    events = read_events(r.log_path)
    truncated = [e for e in events if e["type"] == "reply_truncated"]
    assert len(truncated) == 1
    assert truncated[0]["iteration"] == 1
    assert truncated[0]["output_tokens"] == 4096
    assert truncated[0]["max_tokens"] == 4096

    msgs = _user_messages(scripted.calls[1])
    last = msgs[-1]
    assert "4096" in last
    assert "no tool ran" in last
    assert "write_file" in last
    assert "append=true" in last
    assert not any(INPUT_ERROR in m for m in msgs)
    assert not any(e["type"] == "tool_call" for e in events)


def test_not_truncated_keeps_input_error(scripted, mock_config, tmp_path):
    scripted.script[:] = [
        _truncated_reply(EDIT_CUT, 100, None),
        "Final Answer: done",
    ]
    r = _run(mock_config, tmp_path)
    events = read_events(r.log_path)
    assert not any(e["type"] == "reply_truncated" for e in events)
    msgs = _user_messages(scripted.calls[1])
    assert any(INPUT_ERROR in m for m in msgs)


def test_truncated_but_valid_executes(scripted, mock_config, tmp_path):
    scripted.script[:] = [
        _truncated_reply(act("list_files", {"path": "."}), 900, "length"),
        "Final Answer: done",
    ]
    r = _run(mock_config, tmp_path)
    events = read_events(r.log_path)
    assert not any(e["type"] == "reply_truncated" for e in events)
    msgs = _user_messages(scripted.calls[1])
    assert any(m.startswith("Observation:") for m in msgs)
    assert not any("no tool ran" in m for m in msgs)
