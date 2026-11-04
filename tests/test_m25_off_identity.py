from __future__ import annotations

import json

import m25_diag
from m20_trial import ROOT


def test_planner_prompts_identical_at_defaults():
    path = ROOT / "tests/fixtures/m25/planner_prompts_off.json"
    golden = json.loads(path.read_text(encoding="utf-8"))
    assert m25_diag.capture() == golden
