from __future__ import annotations

import json
from pathlib import Path

import pytest

import m15_baseline as B
from cora.bench import e2e
from cora.bench.compare import known_task_ids, load_compare_baseline
from cora.bench.live_tasks import MULTI_TASKS

pytestmark = pytest.mark.usefixtures("no_network")


def _multi(task_id: str):
    return next(t for t in MULTI_TASKS if t.id == task_id)


def test_prepare_multi(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    ws = B.prepare("query_client_timeout", dest)
    task = _multi("query_client_timeout")
    assert (ws / "svc" / "client.py").exists()
    assert (dest / "prompt.txt").read_text(encoding="utf-8") == task.prompt
    for name in task.check_files:
        assert not (ws / name).exists()


def test_prepare_e2e_hides_grader(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    ws = B.prepare("e2e_text_stats", dest)
    task = e2e.select_e2e_tasks(["e2e_text_stats"])[0]
    assert (ws / "REQUIREMENTS.md").exists()
    assert not (ws / ".cora_grader").exists()
    assert (dest / "prompt.txt").read_text(encoding="utf-8") == e2e.agent_prompt(task)


@pytest.mark.slow
def test_grade_e2e_reference_and_template(tmp_path: Path) -> None:
    task = e2e.select_e2e_tasks(["e2e_text_stats"])[0]
    ws = B.prepare("e2e_text_stats", tmp_path / "d")
    scratch = tmp_path / "grade"
    assert B.grade("e2e_text_stats", ws, None, scratch)["solved"] is False
    e2e.apply_reference(task, ws)
    assert B.grade("e2e_text_stats", ws, None, tmp_path / "grade2")["solved"] is True


def test_grade_multi_wrong_answer(tmp_path: Path) -> None:
    ws = B.prepare("query_client_timeout", tmp_path / "d")
    assert B.grade("query_client_timeout", ws, "no idea", tmp_path / "grade")["solved"] is False


def test_recompute_cost() -> None:
    usage = {
        "claude-sonnet-x": {
            "inputTokens": 1_000_000,
            "outputTokens": 100_000,
            "cacheReadInputTokens": 0,
            "cacheCreationInputTokens": 0,
        }
    }
    assert B.recompute_cost(usage) == (3.0, [])
    cost, notes = B.recompute_cost({"mystery-model": {"inputTokens": 1}})
    assert cost is None
    assert notes == ["no price for mystery-model"]


def test_run_record_whitelist() -> None:
    cc = {
        "result": "the answer sk-test",
        "secret_like": "sk-test",
        "total_cost_usd": 0.01,
        "modelUsage": {
            "claude-sonnet-x": {"inputTokens": 10, "outputTokens": 5, "contextWindow": 1}
        },
        "num_turns": 2,
        "subtype": "success",
        "is_error": False,
        "session_id": "s",
    }
    graded = {"solved": True, "score": 1.0, "detail": ""}
    rec = B.run_record("query_client_timeout", 1, cc, graded, 3.5, dry_run=False)
    dumped = json.dumps(rec)
    assert "result" not in rec
    assert "sk-test" not in dumped
    assert rec["json_keys"] == sorted(cc)
    assert rec["model_usage"]["claude-sonnet-x"] == {"inputTokens": 10, "outputTokens": 5}


def _hard_rec(task: str, solved: bool) -> dict:
    return {
        "task": task,
        "solved": solved,
        "dry_run": False,
        "cost_recomputed_usd": 0.1,
        "total_cost_usd": 0.12,
        "wall_s": 60.0,
    }


def test_toml_hard_set_tasks(tmp_path: Path) -> None:
    records = [
        _hard_rec("e2e_h01", True),
        _hard_rec("e2e_h01", True),
        _hard_rec("e2e_h01", False),
        _hard_rec("e2e_hx2", False),
        _hard_rec("e2e_hx2", False),
        _hard_rec("e2e_hx2", False),
    ]
    path = tmp_path / "hard.toml"
    path.write_text(
        B.to_baseline_toml(
            records,
            model="claude-sonnet-x",
            date="2026-10-18",
            source="unit test",
            dry_run=False,
        ),
        encoding="utf-8",
    )
    text = path.read_text(encoding="utf-8")
    assert "[tasks.e2e_h01]" in text
    assert "[tasks.e2e_hx2]" in text
    base = load_compare_baseline(path, known_task_ids())
    assert set(base.tasks) == {"e2e_h01", "e2e_hx2"}
    assert base.tasks["e2e_h01"].solve_rate == pytest.approx(0.6666666666666666)
    assert base.tasks["e2e_h01"].n == 3
    assert base.tasks["e2e_hx2"].solve_rate == 0.0


def test_audit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    leak = tmp_path / "leak.jsonl"
    leak.write_text(
        json.dumps({"tool": "Read", "path": f"/x/{B.ROOT_NAME}/.docs/bench-results.md"}) + "\n",
        encoding="utf-8",
    )
    assert B.main(["audit", str(leak)]) == 1
    assert "line 1" in capsys.readouterr().out

    clean = tmp_path / "clean.jsonl"
    clean.write_text(
        '{"cwd": "/tmp/cora-cc-m19/e2e_h01-r1/ws"}\n{"cwd": "/tmp/cora-cc-m19/e2e_h01-r1/ws"}\n',
        encoding="utf-8",
    )
    assert B.main(["audit", str(clean)]) == 0
    assert "clean" in capsys.readouterr().out

    assert B.main(["audit", str(tmp_path / "missing.jsonl")]) == 2


def test_toml_accepted_by_compare_loader(tmp_path: Path) -> None:
    cc = {
        "total_cost_usd": 0.01,
        "modelUsage": {"claude-sonnet-x": {"inputTokens": 1000, "outputTokens": 100}},
    }
    records = [
        B.run_record(
            "query_client_timeout", i, cc, {"solved": solved, "score": 0.0}, 2.0, dry_run=False
        )
        for i, solved in enumerate([True, True, False])
    ]
    records.append(
        B.run_record(
            "query_client_timeout",
            9,
            cc,
            {"solved": True, "score": 1.0},
            2.0,
            dry_run=True,
        )
    )
    counted = tmp_path / "counted.toml"
    counted.write_text(
        B.to_baseline_toml(
            records,
            model="claude-sonnet-x",
            date="2026-10-15",
            source="unit test",
            dry_run=False,
        ),
        encoding="utf-8",
    )
    base = load_compare_baseline(counted, known_task_ids())
    task = base.tasks["query_client_timeout"]
    assert task.solved_k == 2
    assert task.n == 3
    assert base.meta.synthetic is False

    dry = tmp_path / "dry.toml"
    dry.write_text(
        B.to_baseline_toml(
            records,
            model="claude-sonnet-x",
            date="2026-10-15",
            source="unit test",
            dry_run=True,
        ),
        encoding="utf-8",
    )
    dry_base = load_compare_baseline(dry, known_task_ids())
    assert dry_base.meta.source.startswith("DRY-RUN")
    assert dry_base.tasks["query_client_timeout"].note == "dry-run, not counted"
