from __future__ import annotations

import json
import tomllib
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pytest

import m21_ab
from cora.bench.stats import wilson_interval
from cora.core.config import load_config

ROOT = m21_ab.ROOT
MANIFEST = ROOT / "tests" / "fixtures" / "m19e2" / "manifest.toml"
TASKS6 = [f"t{i}" for i in range(6)]
SECTIONS = {
    "L": ("memory", "ledger"),
    "S": ("memory", "summarize"),
    "M": ("context", "repo_map"),
    "D": ("context", "dedupe_reads"),
    "C": ("cache", "compress_observations"),
}


def _cora_lines() -> list[str]:
    return (ROOT / "cora.toml").read_text(encoding="utf-8").splitlines(keepends=True)


def _switched(lines: list[str], arm: str) -> list[str]:
    out = list(lines)
    if arm == "OFF":
        return out
    old, new = m21_ab.SWITCH_LINES[arm]
    idx = next(i for i, line in enumerate(out) if line.startswith(old))
    out[idx] = out[idx].replace(old, new, 1)
    return out


def _rec(solved: bool, in_t: int = 1000, it: int = 10, ev: int = 0, comp: int = 0) -> dict:
    return {
        "solved": solved,
        "input_tokens": in_t,
        "iterations": it,
        "evictions": ev,
        "compressed": comp,
        "cost_eq_usd": 0.001,
    }


def _arm(spec: dict[str, list[bool]], in_t: int = 1000, it: int = 10) -> dict[str, list[dict]]:
    return {t: [_rec(s, in_t, it) for s in solved] for t, solved in spec.items()}


def _flat(arm: dict[str, list[dict]]) -> list[dict]:
    return [r for t in arm for r in arm[t]]


def test_arm_text_only_switch_lines():
    base = m21_ab.arm_text("OFF").splitlines(keepends=True)[1:]
    cora = _cora_lines()
    assert Counter(base) == Counter(cora)
    for a in m21_ab.SINGLE_ARMS:
        lines = m21_ab.arm_text(a).splitlines(keepends=True)[1:]
        diff = [(x, y) for x, y in zip(base, lines, strict=True) if x != y]
        if a == "OFF":
            assert diff == []
        else:
            old, new = m21_ab.SWITCH_LINES[a]
            assert len(diff) == 1
            assert diff[0][0].startswith(old) and diff[0][1].startswith(new)
        assert Counter(lines) == Counter(_switched(cora, a))


def test_arm_configs_load_and_free_first(tmp_path):
    m21_ab.write_arms(tmp_path)
    cfgs = {}
    for a in m21_ab.SINGLE_ARMS:
        path = tmp_path / "arms" / f"{a}.toml"
        m21_ab.check_arm(path, {a} - {"OFF"})
        cfg = load_config(path)
        cheap = next(m for m in cfg.models if m.tier == "cheap")
        assert cheap.id == m21_ab.MODEL
        assert cheap.free_tier is True
        cfgs[a] = asdict(cfg)
    off = cfgs["OFF"]
    for a, cfg in cfgs.items():
        rest = {k: v for k, v in cfg.items() if k not in ("memory", "context", "cache", "models")}
        base = {k: v for k, v in off.items() if k not in ("memory", "context", "cache", "models")}
        assert rest == base
        for section in ("memory", "context", "cache"):
            changed = {k for k in off[section] if off[section][k] != cfg[section][k]}
            expected = {SECTIONS[a][1]} if a in SECTIONS and SECTIONS[a][0] == section else set()
            assert changed == expected


def test_best_and_budget():
    off = m21_ab.arm_text("OFF").splitlines(keepends=True)[1:]
    best = m21_ab.arm_text("BEST", best=("L", "C")).splitlines(keepends=True)[1:]
    diff = [(x, y) for x, y in zip(off, best, strict=True) if x != y]
    assert len(diff) == 2
    assert {y.split(" =")[0] for _, y in diff} == {"ledger", "compress_observations"}
    assert "ledger = true" in "".join(best)
    assert "compress_observations = true" in "".join(best)
    assert 'summarize = "off"' in "".join(best)
    assert "repo_map = false" in "".join(best)
    with pytest.raises(SystemExit):
        m21_ab.arm_text("BEST", best=("L",))
    budget = m21_ab.arm_text("L", budget=6000).splitlines(keepends=True)[1:]
    changed = [(x, y) for x, y in zip(off, budget, strict=True) if x != y]
    assert len(changed) == 2
    assert "context_budget_tokens = 6000" in "".join(budget)
    assert "context_budget_tokens = 12000" not in "".join(budget)
    with pytest.raises(SystemExit):
        m21_ab.arm_text("M", budget=6000)


def test_child_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-12345678")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-key-12345678")
    env = m21_ab.child_env()
    assert "OPENROUTER_API_KEY" not in env
    assert env["GEMINI_API_KEY"] == "gm-key-12345678"
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(SystemExit):
        m21_ab.child_env()


def test_bench_command_exact():
    assert m21_ab.bench_command(Path("x.toml"), "e2e_n03", 2, Path("o")) == [
        "uv",
        "run",
        "cora",
        "bench",
        "--live",
        "--suite",
        "e2e",
        "--tasks",
        "e2e_n03",
        "--models",
        "gemini-3.5-flash-lite",
        "--protocols",
        "react",
        "--max-iterations",
        "30",
        "--max-cost",
        "0.30",
        "--repeats",
        "1",
        "--seed",
        "2",
        "--config",
        "x.toml",
        "--out",
        "o",
    ]


def test_classify():
    blocked = {
        "end_reason": "error",
        "detail": "ProviderError: gemini HTTP 503 UNAVAILABLE end_reason=error score=1.00",
        "full_pass": True,
    }
    assert m21_ab.classify(blocked) == "blocked"
    assert (
        m21_ab.classify(
            {"end_reason": "time_limit", "stop_reason": "provider_timeout", "detail": ""}
        )
        == "blocked"
    )
    assert (
        m21_ab.classify({"end_reason": "error", "detail": "KeyError: x end_reason=error"})
        == "defect"
    )
    assert m21_ab.classify({"end_reason": "time_limit", "detail": ""}) == "ok"
    assert m21_ab.classify({"end_reason": "max_iterations", "detail": ""}) == "ok"


def test_run_record_counts(tmp_path):
    run = tmp_path / "counted" / "L" / "e2e_n03" / "r1-retry1"
    (run / "state" / "memory").mkdir(parents=True)
    (run / "state" / "sessions" / "s").mkdir(parents=True)
    report = {
        "wall_s": 50,
        "results": [
            {
                "run_id": "x",
                "status": "solved",
                "full_pass": True,
                "end_reason": "final_answer",
                "stop_reason": "final_answer",
                "detail": "end_reason=final_answer score=1.00",
                "iterations": 7,
                "calls": 7,
                "input_tokens": 1000,
                "output_tokens": 100,
                "cost_usd": 0.0,
            }
        ],
    }
    (run / "report.json").write_text(json.dumps(report), encoding="utf-8")
    (run / "state" / "memory" / "s.jsonl").write_text(
        '{"kind": "evicted", "data": {}}\n{"kind": "evicted", "data": {}}\n'
        '{"kind": "other", "data": {}}\n',
        encoding="utf-8",
    )
    events = [
        {"type": "read_dedupe", "superseded": 2, "iteration": 1},
        {"type": "observation_compress", "compressed": 3, "iteration": 2},
        {"type": "repo_map", "files": 1, "chars": 100, "tokens": 25},
        {"type": "llm_call", "provider": "gemini", "prompt_tokens_estimate": 900},
    ]
    (run / "state" / "sessions" / "s" / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    rec = m21_ab.run_record(run)
    assert rec["arm"] == "L"
    assert rec["task"] == "e2e_n03"
    assert rec["repeat"] == 1
    assert rec["attempt"] == 1
    assert rec["class"] == "ok"
    assert rec["solved"] is True
    assert rec["evictions"] == 2
    assert rec["read_dedupe"] == 2
    assert rec["compressed"] == 3
    assert rec["repo_map_tokens"] == 25
    assert rec["peak_prompt_tokens"] == 900
    assert rec["cost_eq_usd"] == pytest.approx((1000 * 0.10 + 100 * 0.40) / 1e6)
    assert rec["cost_source"] == "free_tier"
    assert rec["openrouter_calls"] == 0


def _attempt(rep: int, attempt: int, cls: str, solved: bool = False) -> dict:
    return {
        "arm": "L",
        "task": "e2e_n03",
        "repeat": rep,
        "attempt": attempt,
        "class": cls,
        "solved": solved,
    }


def test_counted_uses_retry_and_drops_double_block():
    records = [
        _attempt(0, 0, "blocked"),
        _attempt(0, 1, "ok", True),
        _attempt(1, 0, "blocked"),
        _attempt(1, 1, "blocked"),
        _attempt(2, 0, "ok", False),
    ]
    out, blocked = m21_ab.counted(records)
    kept = out["L"]["e2e_n03"]
    assert [r["repeat"] for r in kept] == [0, 2]
    assert [r["attempt"] for r in kept] == [1, 0]
    assert all(r["class"] == "ok" for r in kept)
    assert len(blocked) == 3


def test_verdict_flip():
    spec = {t: [True, True, False] for t in TASKS6}
    v = m21_ab.verdict("M", _arm(spec), _arm(spec, in_t=800, it=10.5), TASKS6)
    assert v["verdict"].startswith("flip")
    assert v["a"] and v["b"] and v["c"]


def test_verdict_tokens_short():
    spec = {t: [True, True, False] for t in TASKS6}
    v = m21_ab.verdict("M", _arm(spec), _arm(spec, in_t=950), TASKS6)
    assert v["verdict"] == "stays OFF"
    assert v["b"] is False


def test_verdict_no_eviction():
    spec = {t: [True, True, False] for t in TASKS6}
    on = _arm(spec, in_t=800)
    for r in _flat(on)[:4]:
        r["evictions"] = 1
    v = m21_ab.verdict("L", _arm(spec), on, TASKS6)
    assert v["verdict"] == "not evaluable (no eviction)"
    assert v["d_runs"] == 4
    assert v["d"] is False


def test_verdict_not_measured():
    spec = {t: [True, True, False] for t in TASKS6}
    on = _arm({t: spec[t] for t in TASKS6[:5]})
    v = m21_ab.verdict("M", _arm(spec), on, TASKS6)
    assert v["verdict"] == "not measured"
    assert v["common"] == 5


def test_verdict_task_drop():
    off = _arm({t: [True, True, False] for t in TASKS6})
    two = _arm(
        {
            "t0": [False, False, False],
            "t1": [False, False, False],
            "t2": [True, True, True],
            "t3": [True, True, True],
            "t4": [True, True, True],
            "t5": [True, True, True],
        }
    )
    v2 = m21_ab.verdict("M", off, two, TASKS6)
    assert len(v2["drops"]) == 2
    assert v2["a"] is False
    one = _arm(
        {
            "t0": [False, False, False],
            "t1": [True, True, False],
            "t2": [True, True, True],
            "t3": [True, True, True],
            "t4": [True, True, False],
            "t5": [True, True, False],
        }
    )
    v1 = m21_ab.verdict("M", off, one, TASKS6)
    assert len(v1["drops"]) == 1
    assert v1["a"] is True


def test_verdict_iterations():
    spec = {t: [True, True, False] for t in TASKS6}
    v = m21_ab.verdict("M", _arm(spec), _arm(spec, in_t=800, it=11.1), TASKS6)
    assert v["c"] is False


def test_verdict_c_uses_compressed():
    spec = {t: [True, True, False] for t in TASKS6}
    on = _arm(spec, in_t=800)
    for r in _flat(on)[:5]:
        r["compressed"] = 2
    v = m21_ab.verdict("C", _arm(spec), on, TASKS6)
    assert v["d_runs"] == 5
    assert v["d"] is True


def test_best_set():
    flip = {"verdict": m21_ab.FLIP_TEXT}
    assert m21_ab.best_set({"M": flip, "D": flip}) == ("M", "D")
    ratios = {
        "L": {"verdict": "stays OFF", "k_on": 6, "k_off": 5, "n": 10},
        "S": {"verdict": "stays OFF", "k_on": 6, "k_off": 5, "n": 10},
        "M": {"verdict": "stays OFF", "k_on": 5, "k_off": 5, "n": 10},
    }
    assert m21_ab.best_set(ratios) == ("L", "S")
    worse = {"L": {"verdict": "stays OFF", "k_on": 4, "k_off": 5, "n": 10}}
    assert m21_ab.best_set(worse) == ()


def test_wilson_overlap_labels():
    assert m21_ab.overlap_label(wilson_interval(5, 10), wilson_interval(50, 100)) == "full"
    assert m21_ab.overlap_label(wilson_interval(3, 10), wilson_interval(5, 10)) == "partial"
    assert m21_ab.overlap_label(wilson_interval(1, 20), wilson_interval(18, 20)) == "none"


def test_task_order_matches_manifest():
    data = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    ids = [t["id"] for t in data["task"]]
    assert len(ids) == 14
    assert sorted(m21_ab.TASK_ORDER) == sorted(ids)
    assert len(m21_ab.TASK_ORDER) == 14
    assert set(m21_ab.CAL_ITERATIONS) == set(m21_ab.TASK_ORDER)


def test_plan_text_numbers():
    text = m21_ab.plan_text("OFF", m21_ab.TASK_ORDER)
    assert "42" in text
    assert "831" in text


def test_keygrep(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummykey-12345")
    d = tmp_path / "d"
    d.mkdir()
    (d / "hit.txt").write_text("x dummykey-12345 y", encoding="utf-8")
    assert m21_ab.keygrep([d])["matches"] == [str(d / "hit.txt")]
    (d / "hit.txt").write_text("clean", encoding="utf-8")
    assert m21_ab.keygrep([d])["matches"] == []
