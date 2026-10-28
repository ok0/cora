from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m20_trial  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "m20d"
ART = FIX / "artifacts"
RUN_DIR = ART / "m20d-deepseek-v2"
BAD_STRINGS = ("/var/folders/", "/private/var/")
HOST_USER_RE = re.compile(r"/Users/[A-Za-z0-9._-]+/")
SESSION_COUNTS = {
    "e2e_n08-r0": 5,
    "e2e_n08-r1": 5,
    "e2e_n08-r2": 1,
    "e2e_h03-r0": 7,
    "e2e_h03-r1": 6,
}


@pytest.fixture
def manifest() -> dict:
    return json.loads((FIX / "MANIFEST.json").read_text("utf-8"))


def _all_fixture_files() -> list[Path]:
    return sorted(p for p in FIX.rglob("*") if p.is_file() and p.name != "MANIFEST.json")


def _run_id(run: str) -> str:
    return json.loads((RUN_DIR / run / "outcome.json").read_text("utf-8"))["run_id"]


def test_inventory(manifest):
    expected = {p.relative_to(FIX).as_posix() for p in _all_fixture_files()}
    assert set(manifest["files"]) == expected
    top = ("runs.jsonl", "extract.jsonl", "rehearsal.jsonl", "ledger.md", "m20d_extract.py.txt")
    for name in top:
        assert (FIX / name).is_file(), name
    assert (ART / "cora-m20d-deepseek-deadline.toml").is_file()
    for run in m20_trial.M20D_RUNS:
        base = RUN_DIR / run
        assert (base / "outcome.json").is_file(), run
        rid = _run_id(run)
        for name in ("checkpoint.json", "events.jsonl", "plan.toml"):
            assert (base / "projects" / rid / name).is_file(), (run, name)
        assert (base / "meta" / "time.txt").is_file(), run
    for run, count in SESSION_COUNTS.items():
        sessions = sorted((RUN_DIR / run / "sessions").glob("*/events.jsonl"))
        assert len(sessions) == count, run
    for run in ("e2e_n08-r0", "e2e_h03-r0"):
        assert (ART / "m20d-rehearsal" / f"{run}" / "outcome.json").is_file(), run
    if manifest["blocked"]:
        pytest.fail(f"rescue reported blocked items: {manifest['blocked']}")
    assert manifest["blocked"] == []


def test_no_key_material():
    env_vals = [v for name in m20_trial.KEY_ENV_VARS if (v := os.environ.get(name)) and len(v) >= 8]
    for path in _all_fixture_files():
        text = path.read_text("utf-8", errors="replace")
        for rx in m20_trial.KEY_SCAN_RES:
            assert not rx.search(text), f"{path.name}: {rx.pattern}"
        for val in env_vals:
            assert val not in text, path.name


def test_sanitized_paths():
    for path in _all_fixture_files():
        text = path.read_text("utf-8", errors="replace")
        for bad in BAD_STRINGS:
            assert bad not in text, (path.name, bad)
        assert not HOST_USER_RE.search(text), path.name


def test_redactions_listed(manifest):
    assert isinstance(manifest["redactions"], list)
    for entry in manifest["redactions"]:
        assert {"file", "line", "pattern"} <= set(entry)
    manifest_text = (FIX / "MANIFEST.json").read_text("utf-8")
    for rx in m20_trial.KEY_SCAN_RES:
        assert not rx.search(manifest_text), rx.pattern
