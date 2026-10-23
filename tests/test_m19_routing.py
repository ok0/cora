from __future__ import annotations

import asyncio
import difflib
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import cora.bench.live
from cora.cli.common import load_resolved
from cora.cli.main import app
from cora.core.providers.openrouter import OpenRouterProvider
from cora.core.types import CompletionRequest, Message

REPO = Path(__file__).resolve().parents[1]
ARMS = REPO / "tests" / "fixtures" / "m19" / "arms"
PREREG = REPO / "tests" / "fixtures" / "m19" / "preregistration.md"
NEW_LINE = 'provider_ignore = ["amazon-bedrock"]   # M19 정정 14: Amazon Bedrock rejects the stop field for qwen3-coder-30b (HTTP 400 stopSequences); unset = OpenRouter default'  # noqa: E501
ANCHOR = "# require_parameters = true "
PAIRS = {
    "deadline-nobedrock-cascade-strong.toml": ARMS / "deadline-cascade-strong.toml",
    "deadline-nobedrock-deleg-nudge.toml": ARMS / "deadline-deleg-nudge.toml",
}
REQ = CompletionRequest("m/x", [Message("user", "hi")], stop=["\nObservation:"])
OK_JSON = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
SSE_OK = b'data: {"choices":[{"delta":{"content":"x"}}]}\n\ndata: [DONE]\n\n'


def _prereg_diff_block(name: str) -> list[str]:
    lines = PREREG.read_text(encoding="utf-8").splitlines()
    heading = f"#### 설정 {name}"
    start = lines.index(heading)
    open_idx = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("```diff"))
    close_idx = next(i for i in range(open_idx + 1, len(lines)) if lines[i] == "```")
    return lines[open_idx + 1 : close_idx][2:]


@pytest.mark.parametrize("name", list(PAIRS))
def test_file_is_base_plus_one_line(name: str) -> None:
    base = PAIRS[name].read_text(encoding="utf-8")
    assert base.count(ANCHOR) == 1
    lines = base.splitlines()
    idx = next(i for i, ln in enumerate(lines) if ln.startswith(ANCHOR))
    lines.insert(idx + 1, NEW_LINE)
    expected = "\n".join(lines) + "\n"
    actual = (ARMS / name).read_text(encoding="utf-8")
    assert actual == expected


@pytest.mark.parametrize("name", list(PAIRS))
def test_diff_registered(name: str) -> None:
    base = PAIRS[name].read_text(encoding="utf-8").splitlines()
    variant = (ARMS / name).read_text(encoding="utf-8").splitlines()
    diff = list(difflib.unified_diff(base, variant, n=3, lineterm=""))[2:]
    assert diff == _prereg_diff_block(name.removesuffix(".toml"))


@pytest.mark.parametrize("name", list(PAIRS))
def test_values_compose(name: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")
    _, cfg = load_resolved(ARMS / name, tmp_path)
    assert cfg.providers["openrouter"]["provider_ignore"] == ["amazon-bedrock"]
    assert cfg.providers["openrouter"]["request_deadline_s"] == 300
    assert cfg.providers["openrouter"]["timeout_s"] == 300
    assert cfg.agent.call_timeout_s == 960
    run = cora.bench.live._run_config(cfg, "qwen/qwen3-coder-30b-a3b-instruct", "react", 30, 0.30)
    assert OpenRouterProvider(run.providers["openrouter"]).provider_ignore == ("amazon-bedrock",)


def test_base_has_no_provider_ignore(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")
    _, cfg = load_resolved(ARMS / "deadline-cascade-strong.toml", tmp_path)
    assert "provider_ignore" not in cfg.providers["openrouter"]


def test_body_excludes_bedrock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy")
    _, cfg = load_resolved(ARMS / "deadline-nobedrock-cascade-strong.toml", tmp_path)
    run = cora.bench.live._run_config(cfg, "qwen/qwen3-coder-30b-a3b-instruct", "react", 30, 0.30)
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=OK_JSON)

    p = OpenRouterProvider(run.providers["openrouter"], transport=httpx.MockTransport(handler))
    asyncio.run(p.complete(REQ))
    assert bodies[0]["provider"] == {"ignore": ["amazon-bedrock"]}
    assert bodies[0]["stop"]


def _total_line(output: str) -> str:
    lines = [ln for ln in output.splitlines() if ln.startswith("total_max_usd:")]
    assert len(lines) == 1, output
    return lines[0]


PLAN_CASES = [
    (
        "deadline-nobedrock-cascade-strong.toml",
        "deadline-cascade-strong.toml",
        [
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--ab",
            "auto-routed",
            "--tasks",
            "e2e_h06",
            "--repeats",
            "3",
            "--max-cost",
            "0.27",
        ],
        "0.270000",
    ),
    (
        "deadline-nobedrock-cascade-strong.toml",
        "deadline-cascade-strong.toml",
        [
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--ab",
            "auto-routed",
            "--tasks",
            "e2e_hx2",
            "--repeats",
            "3",
            "--max-cost",
            "0.24",
        ],
        "0.240000",
    ),
    (
        "deadline-nobedrock-cascade-strong.toml",
        "deadline-cascade-strong.toml",
        [
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--ab",
            "auto-routed",
            "--tasks",
            "e2e_h04",
            "--repeats",
            "1",
            "--max-cost",
            "0.10",
        ],
        "0.100000",
    ),
    (
        "deadline-nobedrock-cascade-strong.toml",
        "deadline-cascade-strong.toml",
        [
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--ab",
            "auto-routed",
            "--tasks",
            "e2e_h05",
            "--repeats",
            "1",
            "--max-cost",
            "0.05",
        ],
        "0.050000",
    ),
    (
        "deadline-nobedrock-deleg-nudge.toml",
        "deadline-deleg-nudge.toml",
        [
            "--suite",
            "e2e",
            "--ab",
            "deleg-on-par-on",
            "--tasks",
            "e2e_hx1,e2e_hx2",
            "--repeats",
            "3",
            "--max-cost",
            "0.39",
        ],
        "0.390000",
    ),
    (
        "deadline-nobedrock-cascade-strong.toml",
        "deadline-cascade-strong.toml",
        [
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--ab",
            "auto-routed",
            "--tasks",
            "e2e_h06",
            "--repeats",
            "1",
            "--max-cost",
            "0.09",
        ],
        "0.090000",
    ),
]


@pytest.mark.parametrize(("name", "base", "args", "value"), PLAN_CASES)
def test_plan_total_unchanged(
    name: str, base: str, args: list[str], value: str, monkeypatch
) -> None:
    monkeypatch.chdir(REPO)
    env = {"OPENROUTER_API_KEY": "test-dummy"}
    variant = CliRunner().invoke(app, ["bench", "plan", "-c", str(ARMS / name), *args], env=env)
    base_run = CliRunner().invoke(app, ["bench", "plan", "-c", str(ARMS / base), *args], env=env)
    assert variant.exit_code == 0, variant.output
    assert base_run.exit_code == 0, base_run.output
    assert _total_line(variant.output) == _total_line(base_run.output)
    assert value in _total_line(variant.output)


def _task_cap(output: str, task: str) -> str:
    lines = [ln for ln in output.splitlines() if ln.startswith("|")]
    header = next(ln for ln in lines if "task_cap_usd" in ln)
    cols = [c.strip() for c in header.strip().strip("|").split("|")]
    idx = cols.index("task_cap_usd")
    row = next(ln for ln in lines if task in ln and ln is not header)
    return [c.strip() for c in row.strip().strip("|").split("|")][idx]


@pytest.mark.parametrize(("max_cost", "cap"), [("0.10", "0.100000"), ("0.08", "0.080000")])
def test_rerun_cap_rule_keeps_task_cap(max_cost: str, cap: str, monkeypatch) -> None:
    monkeypatch.chdir(REPO)
    env = {"OPENROUTER_API_KEY": "test-dummy"}
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "plan",
            "-c",
            str(ARMS / "deadline-nobedrock-cascade-strong.toml"),
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--ab",
            "auto-routed",
            "--tasks",
            "e2e_h04",
            "--repeats",
            "1",
            "--max-cost",
            max_cost,
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    assert _task_cap(result.output, "e2e_h04") == cap


@pytest.mark.parametrize(("repeats", "max_cost"), [("3", "0.27"), ("1", "0.09")])
def test_rr10_ceiling_equals_original_task_cap(repeats: str, max_cost: str, monkeypatch) -> None:
    monkeypatch.chdir(REPO)
    env = {"OPENROUTER_API_KEY": "test-dummy"}
    result = CliRunner().invoke(
        app,
        [
            "bench",
            "plan",
            "-c",
            str(ARMS / "deadline-nobedrock-cascade-strong.toml"),
            "--suite",
            "e2e",
            "--models",
            "qwen/qwen3-coder-30b-a3b-instruct",
            "--protocols",
            "react",
            "--ab",
            "auto-routed",
            "--tasks",
            "e2e_h06",
            "--repeats",
            repeats,
            "--max-cost",
            max_cost,
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    assert _task_cap(result.output, "e2e_h06") == "0.090000"
