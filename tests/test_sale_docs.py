from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCH = ROOT / ".docs" / "architecture.md"
TIERS = ROOT / "src" / "cora" / "data" / "sale_tiers.toml"
CASES = ROOT / "src" / "cora" / "data" / "sale_cases.synthetic.jsonl"
NOTE = "SYNTHETIC / PLACEHOLDER, 실측 아님"


def test_usage_documents_sale():
    text = USAGE.read_text(encoding="utf-8")
    needles = [
        "[sale]",
        "cora sale eval",
        "### `cora sale`",
        "`--tiers`",
        "`--reward`",
        "`--budget-cap`",
        "`--cases`",
        "budget_cap",
        "max_escalations",
        "tiers_file",
        "solve_rate",
        "plan_text",
        "outcomes",
        "always-cheap",
        "always-strong",
        "heuristic-router",
        "sale-lite",
        "over_budget",
        "estimated_cost",
        "expected_success",
        NOTE,
        "sale_tiers.toml",
        "sale_cases.synthetic.jsonl",
    ]
    for needle in needles:
        assert needle in text, needle


def test_placeholder_marks_on_data_files():
    tiers_text = TIERS.read_text(encoding="utf-8")
    assert "MEASURED" in tiers_text
    assert "M15" in tiers_text
    assert "Source:" in tiers_text
    assert tomllib.loads(tiers_text)["placeholder"] is False
    for line in CASES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        assert isinstance(obj, dict)
        assert obj["note"] == NOTE


def test_architecture_mentions_sale():
    text = ARCH.read_text(encoding="utf-8")
    assert "core/sale.py" in text
    assert "sale_eval.py" in text
