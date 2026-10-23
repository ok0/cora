from __future__ import annotations

import tomllib
from pathlib import Path

from cora.bench.e2e import agent_prompt, load_e2e_tasks
from cora.bench.live_tasks import LIVE_TASKS, MULTI_TASKS
from cora.core.config import load_config
from cora.core.router import HeuristicRouter

ROOT = Path(__file__).resolve().parents[1]
SET_PATH = ROOT / "tests" / "data" / "router_prompts.toml"
RULE_LINES = (
    "#   simple   = question or explanation, no code change",
    "#   ordinary = code change confined to at most 2 files or one well-specified function/feature",
    "#   complex  = change across 3 or more files with several dependent steps or design choices",
)


def _entries() -> list[dict]:
    return tomllib.loads(SET_PATH.read_text(encoding="utf-8"))["prompts"]


def test_set_shape() -> None:
    entries = _entries()
    assert len(entries) >= 20
    assert {e["label"] for e in entries} == {"simple", "ordinary", "complex"}
    text = SET_PATH.read_text(encoding="utf-8")
    for line in RULE_LINES:
        assert line in text
    assert {e["source"] for e in entries} <= {"live", "multi", "e2e", "written"}

    by_id = {e["id"]: e["prompt"] for e in entries}
    for task in LIVE_TASKS:
        assert by_id[task.id] == task.prompt
    for task in MULTI_TASKS:
        assert by_id[task.id] == task.prompt
    e2e_ids = {e["id"] for e in entries if e["source"] == "e2e"}
    assert e2e_ids == {
        "e2e_todo_cli", "e2e_text_stats", "e2e_rest_notes", "e2e_md_to_html",
        "e2e_refactor_inventory",
    }
    for task in load_e2e_tasks():
        if task.id in e2e_ids:
            assert by_id[task.id] == agent_prompt(task)


def test_routing_shares(capsys) -> None:
    router = HeuristicRouter(load_config(ROOT / "cora.toml"))
    entries = _entries()
    strong_by_label: dict[str, int] = {"simple": 0, "ordinary": 0, "complex": 0}
    count_by_label: dict[str, int] = {"simple": 0, "ordinary": 0, "complex": 0}
    strong_total = 0
    for e in entries:
        decision = router.route(e["prompt"])
        count_by_label[e["label"]] += 1
        if decision.tier == "strong":
            strong_total += 1
            strong_by_label[e["label"]] += 1
    n = len(entries)
    print(f"strong share overall: {strong_total}/{n} ({100 * strong_total / n:.0f}%)")
    for label in ("simple", "ordinary", "complex"):
        print(f"{label}: strong {strong_by_label[label]}/{count_by_label[label]}")
    assert strong_by_label["ordinary"] == 0


def test_ordinary_single_file_fix_routes_cheap() -> None:
    router = HeuristicRouter(load_config(ROOT / "cora.toml"))
    decision = router.route("Fix the failing test in src/calc.py: add() returns the wrong result")
    assert decision.tier == "cheap"
