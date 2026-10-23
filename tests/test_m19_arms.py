from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cora.cli.common import load_resolved
from cora.cli.main import app

REPO = Path(__file__).resolve().parents[1]
ARMS = REPO / "tests" / "fixtures" / "m19" / "arms"
PREREG = REPO / "tests" / "fixtures" / "m19" / "preregistration.md"
CORA_TOML = REPO / "cora.toml"
ENV = {"OPENROUTER_API_KEY": "test-dummy"}

ARM_FILES = {
    "cascade-strong": "cascade-strong.toml",
    "cascade-m1-m2": "cascade-m1-m2.toml",
    "deleg-nudge": "deleg-nudge.toml",
    "keys-on": "keys-on.toml",
}


def _prereg_diff_block(arm: str) -> list[str]:
    lines = PREREG.read_text(encoding="utf-8").splitlines()
    heading = f"#### 설정 {arm}"
    start = lines.index(heading)
    open_idx = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("```diff"))
    close_idx = next(i for i in range(open_idx + 1, len(lines)) if lines[i] == "```")
    return lines[open_idx + 1 : close_idx][2:]


@pytest.mark.parametrize("arm", list(ARM_FILES))
def test_arm_diffs_match_registration(arm: str) -> None:
    base = CORA_TOML.read_text(encoding="utf-8").splitlines()
    fixture = (ARMS / ARM_FILES[arm]).read_text(encoding="utf-8").splitlines()
    diff = list(difflib.unified_diff(base, fixture, n=3, lineterm=""))[2:]
    assert diff == _prereg_diff_block(arm)


def test_rehearsal_config_differs_only_in_strong_model(tmp_path: Path) -> None:
    strong = (ARMS / "cascade-strong.toml").read_text(encoding="utf-8").splitlines()
    rehearsal = (ARMS / "cascade-free-rehearsal.toml").read_text(encoding="utf-8").splitlines()
    assert len(strong) == len(rehearsal)
    changed = [i for i, (a, b) in enumerate(zip(strong, rehearsal, strict=True)) if a != b]
    assert len(changed) == 1
    assert strong[changed[0]].startswith('strong_model = "deepseek/deepseek-v3.2" #')
    assert rehearsal[changed[0]] == (
        'strong_model = "gemini-3.5-flash" #' + strong[changed[0]].split("#", 1)[1]
    )
    cfg, _ = load_resolved(ARMS / "cascade-free-rehearsal.toml", tmp_path)
    assert cfg is not None


def _plan_total(output: str) -> float:
    m = re.search(r"total_max_usd: ([0-9.]+)", output)
    assert m is not None, output
    return float(m.group(1))


def _invoke(argv: list[str]):
    return CliRunner().invoke(app, argv, env=ENV)


def test_live_ceiling_equals_plan_c_s(tmp_path: Path) -> None:
    cfg = str(ARMS / "cascade-strong.toml")
    common = [
        "-c",
        cfg,
        "--suite",
        "e2e",
        "--models",
        "google/gemini-2.5-flash-lite",
        "--protocols",
        "react",
        "--ab",
        "auto-routed",
    ]
    tasks = ["--tasks", "e2e_h01,e2e_h02", "--repeats", "3"]
    plan = _invoke(["bench", "plan", *common, *tasks, "--max-cost", "0.42"])
    assert plan.exit_code == 0, plan.output
    assert "0.420000" in plan.output
    out = tmp_path / "out"
    live = _invoke(
        [
            "bench",
            *common,
            "--live",
            "--sensor",
            "--sensor-source",
            "auto",
            *tasks,
            "--max-cost",
            "0.41",
            "--out",
            str(out),
        ]
    )
    assert live.exit_code == 2, live.output
    msg = "estimated maximum cost $0.420000 for 6 runs exceeds --max-cost $0.41; nothing was called"
    assert msg in live.output
    assert not (out / "report.json").exists()


def test_live_ceiling_equals_plan_d1(tmp_path: Path) -> None:
    cfg = str(ARMS / "deleg-nudge.toml")
    common = [
        "-c",
        cfg,
        "--suite",
        "e2e",
        "--models",
        "google/gemini-2.5-flash-lite",
        "--protocols",
        "react",
        "--ab",
        "deleg-on-par-on",
    ]
    tasks = ["--tasks", "e2e_hx1,e2e_hx2", "--repeats", "3"]
    plan = _invoke(["bench", "plan", *common, *tasks, "--max-cost", "0.39"])
    assert plan.exit_code == 0, plan.output
    assert "0.390000" in plan.output
    out = tmp_path / "out"
    live = _invoke(
        [
            "bench",
            *common,
            "--live",
            "--sensor",
            "--sensor-source",
            "auto",
            *tasks,
            "--max-cost",
            "0.38",
            "--out",
            str(out),
        ]
    )
    assert live.exit_code == 2, live.output
    assert "$0.390000 for 6 runs exceeds --max-cost $0.38" in live.output
    assert not (out / "report.json").exists()


def test_live_ceiling_equals_plan_b(tmp_path: Path) -> None:
    common = [
        "--suite",
        "e2e",
        "--models",
        "google/gemini-2.5-flash-lite",
        "--protocols",
        "react",
    ]
    tasks = ["--tasks", "e2e_h01,e2e_h02", "--repeats", "3"]
    plan = _invoke(["bench", "plan", *common, *tasks, "--max-cost", "0.42"])
    assert plan.exit_code == 0, plan.output
    total = _plan_total(plan.output)
    out = tmp_path / "out"
    live = _invoke(
        [
            "bench",
            *common,
            "--live",
            "--verify-attempts",
            "3",
            *tasks,
            "--max-cost",
            f"{total - 0.01:.6f}",
            "--out",
            str(out),
        ]
    )
    assert live.exit_code == 2, live.output
    assert f"${total:.6f} for 6 runs" in live.output
    assert not (out / "report.json").exists()
