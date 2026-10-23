from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from conftest import FIXED_CFG_TOML, act, run_repl
from cora.core.config import ModelSpec
from cora.core.metering import CostMeter, DelegationStats, format_summary
from cora.core.state import SessionStore
from cora.core.tools import ApprovalPolicy, ToolContext, Workspace
from cora.core.tools.builtin import ReadFileTool
from cora.core.types import estimate_tokens
from explore_mock import EXPLORE_TOML, ExploreMock, turn


@pytest.fixture(autouse=True)
def _reset_mock():
    ExploreMock.reset()


def _cfg(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cora.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _session_stats(ws: Path) -> dict:
    store = SessionStore(ws / ".cora" / "sessions")
    [sid] = store.list_ids()
    return store.load(sid).delegation_stats


def test_summary_unchanged_without_delegation():
    m = CostMeter()
    spec = ModelSpec("mock/cheap", "p", "cheap", 1.0, 2.0)
    m.record(spec, "cheap", "react", 1000, 100)
    expected = (
        "== CORA cost summary ==\n"
        "calls: 1\n"
        "model mock/cheap: calls=1 in=1000 out=100 cost=$0.001200\n"
        "total_estimated_cost_usd: 0.001200"
    )
    assert format_summary(m.summary()) == expected
    assert format_summary(m.summary({})) == expected
    assert format_summary(m.summary(DelegationStats().to_dict())) == expected
    assert set(m.summary()["delegated"]) == {
        "calls",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "price_known",
    }


def test_repl_cost_without_delegation_has_no_detail(scripted, ws, tmp_path):
    scripted.script[:] = ["Final Answer: hi"]
    cfg = _cfg(tmp_path, FIXED_CFG_TOML)
    out = run_repl(ws, cfg, ["hello", "/cost", "/exit"])
    assert "delegated" not in out


def test_cost_shows_delegation_metrics(ws, tmp_path):
    (ws / "f.txt").write_text("a" * 400, encoding="utf-8")
    for t in ("qa", "qb", "qc"):
        ExploreMock.subs[t] = [act("read_file", {"path": "f.txt"}), "Final Answer: A"]
    ExploreMock.main = [turn("qa", "qb", "qc"), "Final Answer: done"]
    cfg = _cfg(tmp_path, EXPLORE_TOML + "\n[delegation]\nenabled = true\n")
    out = run_repl(ws, cfg, ["main task", "/cost", "/exit"])
    assert "delegated (sub-agents): calls=6" in out
    assert "delegated detail: invocations=3 (explore=3 general=0) ok=3 failed=0 refused=0" in out
    assert "max_fanout=3" in out
    assert "wall_s=" in out
    assert "(estimate)" in out
    result = asyncio.run(
        ReadFileTool().run({"path": "f.txt"}, ToolContext(Workspace(ws), ApprovalPolicy("auto")))
    )
    exp = estimate_tokens(result.output)
    st = estimate_tokens("Sub-agent summary:\nA")
    stats = _session_stats(ws)
    assert stats["tool_result_tokens"] == 3 * exp
    assert stats["summary_tokens"] == 3 * st
    assert stats["avoided_tokens_est"] == 3 * (exp - st)
    assert f"avoided_tokens_est={3 * (exp - st)}" in out


def test_delegation_stats_persist_and_merge(ws, tmp_path):
    ExploreMock.subs["qa"] = ["Final Answer: A"]
    ExploreMock.subs["qb"] = ["Final Answer: B"]
    ExploreMock.subs["qg"] = ["Final Answer: G"]
    ExploreMock.main = [
        turn("qa", "qb"),
        "Final Answer: d1",
        act("delegate", {"task": "qg"}),
        "Final Answer: d2",
    ]
    cfg = _cfg(tmp_path, EXPLORE_TOML + "\n[delegation]\nenabled = true\n")
    run_repl(ws, cfg, ["first", "second", "/exit"])
    stats = _session_stats(ws)
    assert stats["explore_calls"] == 2
    assert stats["general_calls"] == 1
    assert stats["max_fanout"] == 2


def test_delegation_stats_merged_unit():
    a = DelegationStats(explore_calls=1, max_fanout=2, busy_s=1.5)
    b = DelegationStats(explore_calls=2, max_fanout=3, busy_s=0.5)
    out = a.merged(b)
    assert out.explore_calls == 3
    assert out.max_fanout == 3
    assert out.busy_s == pytest.approx(2.0)
    assert DelegationStats.from_dict({"explore_calls": 4, "unknown": 9}).explore_calls == 4
