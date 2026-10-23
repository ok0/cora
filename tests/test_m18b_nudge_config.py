from __future__ import annotations

import filecmp
import re
from pathlib import Path

import pytest

from conftest import CFG_TOML
from cora.core.config import ConfigError, parse_config
from cora.core.prompts import DELEGATE_NUDGE, build_system_prompt
from test_headless import base, run_cli, write_cfg

ROOT = Path(__file__).resolve().parents[1]
TOMLS = (ROOT / "cora.toml", ROOT / "src" / "cora" / "data" / "cora.toml")


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


def test_toml_copies_have_nudge_false():
    for p in TOMLS:
        text = p.read_text(encoding="utf-8")
        assert re.search(r"^nudge = false", text, re.M), p
    assert filecmp.cmp(TOMLS[0], TOMLS[1], shallow=False)


def test_nudge_default_and_invalid():
    cfg = parse_config({"models": _model_list()})
    assert cfg.delegation.nudge is False
    for bad in ("yes", 1):
        with pytest.raises(ConfigError, match="nudge"):
            parse_config({"models": _model_list(), "delegation": {"nudge": bad}})


def test_nudge_invalid_exit_2(ws, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML + '\n[delegation]\nnudge = "yes"\n')
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    assert result.exit_code == 2
    assert "nudge" in result.stdout


def test_unknown_delegation_key_exit_2(ws, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML + "\n[delegation]\nnudges = true\n")
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    assert result.exit_code == 2


@pytest.mark.parametrize("protocol", ["react", "native"])
def test_build_system_prompt_nudge_unit(tmp_path, protocol):
    kwargs = {"repo_map": "m", "protocol": protocol}
    plain = build_system_prompt(tmp_path, "- x: y", [], "CTX", **kwargs)
    assert build_system_prompt(tmp_path, "- x: y", [], "CTX", nudge=False, **kwargs) == plain
    on = build_system_prompt(tmp_path, "- x: y", [], "CTX", nudge=True, **kwargs)
    assert on == plain + DELEGATE_NUDGE
    assert on.endswith(DELEGATE_NUDGE)
