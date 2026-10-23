from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / ".docs/bench-results.md"
ARCH = ROOT / ".docs/architecture.md"
PROMPTS = (
    ROOT / "tests/fixtures/m19e/judge-prompt-s1a.txt",
    ROOT / "tests/fixtures/m19e/judge-prompt-s1b.txt",
)
TASKS = (
    "query_client_timeout",
    "query_total_backoff",
    "query_env_override",
    "multi_edit_delay_cap",
    "multi_edit_rename_cents",
    "multi_edit_region",
    "e2e_todo_cli",
    "e2e_text_stats",
    "e2e_rest_notes",
    "e2e_md_to_html",
    "e2e_refactor_inventory",
    "e2e_h01",
    "e2e_h02",
    "e2e_h03",
    "e2e_h04",
    "e2e_h05",
    "e2e_h06",
    "e2e_hx1",
    "e2e_hx2",
)
PASS_RULE = (
    "PASS iff at least one signal meets all of: (i) AUROC ≥ 0.75; (ii) permutation p ≤ 0.025 "
    "(0.10 Bonferroni over 4 signals); (iii) S1–S3: AUROC > the set-identity baseline's; "
    "(iv) its simulated policy has solved-per-dollar > always-strong's AND solved ratio ≥ "
    "always-strong's − 0.05."
)
ALLOWED = (
    "The prompt text; spec files the prompt names that exist in the workspace "
    "(e.g. `REQUIREMENTS.md`); "
    "workspace metadata from a read-only walk (paths, sizes, line counts, "
    "top-level symbols via `ast` for `.py`); "
    "an optional judge score from a `Decider`; an optional history of OTHER tasks' outcomes."
)
HEADING_RE = re.compile(r"^## M19e 1단계 사전 등록 \(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)$", re.M)


def _prereg() -> str:
    text = BENCH.read_text(encoding="utf-8")
    m = HEADING_RE.search(text)
    assert m is not None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return text[m.start(): m.end() + (nxt.start() if nxt else len(rest))]


def test_preregistration_present() -> None:
    text = BENCH.read_text(encoding="utf-8")
    assert len(HEADING_RE.findall(text)) == 1
    assert "## M19e 1단계 사전 등록 (" in text


def test_preregistration_lists_dataset() -> None:
    section = _prereg()
    for t in TASKS:
        if t.startswith("e2e_h0"):
            continue
        assert t in section, t
    assert "e2e_h01..e2e_h06" in section
    assert "e2e_hx1" in section and "e2e_hx2" in section
    for cell in ("A-e2e", "A2-e2e", "OFF-md", "retest-cheap", "A cheap", "C strong"):
        assert cell in section, cell


def test_preregistration_signals_and_rule() -> None:
    section = _prereg()
    for token in (
        "cheap_ok",
        "S1a",
        "S1b",
        "S2",
        "S3",
        "S4",
        "claude-sonnet-5-5",
        "gemini-3.5-flash-lite",
        PASS_RULE,
        "Bonferroni",
        "20261022",
    ):
        assert token in section, token


def test_prompt_hashes_registered() -> None:
    section = _prereg()
    for path in PROMPTS:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        assert digest in section, path.name


def test_rubric_at_most_8_criteria() -> None:
    lines = (PROMPTS[0].read_text(encoding="utf-8")).splitlines()
    assert len([ln for ln in lines if re.match(r"^c[1-8] ", ln)]) == 8


def test_allowed_inputs_verbatim() -> None:
    assert ALLOWED in ARCH.read_text(encoding="utf-8")


RESULT_HEADING_RE = re.compile(
    r"^## M19e 1단계 결과 \(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)$", re.M
)
SIGNALS = ROOT / "tests/fixtures/m19e/signals.md"
JUDGE_ROWS = ROOT / "tests/fixtures/m19e/judge-scores.jsonl"


def _result() -> str:
    text = BENCH.read_text(encoding="utf-8")
    m = RESULT_HEADING_RE.search(text)
    assert m is not None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return text[m.start(): m.end() + (nxt.start() if nxt else len(rest))]


def test_result_section() -> None:
    result = _result()
    sig = SIGNALS.read_text(encoding="utf-8")
    decision = sig.split("\n## Decision\n", 1)[1]
    prefixes = ("PASS", "FAIL", "S1a-only", "S4-only")
    lines = [ln for ln in decision.splitlines() if ln.startswith(prefixes)]
    assert lines
    for ln in lines:
        assert ln in result, ln


def test_usage_note() -> None:
    text = (ROOT / "USAGE.md").read_text(encoding="utf-8")
    for token in ("prerouter", "실험", "미연결"):
        assert token in text, token


def test_judge_rows() -> None:
    raw_lines = JUDGE_ROWS.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(ln) for ln in raw_lines if ln.strip()]
    hashes = {
        "S1a": hashlib.sha256(PROMPTS[0].read_bytes()).hexdigest()[:16],
        "S1b": hashlib.sha256(PROMPTS[1].read_bytes()).hexdigest()[:16],
    }
    for judge in hashes:
        judged = [r for r in rows if r["judge"] == judge]
        assert sorted(r["task"] for r in judged) == sorted(TASKS), judge
    for r in rows:
        assert r["judge_id"]
        assert r["prompt_hash"] == hashes[r["judge"]]
        assert "raw" in r
        assert r["cost_usd"] == 0.0
        assert r["status"] in ("ok", "blocked")
