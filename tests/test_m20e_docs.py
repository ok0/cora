from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m20_trial  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / ".docs" / "bench-results.md"
FIX = ROOT / "tests" / "fixtures" / "m20d"
ART = FIX / "artifacts" / "m20d-deepseek-v2"
CFG = FIX / "artifacts" / "cora-m20d-deepseek-deadline.toml"
N08_RUNS = ("e2e_n08-r0", "e2e_n08-r1", "e2e_n08-r2")
H03_RUNS = ("e2e_h03-r0", "e2e_h03-r1")
HEADING = re.compile(r"^## M20e 결과 \(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)$", re.M)


@pytest.fixture(scope="module")
def section() -> str:
    text = DOC.read_text(encoding="utf-8")
    m = HEADING.search(text)
    assert m, "M20e heading not found"
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return text[m.start(): m.end() + (nxt.start() if nxt else len(rest))]


def _outcome(name: str) -> dict:
    return json.loads((ART / name / "outcome.json").read_text(encoding="utf-8"))


def test_deny_table_complete(section):
    cites = []
    for run in N08_RUNS:
        cites += [row["cite"] for row in m20_trial.deny_table(ART / run)]
    assert len(cites) == 43
    missing = [c for c in cites if c not in section]
    assert not missing, missing[:5]


def test_wall_numbers(section):
    out = _outcome("e2e_h03-r1")
    wall = m20_trial.wall_breakdown(ART / "e2e_h03-r1", out)
    for key in ("llm_s", "tool_s", "gaps_s", "unattributed_s"):
        assert f"{wall[key]:.1f}" in section, key


def test_cost_numbers(section):
    prices = m20_trial.model_prices(CFG, "deepseek/deepseek-v3.2")
    for run in H03_RUNS:
        c = m20_trial.cost_check(ART / run, _outcome(run), prices)
        assert f"{c['metered_total']:.6f}" in section, run
        assert f"{c['priced']:.6f}" in section, run
    assert "0.004238" in section


def test_verdicts(section):
    keys = ("여기서 수정", "M25", "M22", "M22b", "BLUEPRINT CHANGE", "문서화된 한계")
    for tag in ("R10", "R11", "R12", "R13", "R14"):
        lines = [ln for ln in section.splitlines() if ln.startswith(f"- 판정 ({tag}):")]
        assert lines, tag
        assert any(k in lines[0] for k in keys), tag


def test_corrections(section):
    for token in ("cap_bound", "False → True", "gate_failed_final"):
        assert token in section, token


def test_earlier_text_untouched():
    try:
        head = subprocess.run(
            ["git", "show", "HEAD:.docs/bench-results.md"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git or HEAD copy unavailable")
    assert DOC.read_bytes().startswith(head)
