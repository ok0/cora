from __future__ import annotations

from cora.core.config import ModelSpec
from cora.core.metering import CostMeter, DelegationStats, format_summary
from cora.core.react import has_delegate_action_line


def test_stats_new_fields():
    assert DelegationStats().attempts == 0 == DelegationStats().attempts_unparsed
    out = DelegationStats(attempts=1).merged(DelegationStats(attempts=2, attempts_unparsed=1))
    assert out.attempts == 3
    assert out.attempts_unparsed == 1
    assert DelegationStats.from_dict({"explore_calls": 1}).attempts == 0


def test_summary_gate_attempts_only():
    m = CostMeter()
    spec = ModelSpec("mock/cheap", "p", "cheap", 1.0, 2.0)
    m.record(spec, "cheap", "react", 1000, 100)
    d = m.summary(DelegationStats(attempts=1).to_dict())["delegated"]
    assert d["attempts"] == 1
    assert d["attempts_unparsed"] == 0
    assert d["invocations"] == 0
    assert "refused=0 attempts=1 attempts_unparsed=0 wall_s=" in format_summary(
        m.summary(DelegationStats(attempts=1).to_dict())
    )
    assert set(m.summary(DelegationStats().to_dict())["delegated"]) == {
        "calls",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "price_known",
    }


def test_has_delegate_action_line():
    for text in ("Thought: x\nAction: delegate\n", "  Action:   delegate  ", "a\nAction: delegate"):
        assert has_delegate_action_line(text), text
    for text in (
        "Action: delegate_x",
        "Action: read_file",
        "Action:\ndelegate",
        "I will Action: delegate",
        "",
    ):
        assert not has_delegate_action_line(text), text
