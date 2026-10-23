from __future__ import annotations

import asyncio

import pytest

import cora.core.deciders.llm as llm_mod
from conftest import with_decider
from cora.bench.e2e import agent_prompt, select_e2e_tasks
from cora.core.errors import ConfigError, ProviderError
from cora.core.router import HeuristicRouter
from cora.core.types import CompletionRequest, CompletionResponse
from m19c_probe import (
    LABELS,
    TASK_IDS,
    GeminiOnlyPool,
    build_input,
    main,
    outcome_text,
    probe_config,
    render,
    run_probe,
    summarize,
    template_file_count,
)

pytestmark = pytest.mark.usefixtures("no_network")

STRONG = '{"answer":"strong","confidence":0.9}'
CHEAP = '{"answer":"cheap","confidence":0.9}'
TASKS = select_e2e_tasks(TASK_IDS)
TASK_BY_ID = {t.id: t for t in TASKS}


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
    return with_decider(probe_config(mock_config, "mock/cheap"), max_cost_per_decision=1.0)


def make(replies: list) -> tuple[FakeProvider, GeminiOnlyPool]:
    fake = FakeProvider(replies)
    return fake, GeminiOnlyPool(fake, allowed="scripted")


def test_labels_preregistered():
    assert LABELS == {
        "e2e_h01": "strong",
        "e2e_h02": "cheap",
        "e2e_h03": "strong",
        "e2e_h04": "strong",
        "e2e_h05": "cheap",
        "e2e_h06": "cheap",
        "e2e_hx1": "cheap",
        "e2e_hx2": "strong",
    }
    assert set(LABELS) == set(TASK_IDS)
    values = list(LABELS.values())
    assert values.count("strong") == 4
    assert values.count("cheap") == 4


def test_build_input_spec_and_summary():
    t = TASK_BY_ID["e2e_hx2"]
    spec = build_input(t, "spec")
    assert spec.startswith(agent_prompt(t))
    assert t.requirements_path.read_text(encoding="utf-8") in spec
    assert "Repository summary" not in spec
    summary = build_input(t, "spec+summary")
    assert summary.endswith(f"template files = {template_file_count(t)}, required files = 1")
    with pytest.raises(ValueError):
        build_input(t, "unknown")


def test_no_truncation_full_spec_reaches_provider(cfg):
    fake, pool = make([STRONG] * 8)
    asyncio.run(run_probe(cfg, pool, TASKS, ("spec",)))
    assert len(fake.calls) == 8
    for task, req in zip(TASKS, fake.calls, strict=True):
        tail = task.requirements_path.read_text(encoding="utf-8")[-200:]
        assert tail in req.messages[-1].content
    assert llm_mod.MAX_INPUT_CHARS == 2000


def test_input_over_cap_raises(cfg):
    _, pool = make([])
    with pytest.raises(ValueError):
        asyncio.run(run_probe(cfg, pool, TASKS, ("spec",), cap=500))
    assert llm_mod.MAX_INPUT_CHARS == 2000


def test_all_strong_is_4_of_8(cfg):
    _, pool = make([STRONG] * 8)
    rows = asyncio.run(run_probe(cfg, pool, TASKS, ("spec",)))
    s = summarize(rows, "spec")
    assert s["line"] == "4/8 hits"
    assert s["misses"] == ["e2e_h02", "e2e_h05", "e2e_h06", "e2e_hx1"]
    assert s["blocked"] == []
    assert s["outcome"].startswith("near chance")


def test_label_matching_is_8_of_8(cfg):
    replies = [CHEAP if LABELS[t.id] == "cheap" else STRONG for t in TASKS]
    _, pool = make(replies)
    rows = asyncio.run(run_probe(cfg, pool, TASKS, ("spec",)))
    s = summarize(rows, "spec")
    assert s["line"] == "8/8 hits"
    assert s["outcome"] == (
        "not adopted before paid validation on new tasks (separately approved, about $1)"
    )


def test_failures_are_blocked_not_hits(cfg):
    replies = ["not json", ProviderError("boom")] + [STRONG] * 6
    _, pool = make(replies)
    rows = asyncio.run(run_probe(cfg, pool, TASKS, ("spec",)))
    h01, h02 = rows[0], rows[1]
    assert h01.task_id == "e2e_h01"
    assert h01.status == "blocked"
    assert h01.reason == "bad_json"
    assert h01.hit is None
    assert h01.pick is None
    assert h02.task_id == "e2e_h02"
    assert h02.reason == "provider_error"
    assert h02.raw.startswith("<error ProviderError")
    s = summarize(rows, "spec")
    assert s["blocked"] == ["e2e_h01", "e2e_h02"]
    assert s["hits"] == 3
    assert s["line"] == "3/8 hits"
    assert s["outcome"].endswith("(incomplete: blocked e2e_h01, e2e_h02)")


def test_outcome_bands():
    for k in (0, 2):
        assert outcome_text(k, []).startswith("below chance")
    for k in (3, 5):
        assert outcome_text(k, []).startswith("near chance")
    assert outcome_text(6, []).startswith("not adopted")


def test_pool_rejects_non_gemini():
    pool = GeminiOnlyPool(FakeProvider([]))
    with pytest.raises(ConfigError):
        pool.get("openrouter")
    assert hasattr(pool.get("gemini"), "complete")


def test_render_contains_required_fields(cfg):
    _, pool = make([STRONG] * 8)
    rows = asyncio.run(run_probe(cfg, pool, TASKS, ("spec",)))
    meta = {
        "date": "2026-10-22",
        "model": "gemini-3.5-flash-lite",
        "provider": "gemini",
        "input_cap": "6000",
        "timeout_s": "60.0",
    }
    text = render(rows, meta)
    router = HeuristicRouter(cfg)
    for t in TASKS:
        line = next(
            ln for ln in text.splitlines() if ln.startswith(f"| {t.id} |")
        )
        assert f"| {LABELS[t.id]} |" in line
        heur = router.score(agent_prompt(t))[0]
        assert f"| {heur} |" in line
    for r in rows:
        assert r.heur_wrapper == router.score(agent_prompt(TASK_BY_ID[r.task_id]))[0]
    assert "model: gemini-3.5-flash-lite" in text
    assert "Summary: 4/8 hits" in text
    assert "## Raw answers" in text
    assert "## Pre-registered labels" in text
    assert "## Protocol" in text


def test_main_refuses_non_free_model(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    out = tmp_path / "o.md"
    assert main(["--out", str(out)]) == 2
    assert not out.exists()
    assert main(["--model", "google/gemini-2.5-flash-lite", "--out", str(out)]) == 2
    assert not out.exists()
