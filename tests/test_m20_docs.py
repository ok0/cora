from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / ".docs/bench-results.md"
HEADING_RE = re.compile(r"^## M20 사전 등록 \(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)$", re.M)
RESULT_RE = re.compile(r"^## M20 결과 \(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)$", re.M)


def _prereg() -> str:
    text = BENCH.read_text(encoding="utf-8")
    m = HEADING_RE.search(text)
    assert m is not None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return text[m.start(): m.end() + (nxt.start() if nxt else len(rest))]


def test_prereg_exists_once() -> None:
    text = BENCH.read_text(encoding="utf-8")
    assert len(HEADING_RE.findall(text)) == 1


def test_prereg_items() -> None:
    section = _prereg()
    for token in (
        "deepseek/deepseek-v3.2",
        'pin = "deepseek/deepseek-v3.2"',
        "e2e_h01",
        "e2e_h03",
        "e2e_n08",
        "e2e_h02",
        "e2e_h05",
        "e2e_h06",
        "$2.00",
        "--max-cost",
        "not measured (budget)",
        "M19e3 deferred by user 2026-10-23",
        "report-only",
        "free_tier",
        "no baseline (not measured)",
    ):
        assert token in section, token
    digest = hashlib.sha256(ROOT.joinpath("cora.toml").read_bytes()).hexdigest()
    assert digest in section


def test_prereg_before_results() -> None:
    text = BENCH.read_text(encoding="utf-8")
    m = HEADING_RE.search(text)
    assert m is not None
    r = RESULT_RE.search(text)
    if r is not None:
        assert r.start() > m.start()
