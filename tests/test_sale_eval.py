from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML
from cora.bench.sale_eval import (
    POLICIES,
    Outcome,
    format_sale_eval,
    load_sale_cases,
    run_sale_eval,
    sale_eval_json,
)
from cora.cli.main import app
from cora.core.errors import ConfigError
from cora.core.sale import PlanFeatures, load_tier_table

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "src/cora/data/sale_cases.synthetic.jsonl"
FIXTURE = ROOT / "tests/fixtures/sale_tiers.synthetic.toml"
TABLE = load_tier_table(FIXTURE)
GOOD = '{"id":"g","plan_text":"x"}'
MEASURED_3 = (
    'placeholder = false\nunit = "usd"\n'
    '[[tiers]]\nname = "cheap"\ncost = 1.0\nsolve_rate = 0.6\n'
    '[[tiers]]\nname = "mid"\ncost = 4.0\nsolve_rate = 0.8\n'
    '[[tiers]]\nname = "strong"\ncost = 10.0\nsolve_rate = 0.9\n'
)


def _run(args: list[str]):
    return CliRunner().invoke(app, args)


def test_example_cases_load():
    cases = load_sale_cases(EXAMPLE, TABLE)
    assert len(cases) == 9
    assert [c.id for c in cases] == [f"syn-0{i}" for i in range(1, 10)]
    by_id = {c.id: c for c in cases}
    assert by_id["syn-04"].features == PlanFeatures(2, 1, 0.5, 0.0)
    assert by_id["syn-07"].features == PlanFeatures(8, 7, 0.625, 0.25)
    assert by_id["syn-08"].outcomes == {
        "cheap": Outcome(False, 1.5),
        "strong": Outcome(True, 12.0),
    }


def test_example_policy_table():
    """Mechanism demo on SYNTHETIC / PLACEHOLDER data, not a measured effect."""
    r = run_sale_eval(
        load_sale_cases(EXAMPLE, TABLE),
        TABLE,
        reward=20.0,
        budget_cap=20.0,
        router_threshold=3,
    )
    rows = {p.policy: p for p in r.rows}
    assert rows["always-cheap"].total_cost == pytest.approx(12.3)
    assert rows["always-cheap"].solve_rate == pytest.approx(1.89 / 9)
    assert rows["always-cheap"].strong_share == pytest.approx(0)
    assert rows["always-cheap"].over_budget == 0
    assert rows["always-cheap"].recorded == 1
    assert rows["always-strong"].total_cost == pytest.approx(120.0)
    assert rows["always-strong"].solve_rate == pytest.approx(7.4725 / 9)
    assert rows["always-strong"].strong_share == pytest.approx(1.0)
    assert rows["always-strong"].over_budget == 1
    assert rows["always-strong"].recorded == 1
    assert rows["heuristic-router"].total_cost == pytest.approx(24.9)
    assert rows["heuristic-router"].solve_rate == pytest.approx(2.64 / 9)
    assert rows["heuristic-router"].strong_share == pytest.approx(1 / 9)
    assert rows["heuristic-router"].over_budget == 0
    assert rows["sale-lite"].total_cost == pytest.approx(61.5)
    assert rows["sale-lite"].solve_rate == pytest.approx(5.14 / 9)
    assert rows["sale-lite"].strong_share == pytest.approx(4 / 9)
    assert rows["sale-lite"].over_budget == 0
    assert rows["sale-lite"].total_cost < rows["always-strong"].total_cost
    assert rows["sale-lite"].solve_rate > rows["always-cheap"].solve_rate
    assert r.placeholder is True


def test_eval_deterministic():
    cases = load_sale_cases(EXAMPLE, TABLE)

    def go():
        return run_sale_eval(cases, TABLE, reward=20.0, budget_cap=20.0, router_threshold=3)

    assert format_sale_eval(go()) == format_sale_eval(go())
    assert sale_eval_json(go()) == sale_eval_json(go())


def test_recorded_outcome_overrides(tmp_path: Path):
    path = tmp_path / "r.jsonl"
    path.write_text(
        '{"id":"r","plan":{"steps":1,"files":1,"tool_risk":0.0,"uncertainty":0.0},'
        '"outcomes":{"cheap":{"success":true,"cost":0.25}}}\n',
        encoding="utf-8",
    )
    r = run_sale_eval(
        load_sale_cases(path, TABLE), TABLE, reward=20.0, budget_cap=20.0, router_threshold=3
    )
    row = {p.policy: p for p in r.rows}["always-cheap"]
    assert row.total_cost == pytest.approx(0.25)
    assert row.solve_rate == pytest.approx(1.0)
    assert row.recorded == 1


@pytest.mark.parametrize(
    "content, lineno, needle",
    [
        ('{"id": "a", "plan": {', 1, "invalid JSON"),
        (GOOD + '\n{"plan_text":"x"}', 2, "'id'"),
        ('{"id":"a"}', 1, "'plan' or 'plan_text'"),
        ('{"id":"a","plan":{"steps":1,"files":1,"tool_risk":0.0}}', 1, "missing keys"),
        (
            '{"id":"a","plan":{"steps":1,"files":1,"tool_risk":1.5,"uncertainty":0}}',
            1,
            "invalid 'plan'",
        ),
        ("[1,2]", 1, "JSON object"),
        ('{"id":"a","plan_text":"x","foo":1}', 1, "unknown keys"),
        (
            '{"id":"a","plan_text":"x","outcomes":{"mid":{"success":true,"cost":1}}}',
            1,
            "unknown tier",
        ),
        ('{"id":"a","plan_text":"x","outcomes":{"cheap":{"success":true,"cost":-1}}}', 1, "cost"),
        (GOOD + "\n" + GOOD, 2, "duplicate id"),
    ],
)
def test_bad_lines_report_line_number(tmp_path: Path, content, lineno, needle):
    path = tmp_path / "c.jsonl"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_sale_cases(path, TABLE)
    msg = str(exc.value)
    assert msg.startswith(f"{path}:{lineno}:")
    assert needle in msg


def test_empty_and_missing_files(tmp_path: Path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="no cases"):
        load_sale_cases(empty, TABLE)
    blank = tmp_path / "blank.jsonl"
    blank.write_text("\n  \n", encoding="utf-8")
    with pytest.raises(ConfigError, match="no cases"):
        load_sale_cases(blank, TABLE)
    with pytest.raises(ConfigError, match="cannot read cases file"):
        load_sale_cases(tmp_path / "missing.jsonl", TABLE)


def test_cli_eval_table(cfg_file: Path):
    args = [
        "sale",
        "eval",
        "--cases",
        str(EXAMPLE),
        "--tiers",
        str(FIXTURE),
        "--config",
        str(cfg_file),
    ]
    result = _run(args)
    assert result.exit_code == 0, result.output
    for policy in POLICIES:
        assert policy in result.output
    assert "SYNTHETIC / PLACEHOLDER" in result.output
    assert "실측 아님" in result.output
    again = _run(args)
    assert again.output == result.output


def test_cli_json(cfg_file: Path):
    result = _run(
        [
            "sale",
            "eval",
            "--cases",
            str(EXAMPLE),
            "--tiers",
            str(FIXTURE),
            "--json",
            "--config",
            str(cfg_file),
        ]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "SYNTHETIC / PLACEHOLDER" in data["warning"]
    assert [p["policy"] for p in data["policies"]] == list(POLICIES)


def test_cli_bad_line(tmp_path: Path, cfg_file: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id":"a","plan_text":"x"}\n{bad\n', encoding="utf-8")
    result = _run(["sale", "eval", "--cases", str(path), "--config", str(cfg_file)])
    assert result.exit_code == 2
    assert ":2:" in result.output


def test_cli_missing_and_empty(tmp_path: Path, cfg_file: Path):
    missing = _run(
        ["sale", "eval", "--cases", str(tmp_path / "nope.jsonl"), "--config", str(cfg_file)]
    )
    assert missing.exit_code == 2
    assert "cannot read cases file" in missing.output
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    result = _run(["sale", "eval", "--cases", str(empty), "--config", str(cfg_file)])
    assert result.exit_code == 2
    assert "no cases" in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["sale", "eval"],
        ["sale", "run", "--cases", str(EXAMPLE)],
        ["sale", "eval", "--cases", str(EXAMPLE), "--reward", "0"],
        ["sale", "eval", "--cases", str(EXAMPLE), "--budget-cap", "-1"],
    ],
    ids=["no_cases", "bad_action", "reward_zero", "budget_cap_negative"],
)
def test_cli_usage_errors(cfg_file: Path, args):
    result = _run(args + ["--config", str(cfg_file)])
    assert result.exit_code == 2


def test_cli_custom_measured_table(tmp_path: Path, cfg_file: Path):
    table = tmp_path / "measured.toml"
    table.write_text(MEASURED_3, encoding="utf-8")
    result = _run(
        [
            "sale",
            "eval",
            "--cases",
            str(EXAMPLE),
            "--tiers",
            str(table),
            "--config",
            str(cfg_file),
        ]
    )
    assert result.exit_code == 0, result.output
    assert "SYNTHETIC" not in result.output
    assert "tiers=cheap,mid,strong" in result.output


def test_cli_budget_cap(cfg_file: Path):
    result = _run(
        [
            "sale",
            "eval",
            "--cases",
            str(EXAMPLE),
            "--tiers",
            str(FIXTURE),
            "--budget-cap",
            "0.5",
            "--json",
            "--config",
            str(cfg_file),
        ]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    sale_lite = {p["policy"]: p for p in data["policies"]}["sale-lite"]
    assert sale_lite["over_budget"] == 9


def test_cli_reads_sale_section(tmp_path: Path):
    cfg = tmp_path / "reward.toml"
    cfg.write_text(CFG_TOML + "\n[sale]\nreward = 5\n", encoding="utf-8")
    result = _run(["sale", "eval", "--cases", str(EXAMPLE), "--json", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["reward"] == 5.0

    table = tmp_path / "measured.toml"
    table.write_text(MEASURED_3, encoding="utf-8")
    cfg2 = tmp_path / "tiers.toml"
    cfg2.write_text(CFG_TOML + f'\n[sale]\ntiers_file = "{table}"\n', encoding="utf-8")
    result2 = _run(["sale", "eval", "--cases", str(EXAMPLE), "--json", "--config", str(cfg2)])
    assert result2.exit_code == 0, result2.output
    assert json.loads(result2.output)["tiers"] == ["cheap", "mid", "strong"]
