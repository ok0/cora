from __future__ import annotations

import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import CFG_TOML, COMPLEX_PROMPT
from cora.core.config import ConfigError, EscalationSettings, load_config, parse_config
from cora.core.escalation import TRIGGERS, EscalationPolicy, EscalationSignals
from cora.core.router import HeuristicRouter
from test_headless import base, run_cli, write_cfg

ROOT = Path(__file__).resolve().parents[1]


def test_toml_defaults_both_copies():
    root_toml = ROOT / "cora.toml"
    data_toml = ROOT / "src/cora/data/cora.toml"
    for p in (root_toml, data_toml):
        cfg = load_config(p)
        assert cfg.escalation == EscalationSettings(False, 4, True, 0.0, "")
        assert cfg.router.mode == "heuristic"
        text = p.read_text(encoding="utf-8")
        assert "[escalation]" in text
        assert 'mode = "heuristic"' in text
    assert root_toml.read_bytes() == data_toml.read_bytes()


def test_parse_defaults_absent_section():
    cfg = parse_config(tomllib.loads(CFG_TOML))
    assert cfg.escalation == EscalationSettings()
    assert cfg.router.mode == "heuristic"


@pytest.mark.parametrize(
    "extra",
    [
        "[escalation]\non_stuck_iterations = -1",
        "[escalation]\non_budget_fraction = 1.5",
        "[escalation]\non_budget_fraction = -0.1",
        "[escalation]\non_budget_fraction = true",
        '[escalation]\non_stuck_iterations = "4"',
        '[escalation]\nenabled = "yes"',
        "[escalation]\non_tripwire = 1",
        "[escalation]\nstrong_model = 3",
        '[escalation]\nstrong_model = "nope/x"',
        "[escalation]\nbogus = 1",
        '[router]\nmode = "x"',
        "[router]\nbogus = 1",
    ],
)
def test_invalid_values(extra):
    with pytest.raises(ConfigError):
        parse_config(tomllib.loads(CFG_TOML + "\n" + extra))


@pytest.mark.parametrize(
    "extra",
    [
        "[escalation]\non_stuck_iterations = -1",
        "[escalation]\non_budget_fraction = 1.5",
        '[escalation]\non_stuck_iterations = "4"',
        '[router]\nmode = "x"',
        "[router]\nbogus = 1",
        "[escalation]\nbogus = 1",
        '[escalation]\nstrong_model = "nope/x"',
    ],
)
def test_invalid_values_exit_2(extra, ws, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML + "\n" + extra)
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    assert result.exit_code == 2


def test_valid_strong_model():
    cfg = parse_config(
        tomllib.loads(
            CFG_TOML
            + '\n[escalation]\nstrong_model = "mock/strong"\non_budget_fraction = 1\n'
        )
    )
    assert cfg.escalation.strong_model == "mock/strong"
    assert cfg.escalation.on_budget_fraction == 1


def test_policy_unit():
    off = EscalationPolicy(EscalationSettings())
    signals = [
        EscalationSignals(ladder_exhausted=True),
        EscalationSignals(tripwire=True),
        EscalationSignals(stuck_iterations=99),
        EscalationSignals(budget_fraction=1.0),
    ]
    assert all(off.decide(s) is None for s in signals)

    on = EscalationPolicy(
        EscalationSettings(enabled=True, on_stuck_iterations=4, on_budget_fraction=0.5)
    )
    assert on.decide(EscalationSignals(stuck_iterations=3)) is None
    assert on.decide(EscalationSignals(stuck_iterations=4)) == "stuck"
    assert on.decide(EscalationSignals(budget_fraction=0.6)) == "budget_fraction"
    assert on.decide(EscalationSignals(budget_fraction=0.6, check_passed=True)) is None
    assert (
        on.decide(EscalationSignals(ladder_exhausted=True, tripwire=True, stuck_iterations=9))
        == "ladder_exhausted"
    )
    assert on.decide(EscalationSignals(tripwire=True)) == "tripwire"

    no_trip = EscalationPolicy(EscalationSettings(enabled=True, on_tripwire=False))
    assert no_trip.decide(EscalationSignals(tripwire=True)) is None

    no_stuck = EscalationPolicy(EscalationSettings(enabled=True, on_stuck_iterations=0))
    assert no_stuck.decide(EscalationSignals(stuck_iterations=99)) is None

    assert len(TRIGGERS) == 5


def test_router_cheap_first_unit(mock_config):
    cfg = replace(mock_config, router=replace(mock_config.router, mode="cheap_first"))
    assert HeuristicRouter(mock_config).route(COMPLEX_PROMPT).tier == "strong"
    d = HeuristicRouter(cfg).route(COMPLEX_PROMPT)
    assert d.tier == "cheap"
    assert "cheap_first" in d.reasons
    assert d.grade == "complex"
    assert HeuristicRouter(cfg).route(COMPLEX_PROMPT, "strong").tier == "strong"
