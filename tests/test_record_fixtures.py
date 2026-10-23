from __future__ import annotations

import json
import re
from pathlib import Path

from cora.core.config import load_config

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/recordings"
FAKE_PROVIDERS = {"scripted", "scripted_stream", "fixed_usage"}
FREE_MODELS = {m.id for m in load_config(ROOT / "cora.toml").models if m.free_tier}
# M14 R1: capped cheap-model live recordings; secret scan unchanged
CHEAP_RECORDED_MODELS = {"google/gemini-2.5-flash-lite"}
SECRET_RES = (
    r"AIza[0-9A-Za-z_\-]{20,}",
    r"sk-[A-Za-z0-9][A-Za-z0-9_\-]{15,}",
    r"DUMMY-not-a-real-key",
    r"gm-test-DUMMY-key",
    r"(?i)authorization",
    r"(?i)bearer ",
)


def check_tree(root: Path) -> list[str]:
    problems: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SECRET_RES:
            for _ in re.finditer(pattern, text):
                problems.append(f"{path}: secret-like text matches {pattern!r}")
    for path in root.rglob("??/*.json"):
        if not path.is_file():
            continue
        entry = json.loads(path.read_text(encoding="utf-8"))
        if "key" not in entry:
            continue
        allowed = FREE_MODELS | CHEAP_RECORDED_MODELS
        if entry.get("provider") not in FAKE_PROVIDERS and entry.get("model") not in allowed:
            problems.append(f"{path}: provider/model not a fake, free-tier or admitted cheap model")
        if entry["key"] != path.stem:
            problems.append(f"{path}: key does not match file name")
    return problems


def test_committed_fixtures_clean():
    assert check_tree(FIXTURES) == []


def test_checker_flags_bad_tree(tmp_path):
    key = "ab" + "c" * 62
    entry = {
        "format": 1,
        "key": key,
        "provider": "openrouter",
        "model": "openai/gpt-x",
        "response": {"text": "AIza" + "x" * 35},
    }
    path = tmp_path / "ab" / f"{key}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(entry), encoding="utf-8")
    assert len(check_tree(tmp_path)) >= 2


def test_checker_admits_cheap_recording(tmp_path):
    key = "cd" + "e" * 62
    entry = {
        "format": 1,
        "key": key,
        "provider": "openrouter",
        "model": "google/gemini-2.5-flash-lite",
        "response": {"text": "ok"},
    }
    path = tmp_path / "cd" / f"{key}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(entry), encoding="utf-8")
    assert check_tree(tmp_path) == []
    entry["response"]["text"] = "Bearer abc"
    path.write_text(json.dumps(entry), encoding="utf-8")
    assert len(check_tree(tmp_path)) == 1
