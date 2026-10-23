from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from conftest import CFG_TOML
from cora.core.config import SaleSettings, load_config, parse_config
from cora.core.errors import ConfigError

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]


def test_default_sale_is_off():
    cfg = parse_config(tomllib.loads(CFG_TOML))
    assert cfg.sale == SaleSettings()
    assert cfg.sale.enabled is False
    assert cfg.sale.bids == "heuristic"


@pytest.mark.parametrize(
    "path", [ROOT / "cora.toml", ROOT / "src/cora/data/cora.toml"], ids=["root", "data"]
)
def test_shipped_configs_keep_sale_off(path):
    assert load_config(path).sale == SaleSettings()


def test_shipped_configs_byte_identical():
    assert (ROOT / "cora.toml").read_bytes() == (ROOT / "src/cora/data/cora.toml").read_bytes()


def test_sale_section_parsed():
    text = CFG_TOML + (
        '\n[sale]\nenabled = true\nbids = "llm"\nreward = 5\nbudget_cap = 3\n'
        'max_escalations = 2\ntiers_file = "t.toml"\n'
    )
    cfg = parse_config(tomllib.loads(text))
    assert cfg.sale == SaleSettings(True, "llm", 5.0, 3.0, 2, "t.toml")
    assert isinstance(cfg.sale.reward, float)


@pytest.mark.parametrize(
    "snippet",
    [
        'enabled = "yes"',
        'bids = "gpt"',
        "reward = 0",
        "budget_cap = -1",
        "max_escalations = -1",
        "max_escalations = true",
        "tiers_file = 3",
        "foo = 1",
    ],
)
def test_bad_sale_values_rejected(snippet):
    text = CFG_TOML + "\n[sale]\n" + snippet + "\n"
    with pytest.raises(ConfigError, match=r"\[sale\]"):
        parse_config(tomllib.loads(text))


@pytest.mark.parametrize(
    "rel",
    ["src/cora/core/agent.py", "src/cora/core/router.py", "src/cora/cli/repl.py"],
)
def test_runtime_paths_do_not_use_sale(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "cora.core.sale" not in text
