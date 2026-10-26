import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "tests" / "fixtures" / "m20" / "artifacts"
BENCH = ROOT / ".docs" / "bench-results.md"
SCRIPT = ROOT / "tests" / "m20a_artifacts.py"
GROUPS = ("v2", "p2", "rr", "p1", "p1b", "p1c", "g0", "g0b", "g0c")
PLAN_GROUPS = {"p1", "p1b", "p1c", "g0", "g0b", "g0c"}
RUNS = ("e2e_h01-r1", "e2e_h03-r0", "e2e_h03-r1", "e2e_h03-r2", "e2e_n08-r0", "e2e_n08-r1")
KEY_RES = (
    re.compile(r"sk-or-v1-[0-9a-f]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
)
BAD_STRINGS = ("/var/folders/", "/private/var/")
HOST_USER_RE = re.compile(r"/Users/[A-Za-z0-9._-]+/")
CITE_RE = re.compile(r"([\w./-]+/events\.jsonl):(\d+)")
EVENT_TYPES = {"policy_decision", "check", "tripwire", "stop"}
PLACEHOLDER_KEYS = {"<M20>", "<TMP>", "<HOME>", "<TMP-PARTIAL>"}


def _load_script():
    spec = importlib.util.spec_from_file_location("m20a_artifacts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def manifest():
    path = ARTIFACTS / "MANIFEST.json"
    if not path.is_file():
        pytest.skip("R1 blocked: artifacts dir missing")
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_files_exist(manifest):
    for rel in manifest["files"]:
        assert (ARTIFACTS / rel).is_file(), rel
    assert manifest["blocked"] == [] or all(b["group"] in GROUPS for b in manifest["blocked"])


def test_events_absent_documented(manifest):
    non_plan = set()
    for a in manifest["absent_at_source"]:
        if a["group"] in PLAN_GROUPS:
            assert a["reason"] == "absent at source (plan-only run)", a
        else:
            non_plan.add((a["group"], a["run"]))
            assert a["reason"] == "absent at source (no session started: planner error)", a
            assert a["errors"], a
        assert a["reason"] != "absent at source (unexplained)", a
    assert non_plan == {("v2", "e2e_n08-r2")}
    outcome_path = ARTIFACTS / "v2" / "e2e_n08-r2" / "outcome.json"
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["session_id"] is None
    assert outcome["run_id"] is None
    assert outcome["iterations"] == 0
    assert outcome["exit_code"] == 2
    for g in ("v2", "p2", "rr"):
        assert any(
            f.startswith(g + "/") and f.endswith("events.jsonl") for f in manifest["files"]
        ), g


def test_sanitized(manifest):
    files = [p for p in ARTIFACTS.rglob("*") if p.is_file()]
    assert files
    home = os.path.expanduser("~")
    for path in files:
        text = path.read_text(encoding="utf-8")
        for bad in BAD_STRINGS:
            assert bad not in text, (path, bad)
        assert not HOST_USER_RE.search(text), path
        if len(home) > 1:
            assert home not in text, (path, home)
        for rx in KEY_RES:
            assert not rx.search(text), (path, rx.pattern)


def test_partial_tmp_recorded(manifest):
    partial = manifest["sanitize"]["partial_tmp"]
    assert partial
    assert set(manifest["sanitize"]["placeholders"]) == PLACEHOLDER_KEYS
    for entry in partial:
        assert entry["file"] in manifest["files"], entry
        lines = (ARTIFACTS / entry["file"]).read_text(encoding="utf-8").splitlines()
        assert "<TMP-PARTIAL>" in lines[entry["line"] - 1], entry
    total = 0
    for rel in manifest["files"]:
        text = (ARTIFACTS / rel).read_text(encoding="utf-8")
        total += sum(1 for line in text.splitlines() if "<TMP-PARTIAL>" in line)
    assert total == len(partial)


def test_sanitize_unit():
    mod = _load_script()
    text, partial = mod._sanitize('a\n"File \\"/private/var/folders/8m/082k"}\nb', [])
    lines = text.split("\n")
    assert len(lines) == 3
    assert "<TMP-PARTIAL>" in lines[1]
    assert "/var/folders" not in text
    assert partial == [2]
    kept, none = mod._sanitize("/c/Users/a b/x.txt", [])
    assert kept == "/c/Users/a b/x.txt"
    assert none == []


def test_m20a_classification_citations(manifest):
    lines = BENCH.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## M20a 결과"))
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^## ", lines[i])),
        len(lines),
    )
    section = "\n".join(lines[start:end])
    cites = CITE_RE.findall(section)
    assert len(cites) >= 6
    for rel, num in cites:
        target = ARTIFACTS / rel
        assert target.is_file(), rel
        file_lines = target.read_text(encoding="utf-8").splitlines()
        line = file_lines[int(num) - 1]
        assert json.loads(line)["type"] in EVENT_TYPES, (rel, num)
    for run in RUNS:
        assert run in section, run
