from __future__ import annotations

import json
import os
import re

import m20_trial
from m20_trial import ROOT

FIX = ROOT / "tests/fixtures/m25"
ALLOWED_CLASSES = {
    "wrong_path_or_name",
    "over_specified",
    "later_milestone",
    "env_tool_mismatch",
    "other",
}
BLOCKED_ITEMS = (
    "D8 raw planner reply + events",
    "deepseek-fix3 plan.toml x5 + per-condition reference details",
    "gemini-rehearsal-fix3 plan.toml x5",
)


def _jsonl(name: str) -> list[dict]:
    text = (FIX / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _fixture_files() -> list:
    return sorted(p for p in FIX.rglob("*") if p.is_file())


def test_manifest_inventory():
    man = json.loads((FIX / "MANIFEST.json").read_text(encoding="utf-8"))
    for rel in man["files"]:
        assert (FIX / rel).is_file(), rel
    blocked = {b["item"]: b for b in man["blocked"]}
    for item in BLOCKED_ITEMS:
        assert item in blocked, item
        assert blocked[item]["searched"], item


def test_no_key_material():
    literals = [os.environ[v] for v in m20_trial.KEY_ENV_VARS if len(os.environ.get(v, "")) >= 6]
    hits = []
    for p in _fixture_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        scanned = any(rx.search(text) for rx in m20_trial.KEY_SCAN_RES)
        if scanned or any(v in text for v in literals):
            hits.append(str(p.relative_to(ROOT)))
    assert hits == []


def test_sanitized_paths():
    """Only absolute host paths count.

    Plan-authored literals such as '/c/Users/a b' are not host paths.
    """
    host_path = re.compile(r"(?<!\w)/(?:Users|var/folders|private/var)/")
    for p in _fixture_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        assert host_path.search(text) is None, str(p.relative_to(ROOT))


def test_every_ref_failure_classified():
    failing = {
        (r["plan"], r["milestone"], r["field"])
        for r in _jsonl("refcheck.jsonl")
        if not r["pass_ref"]
    }
    classes = _jsonl("refcheck_classes.jsonl")
    assert {(r["plan"], r["milestone"], r["field"]) for r in classes} == failing
    assert all(r["class"] in ALLOWED_CLASSES for r in classes)


def test_denial_cites_exist():
    for row in _jsonl("denials.jsonl"):
        rel, _, num = row["cite"].rpartition(":")
        path = ROOT / rel
        assert path.is_file(), rel
        ev = json.loads(path.read_text(encoding="utf-8").splitlines()[int(num) - 1])
        assert ev["type"] in ("check", "policy_decision", "tripwire"), row["cite"]


def test_tripcheck_n08_r2_same_response():
    rows = [
        r
        for r in _jsonl("tripcheck.jsonl")
        if r["events"].endswith("20261028-120515-8eca84/events.jsonl")
    ]
    assert len(rows) == 1
    assert rows[0]["same_response"] is True
    assert rows[0]["count"] == 3


def test_d5_evidence_lines():
    rows = [r for r in _jsonl("denials.jsonl") if r["id"] == "D5"]
    assert len(rows) == 1
    evidence = rows[0]["evidence"]
    assert ":24-28" in evidence
    assert "failed tool_calls :32-36" in evidence
    assert "tripwire counted :34-36" in evidence
