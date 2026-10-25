from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / ".docs/bench-results.md"
HEADING_RE = re.compile(r"^## M20 사전 등록 \(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)$", re.M)
RESULT_RE = re.compile(r"^## M20 결과 \(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)$", re.M)
AMEND_RE = re.compile(r"^## M20 사전 등록 수정 \(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)$", re.M)
PREREG_SHA = "a6202e01622662bbe9682cc9245812d4b4c119470308307d1b1187eac1d76710"


def _prereg() -> str:
    text = BENCH.read_text(encoding="utf-8")
    m = HEADING_RE.search(text)
    assert m is not None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return text[m.start(): m.end() + (nxt.start() if nxt else len(rest))]


def _amend() -> str:
    text = BENCH.read_text(encoding="utf-8")
    m = AMEND_RE.search(text)
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


def test_prereg_unchanged() -> None:
    assert hashlib.sha256(_prereg().rstrip().encode("utf-8")).hexdigest() == PREREG_SHA


def test_amendment_once_and_ordered() -> None:
    text = BENCH.read_text(encoding="utf-8")
    matches = list(AMEND_RE.finditer(text))
    assert len(matches) == 1
    m = HEADING_RE.search(text)
    assert m is not None
    assert matches[0].start() > m.start()
    r = RESULT_RE.search(text)
    if r is not None:
        assert matches[0].start() < r.start()


def test_amendment_items() -> None:
    amend = _amend()
    for token in (
        "diagnosis.md",
        "2026-10-25",
        "--variant deadline",
        "timeout_s = 300",
        "request_deadline_s = 300",
        "call_timeout_s = 960",
        "RR-M20-01",
        "e2e_h01-r2",
        "superseded",
        "interventions = 1",
        "R11",
        "test_planner_system_check_is_shell_command",
        "deepseek-fix1",
        "gemini-rehearsal-fix1",
        "pre-fix",
        "check_runnable",
        "checks.jsonl",
        "--max-iterations",
        "240",
        "200",
        "9600",
        "8000",
        "deepseek-v2",
        "30/2400",
        "$0.675",
        "/credits",
        '"check" is a single runnable shell command that exits 0 when the milestone is done; '
        'omit it if no such command exists, and use "conditions" for deterministic checks.',
    ):
        assert token in amend, token
    deadline = ROOT / "tests/fixtures/m19/arms/deadline.toml"
    digest = hashlib.sha256(deadline.read_bytes()).hexdigest()
    assert digest in amend
