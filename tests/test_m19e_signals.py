from __future__ import annotations

import json

import pytest

import m19e_signals as S
from cora.bench.stats import wilson_interval
from cora.core.prerouter import HistoryRow, knn_score


def test_auroc() -> None:
    assert S.auroc([0.1, 0.4, 0.35, 0.8], [False, False, True, True]) == 0.75
    assert S.auroc([1, 1], [True, False]) == 0.5
    assert S.auroc([1, 2], [True, True]) is None


def test_perm_exact() -> None:
    p, method = S.perm_p([1, 2, 3, 4], [False, False, True, True])
    assert p == pytest.approx(1 / 6)
    assert method == "exact"


def test_perm_mc_deterministic() -> None:
    scores = [1, 2, 3, 4, 5, 6]
    pos = [False, False, False, True, True, True]
    a = S.perm_p(scores, pos, exact_limit=1, mc=2000)
    b = S.perm_p(scores, pos, exact_limit=1, mc=2000)
    assert a == b
    assert a[1] == "monte_carlo"
    assert 0 < a[0] <= 1


def test_wilson_matches_bench() -> None:
    assert S.wilson(19, 24) == pytest.approx(wilson_interval(19, 24))
    assert S.wilson(0, 0) is None


def _run(task: str, model: str, solved: bool, tier: str = "cheap") -> dict:
    return {"task": task, "tier": tier, "model": model, "solved": solved, "cost_usd": 0.01}


def test_labels_max_over_members() -> None:
    runs = [
        _run("t", "m1", True),
        _run("t", "m1", False),
        _run("t", "m1", False),
        _run("t", "m2", True),
        _run("t", "m2", True),
        _run("t", "m2", False),
        _run("u", "m1", True),
        _run("u", "m1", False),
        _run("u", "m1", False),
    ]
    got = S.labels(runs)
    assert got["t"] is True
    assert got["u"] is False


def test_set_baseline() -> None:
    task_set = {"t1": "a", "t2": "a", "t3": "a", "t4": "b"}
    cheap_ok = {"t1": True, "t2": False, "t3": False, "t4": True}
    assert S.set_baseline(task_set, cheap_ok) == {"t1": 1.0, "t2": 0.5, "t3": 0.5, "t4": 0.5}


def test_s3_uses_loo_knn() -> None:
    feats = {
        "a": {"judge": 1.0, "scope_files": 0.0, "named_missing": 0.0},
        "b": {"judge": 2.0, "scope_files": 1.0, "named_missing": 0.0},
        "c": {"judge": 9.0, "scope_files": 5.0, "named_missing": 1.0},
        "d": {"judge": 10.0, "scope_files": 6.0, "named_missing": 2.0},
    }
    cheap_ok = {"a": True, "b": True, "c": False, "d": False}
    got = S.s3_scores(feats, cheap_ok)
    history = [HistoryRow(u, feats[u], cheap_ok[u]) for u in feats]
    for t in feats:
        assert got[t] == knn_score(feats[t], history, k=3, exclude_task=t)


def test_policy_and_loo_threshold() -> None:
    cheap = {"tA": (3, 3, 0.03), "tB": (0, 3, 0.03), "tC": (0, 3, 0.03)}
    strong = {"tA": (3, 3, 0.30), "tB": (3, 3, 0.30), "tC": (3, 3, 0.30)}
    scores = {"tA": 1.0, "tB": 5.0, "tC": 6.0}
    assert S.loo_threshold(scores, ["tB", "tC"], cheap, strong) == 5
    assert S.loo_threshold(scores, ["tA", "tC"], cheap, strong) == 6
    assert S.loo_threshold(scores, ["tA", "tB"], cheap, strong) == 5
    routed = S.routed(scores, cheap, strong)
    assert routed["tA"] == (5, "cheap")
    assert routed["tB"] == (6, "cheap")
    assert routed["tC"] == (5, "strong")
    dec = {t: tier for t, (_, tier) in routed.items()}
    routed_pol = S.policy(dec, cheap, strong)
    assert (routed_pol["k"], routed_pol["n"]) == (6, 9)
    assert routed_pol["cost"] == pytest.approx(0.36)
    assert routed_pol["spd"] == pytest.approx(16.667, abs=1e-3)
    always = S.policy({t: "strong" for t in scores}, cheap, strong)
    assert (always["k"], always["n"]) == (9, 9)
    assert always["cost"] == pytest.approx(0.90)
    assert always["spd"] == pytest.approx(10.0)
    oracle = S._oracle(["tA", "tB", "tC"], cheap, strong)
    assert oracle == {"tA": "cheap", "tB": "strong", "tC": "strong"}
    oracle_pol = S.policy(oracle, cheap, strong)
    assert (oracle_pol["k"], oracle_pol["n"]) == (9, 9)
    assert oracle_pol["cost"] == pytest.approx(0.63)


def test_s4_policy() -> None:
    units = [
        {"task": "t", "solved": False, "cost_usd": 0.02, "markers": 3, "prefix_cost_usd": 0.004},
        {"task": "t", "solved": True, "cost_usd": 0.01, "markers": 0, "prefix_cost_usd": 0.004},
    ]
    strong = {"t": (2, 3, 0.30)}
    p = S.s4_policy(units, 2, strong)
    assert p["k"] == pytest.approx(2 / 3 + 1)
    assert p["cost"] == pytest.approx(0.004 + 0.10 + 0.01)


def _metric(**kw: object) -> dict:
    base = {
        "auroc": 0.5,
        "p": 0.5,
        "baseline": 0.5,
        "spd": 1.0,
        "ratio": 0.5,
        "strong_spd": 2.0,
        "strong_ratio": 0.5,
    }
    base.update(kw)
    return base


def _all_fail() -> dict:
    return {n: _metric() for n in ("S1a", "S1b", "S2", "S3", "S4")}


def test_decide_pass_rule() -> None:
    good = _metric(
        auroc=0.8, p=0.01, baseline=0.5, spd=3.0, ratio=0.8, strong_spd=2.0, strong_ratio=0.8
    )
    m = _all_fail()
    m["S2"] = good
    verdict, lines = S.decide_pass(m)
    assert verdict == "PASS"
    assert lines[0] == "PASS — M19e2 proceeds."

    m = _all_fail()
    m["S2"] = _metric(**{**good, "p": 0.03})
    assert S.decide_pass(m)[0] == "FAIL"

    m = _all_fail()
    m["S2"] = _metric(**{**good, "baseline": 0.85})
    assert S.decide_pass(m)[0] == "FAIL"

    m = _all_fail()
    m["S1a"] = good
    verdict, lines = S.decide_pass(m)
    assert verdict == "PASS"
    assert "S1a-only PASS: needs a paid strong-judge call in M19e3." in lines


def _synthetic_inputs() -> list[dict]:
    rows = []
    for task, set_name, judge, scope, missing in (
        ("t1", "multi", 4.0, 0.0, 0.0),
        ("t2", "multi", 9.0, 2.0, 1.0),
        ("t3", "hard", 14.0, 3.0, 0.0),
    ):
        rows.append(
            {
                "task": task,
                "set": set_name,
                "features": {
                    "n_files": 2.0,
                    "n_py_files": 1.0,
                    "total_lines": 10.0,
                    "spec_chars": 0.0,
                    "named_paths": 1.0,
                    "named_missing": missing,
                    "scope_files": scope,
                    "judge": judge,
                },
            }
        )
    return rows


def test_main_offline_on_synthetic(tmp_path, no_network) -> None:
    runs = []
    plan = {"t1": (0, 3), "t2": (3, 3), "t3": (1, 3)}
    for task, (cheap_k, _) in plan.items():
        for i in range(3):
            runs.append(
                {
                    "task": task,
                    "set": "x",
                    "tier": "cheap",
                    "cell": "C-cheap",
                    "model": "m1",
                    "solved": i < cheap_k,
                    "cost_usd": 0.01,
                    "s4": {"markers": i, "prefix_cost_usd": 0.001},
                    "s4_status": "ok",
                }
            )
            runs.append(
                {
                    "task": task,
                    "set": "x",
                    "tier": "strong",
                    "cell": "C-strong",
                    "model": "s",
                    "solved": True,
                    "cost_usd": 0.10,
                    "s4": None,
                    "s4_status": "n/a",
                }
            )
    judges = []
    for task in plan:
        judges.append({"task": task, "judge": "S1a", "status": "ok", "score": 5})
        judges.append({"task": task, "judge": "S1b", "status": "ok", "score": 5})
    inputs = _synthetic_inputs()
    rp, ip, jp = tmp_path / "runs.jsonl", tmp_path / "inputs.jsonl", tmp_path / "judges.jsonl"
    rp.write_text("\n".join(json.dumps(r) for r in runs) + "\n", encoding="utf-8")
    ip.write_text("\n".join(json.dumps(r) for r in inputs) + "\n", encoding="utf-8")
    jp.write_text("\n".join(json.dumps(r) for r in judges) + "\n", encoding="utf-8")
    out = tmp_path / "s.md"
    code = S.main(
        [
            "--runs",
            str(rp),
            "--inputs",
            str(ip),
            "--judges",
            str(jp),
            "--skip-guard",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "## Decision" in text
    assert "Decisions differ across tasks" in text
    assert "cost: $0" in text
    assert no_network == []


def test_guard_blocks_without_prereg(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(S, "committed_bench_results", lambda: "")
    code = S.main(
        [
            "--runs",
            str(tmp_path / "missing-runs.jsonl"),
            "--inputs",
            str(tmp_path / "missing-inputs.jsonl"),
            "--judges",
            str(tmp_path / "missing-judges.jsonl"),
            "--out",
            str(tmp_path / "s.md"),
        ]
    )
    assert code == 2
