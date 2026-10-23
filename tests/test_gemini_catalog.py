from __future__ import annotations

import filecmp
import re
from pathlib import Path

import pytest

from cora.core.config import load_config
from cora.core.router import HeuristicRouter

ROOT = Path(__file__).resolve().parents[1]
REPO_TOML = ROOT / "cora.toml"
PACKAGED_TOML = ROOT / "src" / "cora" / "data" / "cora.toml"
GEMINI_IDS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
KEY_PATTERN = re.compile("AI" + "za" + r"[0-9A-Za-z_\-]{35}")


def test_tomls_identical():
    assert filecmp.cmp(REPO_TOML, PACKAGED_TOML, shallow=False)


@pytest.mark.parametrize("path", [REPO_TOML, PACKAGED_TOML])
def test_gemini_models(path):
    cfg = load_config(path)
    by_id = {m.id: m for m in cfg.models if m.provider == "gemini"}
    for model_id in GEMINI_IDS:
        assert model_id in by_id
        spec = by_id[model_id]
        assert spec.provider == "gemini"
        assert spec.free_tier is True
        assert spec.tier == "cheap"
    assert HeuristicRouter(cfg).resolve("cheap").provider != "gemini"
    assert HeuristicRouter(cfg).route("What is 2+2?").model.provider != "gemini"
    gemini = cfg.providers["gemini"]
    assert gemini["type"] == "openai_compat"
    assert gemini["base_url"] == GEMINI_BASE_URL
    assert gemini["api_key_env"] == "GEMINI_API_KEY"
    assert gemini["rpm_limit"] == 5


@pytest.mark.parametrize("path", [REPO_TOML, PACKAGED_TOML])
def test_rpm_limit_comment(path):
    text = path.read_text(encoding="utf-8")
    assert re.search(r"^rpm_limit = 5\s+#.*conservative default", text, re.MULTILINE)


def test_no_google_key_pattern():
    roots = [ROOT / "src", ROOT / "tests", ROOT / ".docs"]
    files = [ROOT / "README.md", ROOT / "USAGE.md", ROOT / "cora.toml", ROOT / "pyproject.toml"]
    for root in roots:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    hits = [
        str(p)
        for p in files
        if p.exists() and KEY_PATTERN.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert hits == []
