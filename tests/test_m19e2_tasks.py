import math
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from cora.bench import e2e
from cora.bench.e2e import E2ETask, load_e2e_tasks

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests/fixtures/m19e2/manifest.toml"
NEW = [t for t in load_e2e_tasks() if t.id.startswith("e2e_n")]
IDS = [t.id for t in NEW]
DIR_RE = re.compile(r"^2\d\d_n\d\d_[a-z0-9_]+$")
TIER_WORDS = re.compile(r"\b(easy|medium|hard|difficulty|tier)\b", re.I)
LIMITS = {"easy": (900, 20), "medium": (1800, 25), "hard": (2400, 30)}
LEAK = ("grade.py", ".cora_grader", "manifest", "e2e_n")


def _manifest() -> dict:
    return tomllib.loads(MANIFEST.read_text(encoding="utf-8"))


def _entry(tid: str) -> dict:
    return next(e for e in _manifest()["task"] if e["id"] == tid)


def _task(tid: str) -> E2ETask:
    return next(t for t in NEW if t.id == tid)


def _files(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


def _changed(task: E2ETask) -> set[str]:
    template = _files(task.template_dir)
    changed = {
        rel
        for rel, data in _files(task.reference_dir).items()
        if template.get(rel) != data
    }
    return changed | set(task.reference_delete)


def _cost(i: int, o: int) -> float:
    return max(0.05, math.ceil(round(3 * (i * 0.10 + o * 0.40) / 1e6 * 100, 6)) / 100)


def _pytest(ws: Path) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=ws,
        env={**e2e.grader_env(ws), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    ).returncode


def test_count_and_naming() -> None:
    assert 12 <= len(NEW) <= 16
    for t in NEW:
        assert DIR_RE.match(t.root.name)
        assert t.id == "e2e_" + t.root.name.split("_")[1]
    dirs = e2e.e2e_tasks_dir().iterdir()
    new_dirs = {d.name for d in dirs if d.is_dir() and d.name.startswith("2")}
    assert new_dirs <= {t.root.name for t in NEW}


def test_manifest_covers_exactly() -> None:
    m = _manifest()
    ids = [e["id"] for e in m["task"]]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(IDS)
    by_id = {t.id: t for t in NEW}
    for e in m["task"]:
        assert e["dir"] == by_id[e["id"]].root.name
        assert e["source"] == "authored" or (e.get("license") and e.get("user_confirmed") is True)
    assert m["authoring_note"].strip()
    replaced = {r["id"] for r in m["replaced"]}
    assert replaced.isdisjoint(IDS)


def test_tier_mix() -> None:
    m = _manifest()
    counts = {tier: sum(e["tier"] == tier for e in m["task"]) for tier in LIMITS}
    for tier in LIMITS:
        assert 3 <= counts[tier] <= 0.4 * len(NEW)
    by_id = {t.id: t for t in NEW}
    for e in m["task"]:
        assert by_id[e["id"]].difficulty == e["tier"]


@pytest.mark.parametrize("tid", IDS)
def test_changed_files_match_tier(tid: str) -> None:
    task = _task(tid)
    e = _entry(tid)
    n = len(_changed(task))
    assert e["changed_files"] == n
    crit = e["criterion"]
    if e["tier"] == "easy":
        assert n == 1 and crit == "files"
    elif e["tier"] == "medium":
        assert (crit == "files" and 2 <= n <= 3) or (crit == "interacting" and 1 <= n <= 3)
    else:
        assert n >= 3 and crit in ("cross_module", "edge_cases")


@pytest.mark.parametrize("tid", IDS)
def test_limits(tid: str) -> None:
    task = _task(tid)
    e = _entry(tid)
    assert (task.wall_s, task.max_iterations) == LIMITS[e["tier"]]
    assert abs(task.cost_usd - _cost(e["cal_input_tokens"], e["cal_output_tokens"])) < 1e-9
    assert task.grader_visibility == "hidden"
    assert task.grader_timeout_s == 60
    assert e["cal_run_id"] and e["cal_input_tokens"] > 0


@pytest.mark.parametrize("tid", IDS)
def test_checks_and_visible_suite(tid: str, tmp_path: Path, no_network: list[str]) -> None:
    task = _task(tid)
    ws = e2e.prepare_workspace(task, tmp_path / "ref")
    e2e.apply_reference(task, ws)
    r = e2e.run_grader(task, ws, tmp_path / "h")
    assert r.full_pass
    assert len(r.checks) >= 4
    if (task.template_dir / "tests").is_dir():
        tpl = e2e.prepare_workspace(task, tmp_path / "tpl")
        assert _pytest(tpl) != 0
        assert _pytest(ws) == 0
    assert no_network == []


@pytest.mark.parametrize("tid", IDS)
def test_no_leak(tid: str) -> None:
    task = _task(tid)
    for path in task.template_dir.rglob("*"):
        rel = path.relative_to(task.template_dir)
        assert not {"grader", "reference", ".cora_grader"} & set(rel.parts)
        assert path.name != "grade.py"
    texts = [task.requirements_path.read_text(encoding="utf-8")]
    for path in sorted(task.template_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    for text in texts:
        assert TIER_WORDS.search(text) is None
        for leak in LEAK:
            assert leak not in text
    assert TIER_WORDS.search(e2e.agent_prompt(task)) is None
