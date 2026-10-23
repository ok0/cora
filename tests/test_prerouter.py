from __future__ import annotations

import builtins
import dataclasses
import filecmp
import inspect
import pathlib
from pathlib import Path

import pytest

import cora.core.prerouter as mod
from cora.core.decider import Score
from cora.core.prerouter import (
    FEATURE_KEYS,
    HistoryRow,
    decide,
    features,
    knn_score,
    read_inputs,
)
from cora.core.shellguard import PathGuard

ROOT = Path(__file__).resolve().parents[1]
PROMPT = "Read REQUIREMENTS.md and implement it. Required files: ledger/book.py, ledger/report.py."


def _ws(tmp: Path, with_grader: bool) -> Path:
    files = {
        "REQUIREMENTS.md": "Implement `parse_entry` in `ledger/book.py` and add `BookReport`.\n",
        "ledger/book.py": "def parse_entry(x):\n    return x\n",
        "ledger/other.py": "X = 1\n",
    }
    if with_grader:
        files[".cora_grader/test_hidden.py"] = (
            "from ledger.book import parse_entry\nBookReport = 1\n"
        )
        files["hidden/grader.py"] = "parse_entry\n"
    for rel, text in files.items():
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp


def test_read_inputs_probe(tmp_path: Path) -> None:
    ws = _ws(tmp_path, False)
    inp = read_inputs(PROMPT, ws)
    assert inp.repo.named_paths == ("REQUIREMENTS.md", "ledger/book.py", "ledger/report.py")
    assert inp.repo.named_missing == 1
    assert inp.repo.n_files == 3
    assert inp.repo.n_py_files == 2
    assert inp.repo.total_lines == 1 + 2 + 1
    assert inp.repo.scope_files == 1
    assert inp.spec_text.startswith("=== REQUIREMENTS.md ===\n")
    assert inp.repo.spec_chars == len(inp.spec_text)


def test_spec_cap(tmp_path: Path) -> None:
    (tmp_path / "REQUIREMENTS.md").write_text("a" * 10_000, encoding="utf-8")
    inp = read_inputs("Read REQUIREMENTS.md", tmp_path)
    assert len(inp.spec_text) == 6000


def test_features_order_and_judge(tmp_path: Path) -> None:
    inp = read_inputs(PROMPT, _ws(tmp_path, False))
    assert list(features(inp)) == list(FEATURE_KEYS)
    with_judge = features(inp, Score(value=7, lo=0, hi=24, confidence=1.0))
    assert with_judge["judge"] == 7.0
    assert list(with_judge)[-1] == "judge"
    fallback = features(inp, Score(value=7, lo=0, hi=24, confidence=1.0, fallback_used=True))
    assert "judge" not in fallback


def test_deterministic(tmp_path: Path) -> None:
    a = read_inputs(PROMPT, _ws(tmp_path / "a", False))
    b = read_inputs(PROMPT, _ws(tmp_path / "b", False))
    assert a == b
    x = features(a)
    d1 = decide(x, signal="scope", threshold=2.0)
    d2 = decide(x, signal="scope", threshold=2.0)
    assert d1 == d2
    assert d1.inputs_hash == d2.inputs_hash
    assert decide(x, signal="scope", threshold=3.0).inputs_hash != d1.inputs_hash


def test_tie_goes_strong(tmp_path: Path) -> None:
    x = features(read_inputs(PROMPT, _ws(tmp_path, False)))
    assert x["scope_files"] + x["named_missing"] == 2.0
    assert decide(x, signal="scope", threshold=2.0).tier == "strong"
    assert decide(x, signal="scope", threshold=2.5).tier == "cheap"


def test_grader_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws_a = _ws(tmp_path / "a", False)
    ws_b = _ws(tmp_path / "b", True)
    recorded: list[str] = []

    orig_read_bytes = pathlib.Path.read_bytes
    orig_read_text = pathlib.Path.read_text
    orig_path_open = pathlib.Path.open
    orig_open = builtins.open

    def read_bytes(self, *a, **k):
        recorded.append(str(self))
        return orig_read_bytes(self, *a, **k)

    def read_text(self, *a, **k):
        recorded.append(str(self))
        return orig_read_text(self, *a, **k)

    def path_open(self, *a, **k):
        recorded.append(str(self))
        return orig_path_open(self, *a, **k)

    def builtin_open(file, *a, **k):
        recorded.append(str(file))
        return orig_open(file, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_bytes", read_bytes)
    monkeypatch.setattr(pathlib.Path, "read_text", read_text)
    monkeypatch.setattr(pathlib.Path, "open", path_open)
    monkeypatch.setattr(builtins, "open", builtin_open)

    guard_a = PathGuard(ws_a, [ws_a / "hidden"])
    guard_b = PathGuard(ws_b, [ws_b / "hidden"])
    inp_a = read_inputs(PROMPT, ws_a, guard=guard_a)
    x_a = features(inp_a)
    recorded.clear()
    inp_b = read_inputs(PROMPT, ws_b, guard=guard_b)
    x_b = features(inp_b)

    assert x_b == x_a
    assert decide(x_b, signal="scope", threshold=2.0) == decide(x_a, signal="scope", threshold=2.0)
    assert not [p for p in recorded if ".cora_grader" in p or "/hidden/" in p]


def test_knn_excludes_task_and_none() -> None:
    x = {"scope_files": 0.0}
    h = [
        HistoryRow("t0", {"scope_files": 0.0}, False),
        HistoryRow("t1", {"scope_files": 0.0}, True),
        HistoryRow("t2", {"scope_files": 1.0}, True),
        HistoryRow("t3", {"scope_files": 10.0}, False),
        HistoryRow("t4", {"scope_files": 11.0}, False),
    ]
    assert knn_score(x, h, k=3, exclude_task="t0") == pytest.approx(1 / 3)
    assert knn_score(x, h, k=3, exclude_task="t9") == pytest.approx(1 / 3)
    assert knn_score(x, h, k=1, exclude_task="t0") == 0.0
    assert knn_score(x, h, k=1, exclude_task="t9") == 1.0
    assert knn_score(x, h[:3], k=3, exclude_task="t0") is None
    d = decide(x, signal="knn", threshold=0.5, history=h[:3], task_id="t0")
    assert d.tier == "strong"
    assert "knn_insufficient_history" in d.reasons


def test_no_forbidden_parameters() -> None:
    forbidden = ("grader", "outcome", "calibration", "weight", "solved", "label")
    funcs = [
        fn for _, fn in inspect.getmembers(mod, inspect.isfunction) if fn.__module__ == mod.__name__
    ]
    assert funcs
    for fn in funcs:
        for name in inspect.signature(fn).parameters:
            assert not any(f in name for f in forbidden), (fn.__name__, name)
    for cls in (mod.RouteInputs, mod.RepoProbe, mod.PreRoute):
        for field in dataclasses.fields(cls):
            assert not any(f in field.name for f in forbidden), (cls.__name__, field.name)


def test_unwired() -> None:
    for rel in ("src/cora/core/router.py", "src/cora/core/config.py", "cora.toml"):
        assert "prerouter" not in (ROOT / rel).read_text(encoding="utf-8")
    assert filecmp.cmp(ROOT / "cora.toml", ROOT / "src/cora/data/cora.toml", shallow=False)
