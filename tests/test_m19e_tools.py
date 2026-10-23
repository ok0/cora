from __future__ import annotations

import dataclasses
import hashlib

import pytest

import m19e_data as D
import m19e_judge as J
from conftest import with_decider
from cora.core.errors import ProviderError
from cora.core.prerouter import RepoProbe, RouteInputs
from cora.core.types import CompletionRequest, CompletionResponse
from m19c_probe import GeminiOnlyPool, probe_config

pytestmark = pytest.mark.usefixtures("no_network")

ROW = {"task": "t", "judge_input": "TASK TEXT", "judge_input_sha": "abc"}


class FakeProvider:
    def __init__(self, replies: list) -> None:
        self.replies = list(replies)
        self.calls: list[CompletionRequest] = []

    async def complete(self, req: CompletionRequest) -> CompletionResponse:
        self.calls.append(req)
        reply = self.replies.pop(0) if self.replies else ""
        if isinstance(reply, BaseException):
            raise reply
        return CompletionResponse(reply, 100, 10, req.model)


@pytest.fixture
def cfg(mock_config):
    free = dataclasses.replace(
        mock_config,
        models=tuple(
            dataclasses.replace(
                m, input_usd_per_mtok=0.0, output_usd_per_mtok=0.0, free_tier=True
            )
            for m in mock_config.models
        ),
    )
    return with_decider(probe_config(free, "mock/cheap"), max_cost_per_decision=1.0)


def make(replies: list) -> tuple[FakeProvider, GeminiOnlyPool]:
    fake = FakeProvider(replies)
    return fake, GeminiOnlyPool(fake, allowed="scripted")


def test_prefix_markers():
    events = [
        {"type": "attempt_start"},
        {"type": "llm_call", "purpose": "react", "cost_usd": 0.001},
        {"type": "tool_call", "tool": "edit_file", "ok": "False",
         "output_head": "edit_file failed: 'old' text not found in x"},
        {"type": "parse_error"},
        {"type": "llm_call", "purpose": "react", "cost_usd": 0.002},
        {"type": "tool_call", "tool": "read_file", "ok": False},
        {"type": "llm_call", "purpose": "react", "cost_usd": 0.003},
        {"type": "tool_call", "tool": "write_file", "ok": "False"},
    ]
    m = D.prefix_markers(events)
    assert m["markers"] == 3
    assert m["parse_error"] == 1
    assert m["tool_error"] == 2
    assert m["edit_old_not_found"] == 1
    assert m["read_missing"] == 1
    assert m["prefix_cost_usd"] == pytest.approx(0.003)


def test_match_sessions():
    sessions = [
        {"id": "20261017-2", "task": "prompt T1", "attempt": 0},
        {"id": "20261017-1", "task": "prompt T1", "attempt": 0},
        {"id": "20261017-3", "task": "prompt T1", "attempt": 1},
        {"id": "20261017-5", "task": "prompt T2", "attempt": 0},
        {"id": "20261017-4", "task": "prompt T2", "attempt": 0},
    ]
    results = [{"task": "T1"}, {"task": "T1"}, {"task": "T2"}, {"task": "T2"}, {"task": "T3"}]
    got = D.match_sessions(results, sessions, lambda t: f"prompt {t}")
    assert got == [
        "20261017-1",
        "20261017-2",
        "20261017-4",
        "20261017-5",
        None,
    ]


def test_render_judge_input():
    inp = RouteInputs(
        prompt="Do X",
        spec_text="=== A.md ===\nhi",
        repo=RepoProbe(
            n_files=3,
            n_py_files=2,
            total_lines=10,
            spec_chars=14,
            named_paths=("A.md", "b.py"),
            named_missing=1,
            scope_files=2,
        ),
    )
    expected = (
        "TASK PROMPT:\nDo X\n\n"
        "SPEC FILES (named in the prompt, capped at 6000 chars):\n=== A.md ===\nhi\n\n"
        "REPOSITORY PROBE:\nfiles: 3; python files: 2; total lines: 10\n"
        "paths named in the prompt: A.md, b.py; missing: 1\n"
        "files matching spec identifiers: 2"
    )
    assert D.render_judge_input(inp) == expected


def test_prompt_hash():
    assert J.prompt_hash(J.S1A_PROMPT) == hashlib.sha256(J.S1A_PROMPT.read_bytes()).hexdigest()[:16]


def test_parse_s1a():
    text = 'ok {"c1":1,"c2":0,"c3":2,"c4":1,"c5":3,"c6":0,"c7":1,"c8":2,"total":11}'
    parsed = J.parse_s1a(text)
    assert parsed is not None
    assert parsed["total"] == 10
    assert parsed["total_mismatch"] is True
    bad = '{"c1":1,"c2":0,"c3":4,"c4":1,"c5":3,"c6":0,"c7":1,"c8":2,"total":12}'
    assert J.parse_s1a(bad) is None
    assert J.parse_s1a("no json here") is None


def test_s1a_command_isolated():
    cmd = J.s1a_command("prompt", "claude-sonnet-5-5")
    joined = " ".join(cmd)
    assert "--strict-mcp-config" in cmd
    assert "WebFetch" in cmd
    assert "--bare" not in cmd
    assert J.s1a_env({"ANTHROPIC_API_KEY": "x", "GEMINI_API_KEY": "y", "PATH": "p"}) == {
        "PATH": "p"
    }
    d = J.judge_dir("x")
    assert J.ROOT not in d.resolve().parents
    assert d.resolve() != J.ROOT
    assert "--bare" not in joined


def test_s1b_ok_row(cfg):
    _, pool = make(['{"answer":14,"confidence":0.9}'])
    row = J.run_s1b([ROW], cfg, pool, "mock/cheap")[0]
    assert row["status"] == "ok"
    assert row["score"] == 14
    assert '"answer":14' in row["raw"]
    assert row["cost_usd"] == 0.0
    assert row["attempts"] == 1


def test_s1b_blocked_after_one_retry(cfg):
    fake, pool = make([ProviderError("HTTP 503"), ProviderError("HTTP 503")])
    row = J.run_s1b([ROW], cfg, pool, "mock/cheap")[0]
    assert row["status"] == "blocked"
    assert row["attempts"] == 2
    assert row["score"] is None
    assert "<error" in row["raw"]
    assert len(fake.calls) == 2


def test_guard(monkeypatch):
    monkeypatch.setattr(D, "committed_bench_results", lambda: "")
    assert J.main(["s1b"]) == 2
    assert D.main(["inputs"]) == 2
    assert D.main(["runs"]) == 2
