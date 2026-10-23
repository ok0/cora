from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import ScriptedProvider, act, with_agent
from cora.bench.live import Budget, check_task, run_live_bench
from cora.bench.live_tasks import LIVE_TASKS, LiveTask, select_tasks, write_task_files
from cora.bench.report import (
    LiveReport,
    RowSummary,
    baseline_comparison,
    load_live_baseline,
    report_json,
    report_markdown,
)
from cora.cli.main import app
from cora.core.config import CoraConfig, apply_pin, parse_config
from cora.core.errors import ConfigError
from cora.core.providers import register_provider
from cora.core.types import CompletionResponse

REPO_ROOT = Path(__file__).resolve().parents[1]


@register_provider("cost_cent")
class CostCentProvider(ScriptedProvider):
    async def complete(self, req):
        return dataclasses.replace(await super().complete(req), cost_usd=0.01)


def fixed_config() -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "fixed_usage",
                    "tier": "cheap",
                    "input_usd_per_mtok": 1.0,
                    "output_usd_per_mtok": 2.0,
                    "supports_tools": True,
                },
                {
                    "id": "mock/strong",
                    "provider": "fixed_usage",
                    "tier": "strong",
                    "input_usd_per_mtok": 5.0,
                    "output_usd_per_mtok": 10.0,
                    "supports_tools": True,
                },
            ],
            "agent": {"approval": "auto"},
        }
    )


def cent_config() -> CoraConfig:
    return parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "cost_cent",
                    "tier": "cheap",
                    "input_usd_per_mtok": 0.0,
                    "output_usd_per_mtok": 10.0,
                }
            ],
            "agent": {"approval": "auto"},
        }
    )


def T(i: int, rx: str) -> LiveTask:
    return LiveTask(f"t{i}", "explore", "q", {"f.txt": "x"}, answer_regex=rx)


def run(cfg, tmp_path: Path, **kwargs):
    base = dict(max_cost_usd=0.30, max_task_cost_usd=0.10, max_iterations=4)
    base.update(kwargs)
    return asyncio.run(run_live_bench(cfg, state_dir=tmp_path / "state", **base))


def ac3_report(tmp_path: Path, scripted) -> LiveReport:
    scripted.script.extend(
        ["Final Answer: 42", "Final Answer: 0", "Final Answer: 0", "Final Answer: 0"]
    )
    return run(
        fixed_config(),
        tmp_path,
        models=["mock/cheap", "mock/strong"],
        protocols=["react"],
        tasks=[T(1, r"\b42\b"), T(2, r"\b7\b")],
    )


def test_cost_per_solved_and_na(tmp_path, scripted):
    report = ac3_report(tmp_path, scripted)
    assert [r.status for r in report.results] == ["solved", "failed", "failed", "failed"]
    rows = {r["model"]: r for r in json.loads(report_json(report, None))["rows"]}
    cheap_row = rows["mock/cheap"]
    assert cheap_row["solved"] == 1
    assert cheap_row["attempted"] == 2
    assert cheap_row["total_cost_usd"] == pytest.approx(0.0024)
    assert cheap_row["cost_per_solved_usd"] == pytest.approx(0.0024)
    assert rows["mock/strong"]["solved"] == 0
    assert rows["mock/strong"]["cost_per_solved_usd"] is None
    md = report_markdown(report, None)
    strong_line = next(line for line in md.splitlines() if line.startswith("| mock/strong |"))
    assert "| n/a |" in strong_line


def test_total_budget_stops_and_skips(tmp_path, scripted):
    scripted.script.extend(["Final Answer: ok"] * 5)
    report = run(
        with_agent(cent_config(), react_max_tokens=1024),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T(i, "ok") for i in range(1, 6)],
        max_cost_usd=0.035,
        max_task_cost_usd=0.035,
    )
    assert [r.status for r in report.results] == [
        "solved",
        "solved",
        "solved",
        "stopped_budget",
        "skipped_budget",
    ]
    assert len(scripted.calls) == 3
    assert report.budget_exhausted
    assert report.total_cost_usd == pytest.approx(0.03)
    assert report.total_cost_usd <= 0.035


def test_task_budget_stops_only_that_task(tmp_path, scripted):
    scripted.script.extend([act("list_files", {})] * 4)
    report = run(
        with_agent(cent_config(), react_max_tokens=1024),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T(1, "ok"), T(2, "ok")],
        max_cost_usd=0.5,
        max_task_cost_usd=0.015,
    )
    assert [r.status for r in report.results] == ["stopped_budget", "stopped_budget"]
    assert [r.budget_reason for r in report.results] == ["task", "task"]
    assert [r.calls for r in report.results] == [1, 1]
    assert not report.budget_exhausted
    assert len(scripted.calls) == 2


def test_unpriced_model_rejected_before_call(tmp_path, mock_config, scripted):
    cfg = apply_pin(mock_config, "x/unpriced")
    with pytest.raises(ConfigError, match="no known price"):
        run(cfg, tmp_path, models=["x/unpriced"], protocols=["react"], tasks=[T(1, "ok")])
    assert scripted.calls == []
    with pytest.raises(ConfigError, match="not in the model catalog"):
        run(mock_config, tmp_path, models=["nope/x"], protocols=["react"], tasks=[T(1, "ok")])
    with pytest.raises(ConfigError, match="hard per-invocation limit"):
        run(
            mock_config,
            tmp_path,
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[T(1, "ok")],
            max_cost_usd=0.6,
        )


def test_report_json_and_markdown_fields(tmp_path, scripted):
    report = ac3_report(tmp_path, scripted)
    obj = json.loads(report_json(report, None))
    assert set(obj) >= {
        "schema_version",
        "generated_at",
        "cora_version",
        "settings",
        "total_cost_usd",
        "total_calls",
        "provider_cost_calls",
        "budget_exhausted",
        "rows",
        "results",
        "baseline",
        "baseline_note",
    }
    field_names = {f.name for f in dataclasses.fields(RowSummary)}
    assert len(field_names) == 13
    for row in obj["rows"]:
        assert set(row) == field_names
    assert obj["settings"]["protocols"] == ["react"]
    assert obj["settings"]["models"][0]["id"] == "mock/cheap"
    md = report_markdown(report, None)
    assert (
        "| model | protocol | attempted | solved | failed | skipped | solve_rate | "
        "total_cost_usd | cost_per_solved_usd | input_tokens | output_tokens | avg_calls | "
        "avg_latency_s |"
    ) in md.splitlines()


def test_baseline_cases(tmp_path, scripted):
    report = ac3_report(tmp_path, scripted)

    assert "baseline: baseline not provided" in report_markdown(report, None)
    obj = json.loads(report_json(report, None))
    assert obj["baseline"] is None
    assert obj["baseline_note"] == "baseline not provided"

    full = tmp_path / "full.toml"
    full.write_text(
        '[tasks.t1]\ncost_usd = 0.10\nsuccess = true\n\n'
        '[tasks.t2]\ncost_usd = 0.20\nsuccess = true\n',
        encoding="utf-8",
    )
    base = load_live_baseline(full, ["t1", "t2"])
    cmp = baseline_comparison(report, base)
    row = next(r for r in cmp["rows"] if r["model"] == "mock/cheap")
    assert row["baseline_cost_per_solved_usd"] == pytest.approx(0.15)
    assert row["ratio"] == pytest.approx(0.0024 / 0.15)

    partial = tmp_path / "partial.toml"
    partial.write_text(
        '[tasks.t1]\ncost_usd = 0.10\nsuccess = true\n', encoding="utf-8"
    )
    base1 = load_live_baseline(partial, ["t1", "t2"])
    cmp1 = baseline_comparison(report, base1)
    t2_entries = [p for p in cmp1["per_task"] if p["task"] == "t2"]
    assert t2_entries and all(p["baseline_cost_usd"] is None for p in t2_entries)
    md = report_markdown(report, base1)
    assert any(line.startswith("| t2 |") and "n/a" in line for line in md.splitlines())

    bad_cost = tmp_path / "bad_cost.toml"
    bad_cost.write_text('[tasks.t1]\ncost_usd = "x"\nsuccess = true\n', encoding="utf-8")
    bad_success = tmp_path / "bad_success.toml"
    bad_success.write_text('[tasks.t1]\ncost_usd = 0.1\nsuccess = "yes"\n', encoding="utf-8")
    unknown = tmp_path / "unknown.toml"
    unknown.write_text("[tasks.zzz]\ncost_usd = 0.1\nsuccess = true\n", encoding="utf-8")
    broken = tmp_path / "broken.toml"
    broken.write_text("[tasks\n", encoding="utf-8")
    for path, match in [
        (bad_cost, "cost_usd"),
        (bad_success, "success"),
        (unknown, "unknown task id"),
        (broken, "invalid baseline file"),
    ]:
        with pytest.raises(ConfigError, match=match):
            load_live_baseline(path, ["t1", "t2"])


def test_both_protocols_rows(tmp_path, scripted):
    scripted.script.extend(
        [
            "Final Answer: 42",
            CompletionResponse("42", 0, 0, "mock/cheap"),
            "Final Answer: 42",
            CompletionResponse("42", 0, 0, "mock/strong"),
        ]
    )
    report = run(
        fixed_config(),
        tmp_path,
        models=["mock/cheap", "mock/strong"],
        protocols=["react", "native"],
        tasks=[T(1, r"\b42\b")],
    )
    rows = json.loads(report_json(report, None))["rows"]
    assert len(rows) == 4
    assert all(r["solved"] == 1 for r in rows)
    by = {(r["model"], r["protocol"]): r["total_cost_usd"] for r in rows}
    assert by[("mock/cheap", "react")] == pytest.approx(0.0012)
    assert by[("mock/cheap", "native")] == pytest.approx(0.0012)
    assert by[("mock/strong", "react")] == pytest.approx(0.006)
    assert by[("mock/strong", "native")] == pytest.approx(0.006)
    assert scripted.calls[0].tools is None
    assert isinstance(scripted.calls[1].tools, list) and scripted.calls[1].tools


def test_live_tasks_shape():
    assert 10 <= len(LIVE_TASKS) <= 20
    ids = [t.id for t in LIVE_TASKS]
    assert len(set(ids)) == len(ids)
    for t in LIVE_TASKS:
        assert (t.check is None) != (t.answer_regex is None)
    kinds = {t.kind for t in LIVE_TASKS}
    assert {"bugfix", "implement", "refactor", "explore"} <= kinds


REFERENCES: dict[str, dict[str, str]] = {
    "fix_off_by_one": {
        "rng.py": "def inclusive_range(a, b):\n    return list(range(a, b + 1))\n",
    },
    "fix_mutable_default": {
        "counter.py": (
            "def count_words(text, counts=None):\n"
            "    counts = {} if counts is None else counts\n"
            "    for word in text.split():\n"
            "        counts[word] = counts.get(word, 0) + 1\n"
            "    return counts\n"
        ),
    },
    "fix_sort_order": {
        "people.py": (
            "def oldest_first(people):\n"
            "    return sorted(people, key=lambda p: (-p[1], p[0]))\n"
        ),
    },
    "implement_is_palindrome": {
        "text_tools.py": (
            "def is_palindrome(s: str) -> bool:\n"
            "    t = [c.lower() for c in s if c.isalnum()]\n"
            "    return t == t[::-1]\n"
        ),
    },
    "implement_fizzbuzz": {
        "fb.py": (
            "def fizzbuzz(n: int) -> list[str]:\n"
            "    out = []\n"
            "    for i in range(1, n + 1):\n"
            "        s = ('Fizz' if i % 3 == 0 else '') + ('Buzz' if i % 5 == 0 else '')\n"
            "        out.append(s or str(i))\n"
            "    return out\n"
        ),
    },
    "implement_parse_kv": {
        "kv.py": (
            "def parse_kv(text: str) -> dict[str, str]:\n"
            "    out = {}\n"
            "    for line in text.splitlines():\n"
            "        s = line.strip()\n"
            "        if not s or s.startswith('#'):\n"
            "            continue\n"
            "        k, _, v = s.partition('=')\n"
            "        out[k.strip()] = v.strip()\n"
            "    return out\n"
        ),
    },
    "refactor_rename": {
        "shop/cart.py": "def compute_total(prices):\n    return sum(prices)\n",
        "shop/checkout.py": (
            "from shop.cart import compute_total\n\n\n"
            "def checkout(prices):\n"
            "    return round(compute_total(prices) * 1.1, 2)\n"
        ),
    },
    "refactor_extract_constant": {
        "tax.py": (
            "TAX_RATE = 0.08\n\n\n"
            "def with_tax(amount):\n"
            "    return round(amount * (1 + TAX_RATE), 2)\n\n\n"
            "def tax_only(amount):\n"
            "    return round(amount * TAX_RATE, 2)\n"
        ),
    },
}


@pytest.mark.slow
def test_live_task_checks_deterministic(tmp_path):
    for task in LIVE_TASKS:
        if task.check is None:
            continue
        root = tmp_path / task.id
        write_task_files(root, task.files)
        ok, _ = asyncio.run(check_task(task, root, None, frozenset()))
        assert ok is False, task.id
        write_task_files(root, REFERENCES[task.id])
        ok, detail = asyncio.run(check_task(task, root, None, frozenset()))
        assert ok is True, (task.id, detail)

    answers = {
        "explore_find_port": (["8731"], ["8000"]),
        "explore_count_todos": (["3"], ["13"]),
        "explore_find_raiser": (["parse"], ["load"]),
    }
    by_id = {t.id: t for t in LIVE_TASKS}
    for task_id, (good, bad) in answers.items():
        task = by_id[task_id]
        root = tmp_path / task_id
        for ans in good:
            ok, _ = asyncio.run(check_task(task, root, ans, frozenset()))
            assert ok is True, (task_id, ans)
        for ans in bad:
            ok, _ = asyncio.run(check_task(task, root, ans, frozenset()))
            assert ok is False, (task_id, ans)


def test_select_tasks_order_and_unknown():
    assert select_tasks(None) == LIVE_TASKS
    assert select_tasks([]) == LIVE_TASKS
    picked = select_tasks(["explore_find_port", "fix_off_by_one"])
    assert [t.id for t in picked] == ["explore_find_port", "fix_off_by_one"]
    with pytest.raises(ConfigError, match="unknown bench task id"):
        select_tasks(["nope"])


def test_budget_gate_unit():
    b = Budget(0.05, 0.02)
    b.begin_task()
    assert b.gate(0.0, 0.01) is True
    assert b.gate(0.015, 0.01) is False and b.tripped == "task"
    b.settle(0.04)
    assert b.exhausted is False
    b.begin_task()
    assert b.gate(0.0, 0.02) is False and b.tripped == "total"
    b.settle(0.0)
    assert b.exhausted is True


def test_cli_live_without_key(monkeypatch, tmp_path):
    import httpx

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    async def no_network(self, request, **kw):
        raise AssertionError("network")

    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "--live",
            "-c",
            str(REPO_ROOT / "cora.toml"),
            "-w",
            str(tmp_path),
            "--models",
            "deepseek/deepseek-chat-v3.1",
            "--tasks",
            "explore_find_port",
        ],
    )
    assert result.exit_code == 2
    assert "OPENROUTER_API_KEY is not set" in result.stderr
    assert "sk-or" not in result.output + result.stderr


def test_cli_live_options_require_live(tmp_path, cfg_file):
    result = CliRunner().invoke(
        app, ["bench", "--models", "x", "-c", str(cfg_file)]
    )
    assert result.exit_code == 2
    assert "require --live" in result.stderr


def test_baseline_missing_file_is_config_error(tmp_path):
    missing = tmp_path / "missing-baseline.toml"
    with pytest.raises(ConfigError, match="cannot read baseline file missing-baseline.toml") as exc:
        load_live_baseline(missing, ["t1"])
    assert str(tmp_path) not in str(exc.value)
