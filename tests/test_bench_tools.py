from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from conftest import CFG_TOML, ScriptedProvider, act
from cora.bench.live import run_live_bench
from cora.bench.live_tasks import LiveTask
from cora.bench.report import report_markdown
from cora.cli.main import app
from cora.core.config import BenchSettings, CoraConfig, ToolGroupSettings, parse_config
from cora.core.providers import register_provider
from cora.core.types import CompletionResponse

CORE = ["list_files", "read_file", "search", "edit_file", "write_file", "delete_file", "run_shell"]


@register_provider("cost_tenth")
class CostTenthProvider(ScriptedProvider):
    async def complete(self, req):
        return dataclasses.replace(await super().complete(req), cost_usd=0.1)


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


def T(i: int, rx: str) -> LiveTask:
    return LiveTask(f"t{i}", "explore", "q", {"f.txt": "x"}, answer_regex=rx)


def run(cfg, tmp_path: Path, **kwargs):
    base = dict(max_cost_usd=0.30, max_task_cost_usd=0.10, max_iterations=4)
    base.update(kwargs)
    return asyncio.run(run_live_bench(cfg, state_dir=tmp_path / "state", **base))


def test_bench_default_exposes_only_core(tmp_path, scripted):
    configs = [
        fixed_config(),
        dataclasses.replace(fixed_config(), tool_groups=ToolGroupSettings((), True)),
    ]
    for i, cfg in enumerate(configs):
        scripted.script[:] = ["Final Answer: 8731", CompletionResponse("8731", 0, 0, "mock/cheap")]
        scripted.calls.clear()
        report = run(
            cfg,
            tmp_path / f"run{i}",
            models=["mock/cheap"],
            protocols=["react", "native"],
            tasks=[T(1, r"\b8731\b")],
        )
        react_prompt = scripted.calls[0].messages[0].content
        for name in CORE:
            assert f"- {name}:" in react_prompt
        for name in ("git_", "web_fetch", "todo_write"):
            assert name not in react_prompt
        assert {t["function"]["name"] for t in scripted.calls[1].tools} == set(CORE)
        assert report.settings["tools"] == CORE


def test_cli_bench_live_core_tools_and_metadata(tmp_path, scripted):
    cfg = tmp_path / "cora.toml"
    cfg.write_text(
        CFG_TOML + "\n[tool_groups]\ndisabled = []\nauto_simple = false\n", encoding="utf-8"
    )
    out = tmp_path / "out"
    scripted.script.append("Final Answer: 8731")
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "--live",
            "-c",
            str(cfg),
            "-w",
            str(tmp_path),
            "--models",
            "mock/cheap",
            "--protocols",
            "react",
            "--tasks",
            "explore_find_port",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["settings"]["tools"] == CORE
    assert "web_fetch" not in scripted.calls[0].messages[0].content

    out2 = tmp_path / "out2"
    scripted.script.append("Final Answer: 8731")
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "--live",
            "-c",
            str(cfg),
            "-w",
            str(tmp_path),
            "--models",
            "mock/cheap",
            "--protocols",
            "react",
            "--tasks",
            "explore_find_port",
            "--tool-groups",
            "core,git",
            "--out",
            str(out2),
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads((out2 / "report.json").read_text(encoding="utf-8"))
    assert report["settings"]["tool_groups"] == ["core", "git"]
    assert "git_commit" in report["settings"]["tools"]
    assert "tools: list_files" in (out2 / "report.md").read_text(encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "bench",
            "--live",
            "-c",
            str(cfg),
            "-w",
            str(tmp_path),
            "--models",
            "mock/cheap",
            "--tool-groups",
            "core,nope",
            "--out",
            str(tmp_path / "out3"),
        ],
    )
    assert result.exit_code == 2
    assert "unknown tool group" in result.stderr


def test_bench_rejects_out_of_set_tools(tmp_path, scripted, monkeypatch):
    async def no_network(self, *args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    scripted.script.extend(
        [
            act("web_fetch", {"url": "https://example.com"}),
            act("git_commit", {"message": "m"}),
            "Final Answer: 8731",
        ]
    )
    report = run(
        fixed_config(),
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T(1, r"\b8731\b")],
    )
    assert "tool group 'web', which is disabled" in scripted.calls[1].messages[-1].content
    assert "tool group 'git', which is disabled" in scripted.calls[2].messages[-1].content
    assert report.results[0].status == "solved"


def test_bench_default_invocation_cap_stops(tmp_path, scripted):
    cfg = parse_config(
        {
            "models": [
                {
                    "id": "mock/cheap",
                    "provider": "cost_tenth",
                    "tier": "cheap",
                    "input_usd_per_mtok": 0.0,
                    "output_usd_per_mtok": 100.0,
                }
            ],
            "agent": {"approval": "auto", "react_max_tokens": 1024},
        }
    )
    scripted.script.extend(["Final Answer: ok"] * 5)
    report = run(
        cfg,
        tmp_path,
        models=["mock/cheap"],
        protocols=["react"],
        tasks=[T(i, "ok") for i in range(1, 6)],
        max_cost_usd=BenchSettings().max_cost_usd,
        max_task_cost_usd=0.30,
    )
    assert BenchSettings().max_cost_usd == pytest.approx(0.30)
    assert [r.status for r in report.results] == [
        "solved",
        "solved",
        "stopped_budget",
        "skipped_budget",
        "skipped_budget",
    ]
    assert report.results[2].budget_reason == "total"
    assert report.budget_exhausted
    assert report.total_cost_usd == pytest.approx(0.2)
    assert report.total_cost_usd <= 0.30
    assert "budget_exhausted=yes" in report_markdown(report, None)


def test_bench_help_shows_cost_defaults():
    result = CliRunner().invoke(app, ["bench", "--help"])
    assert "0.30" in result.output
    assert "0.50" in result.output
    assert "--tool-groups" in result.output
