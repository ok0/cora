from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cora.bench.compare import load_compare_baseline
from cora.bench.stats import wilson_interval
from m19_panel import (
    PanelError,
    Row,
    apply_cost_basis,
    apply_error_policy,
    baseline_pool,
    cells,
    classes,
    classify,
    complementarity,
    completeness,
    delegation,
    load_extras,
    load_rows,
    main,
    p1,
    parse_thresholds,
    pooled,
)

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "tests" / "m19_panel.py"


def _result(task, model, solved, cost, latency=10.0, arm=None, **extra):
    row = {
        "task": task,
        "model": model,
        "status": "solved" if solved else "failed",
        "cost_usd": cost,
        "latency_s": latency,
        "protocol": "test",
    }
    if arm is not None:
        row["arm"] = arm
    row.update(extra)
    return row


def _write_report(tmp_path: Path, name: str, results: list[dict], settings=None) -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps({"settings": settings or {}, "results": results}), encoding="utf-8"
    )
    return path


def _runs(task, model, solved_count, total, cost):
    return [
        _result(task, model, index < solved_count, cost) for index in range(total)
    ]


@pytest.fixture
def reports(tmp_path):
    a_m1 = _write_report(
        tmp_path,
        "a_m1.json",
        _runs("t1", "m1", 3, 3, 0.01)
        + _runs("t2", "m1", 1, 3, 0.01)
        + _runs("t3", "m1", 0, 3, 0.01)
        + [_result("t1", "m1", False, 0.01, status="error", aborted_run=True)],
    )
    a_m2 = _write_report(
        tmp_path,
        "a_m2.json",
        _runs("t1", "m2", 0, 10, 0.02)
        + _runs("t2", "m2", 1, 10, 0.02)
        + _runs("t3", "m2", 0, 10, 0.02),
    )
    b_m1 = _write_report(
        tmp_path,
        "b_m1.json",
        _runs("t1", "m1", 10, 10, 0.003)
        + _runs("t2", "m1", 10, 10, 0.003)
        + _runs("t3", "m1", 10, 10, 0.003),
    )
    d = _write_report(
        tmp_path,
        "d.json",
        [
            _result(
                "t1",
                "m1",
                True,
                0.02,
                latency=30,
                arm="deleg-on-par-on",
                deleg_attempts=2,
                deleg_attempts_unparsed=1,
                deleg_invocations=1,
            ),
            _result(
                "t1",
                "m1",
                False,
                0.01,
                latency=20,
                arm="deleg-on-par-on",
                deleg_attempts=1,
                deleg_attempts_unparsed=0,
                deleg_invocations=0,
            ),
            _result("t1", "m1", False, 0.01, latency=10, arm="deleg-off"),
        ],
    )
    ab_auto = _write_report(
        tmp_path,
        "ab_auto.json",
        [_result("t1", "auto", True, 0.01, arm="auto-routed")],
        settings={"ab": {"model": "m1"}},
    )
    base = tmp_path / "base.toml"
    base.write_text(
        "\n".join(
            [
                "[meta]",
                'tool = "claude-code"',
                'model = "claude-test"',
                'date = "2026-10-01"',
                'source = "synthetic test"',
                "synthetic = true",
                "",
                "[tasks.t1]",
                "solved = 1.0",
                "n = 3",
                "cost_usd = 0.10",
                "wall_s = 10.0",
                "",
                "[tasks.t2]",
                "solved = 1.0",
                "n = 3",
                "cost_usd = 0.10",
                "wall_s = 10.0",
                "",
                "[tasks.t3]",
                "solved = 1.0",
                "n = 3",
                "cost_usd = 0.10",
                "wall_s = 10.0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "a_m1": a_m1,
        "a_m2": a_m2,
        "b_m1": b_m1,
        "d": d,
        "ab_auto": ab_auto,
        "base": base,
    }


def _synthetic_rows(reports) -> list[Row]:
    return (
        load_rows(f"a={reports['a_m1']}")
        + load_rows(f"a={reports['a_m2']}")
        + load_rows(f"b={reports['b_m1']}")
    )


def _cell(items, arm, model, task):
    return next(
        c for c in items if (c["arm"], c["model"], c["task"]) == (arm, model, task)
    )


def _pool(items, arm, model):
    return next(p for p in items if (p["arm"], p["model"]) == (arm, model))


def test_cells(reports):
    items = cells(_synthetic_rows(reports))

    c = _cell(items, "a", "m1", "t1")
    assert (c["k"], c["n"]) == (3, 3)
    assert c["wilson"][0] == pytest.approx(0.438, abs=1e-3)
    assert c["wilson"][1] == pytest.approx(1.000, abs=1e-3)
    assert c["cost_usd"] == pytest.approx(0.0300)

    c = _cell(items, "a", "m1", "t2")
    assert (c["k"], c["n"]) == (1, 3)
    assert c["wilson"][0] == pytest.approx(0.061, abs=1e-3)
    assert c["wilson"][1] == pytest.approx(0.792, abs=1e-3)

    c = _cell(items, "a", "m1", "t3")
    assert (c["k"], c["n"]) == (0, 3)
    assert c["wilson"][0] == pytest.approx(0.000, abs=1e-3)
    assert c["wilson"][1] == pytest.approx(0.562, abs=1e-3)

    c = _cell(items, "a", "m2", "t2")
    assert (c["k"], c["n"]) == (1, 10)
    assert c["wilson"][0] == pytest.approx(0.018, abs=1e-3)
    assert c["wilson"][1] == pytest.approx(0.404, abs=1e-3)

    c = _cell(items, "a", "m2", "t1")
    assert (c["k"], c["n"]) == (0, 10)
    assert c["wilson"][0] == pytest.approx(0.000, abs=1e-3)
    assert c["wilson"][1] == pytest.approx(0.278, abs=1e-3)

    c = _cell(items, "b", "m1", "t1")
    assert (c["k"], c["n"]) == (10, 10)
    assert c["wilson"][0] == pytest.approx(0.722, abs=1e-3)
    assert c["wilson"][1] == pytest.approx(1.000, abs=1e-3)

    assert sum(c["n"] for c in items if (c["arm"], c["model"]) == ("a", "m1")) == 9


def test_pooled(reports):
    items = pooled(_synthetic_rows(reports))

    p = _pool(items, "a", "m1")
    assert (p["k"], p["n"]) == (4, 9)
    assert p["ratio"] == pytest.approx(0.444, abs=1e-3)
    assert p["wilson"][0] == pytest.approx(0.189, abs=1e-3)
    assert p["wilson"][1] == pytest.approx(0.733, abs=1e-3)
    assert p["cost_usd"] == pytest.approx(0.0900)
    assert p["spd"] == pytest.approx(44.4, abs=0.1)

    p = _pool(items, "a", "m2")
    assert (p["k"], p["n"]) == (1, 30)
    assert p["ratio"] == pytest.approx(0.033, abs=1e-3)
    assert p["wilson"][0] == pytest.approx(0.006, abs=1e-3)
    assert p["wilson"][1] == pytest.approx(0.167, abs=1e-3)
    assert p["cost_usd"] == pytest.approx(0.6000)
    assert p["spd"] == pytest.approx(1.7, abs=0.1)

    p = _pool(items, "b", "m1")
    assert (p["k"], p["n"]) == (30, 30)
    assert p["ratio"] == pytest.approx(1.000)
    assert p["wilson"][0] == pytest.approx(0.886, abs=1e-3)
    assert p["wilson"][1] == pytest.approx(1.000, abs=1e-3)
    assert p["cost_usd"] == pytest.approx(0.0900)
    assert p["spd"] == pytest.approx(333.3, abs=0.1)


def test_classes(reports):
    baseline = load_compare_baseline(reports["base"])
    base = baseline_pool(baseline, {"t1", "t2", "t3"})
    assert (base["k"], base["n"]) == (9, 9)
    assert base["p"] == pytest.approx(1.0)
    assert base["spd"] == pytest.approx(10.0)

    items = classes(_synthetic_rows(reports), baseline, (0.70, 0.40, 2.0))
    by_role = {(c["role"], c["arm"], c["model"]): c for c in items}

    arm_m1 = by_role[("arm a", "a", "m1")]
    assert arm_m1["cls"] == "indeterminate"
    assert arm_m1["cost_advantage"] == "yes"

    arm_m2 = by_role[("arm a", "a", "m2")]
    assert arm_m2["cls"] == "c"
    assert arm_m2["cost_advantage"] == "no"

    best = by_role[("best", "b", "m1")]
    assert best["cls"] == "a"
    assert best["cost_advantage"] == "yes"

    assert classify(0.45, 0.5, 0.55, 0.70, 0.40) == "b"
    assert classify(0.75, 0.8, 0.9, 0.70, 0.40) == "a"


def _row(arm, model, task, solved, cost=0.01):
    return Row(
        arm=arm,
        model=model,
        task=task,
        solved=solved,
        cost_usd=cost,
        wall_s=1.0,
        deleg_attempts=0,
        deleg_attempts_unparsed=0,
        deleg_started=0,
    )


def _baseline_with(tmp_path, solved_by_task: dict[str, float]) -> Path:
    lines = [
        "[meta]",
        'tool = "claude-code"',
        'model = "claude-test"',
        'date = "2026-10-01"',
        'source = "synthetic test"',
        "synthetic = true",
        "",
    ]
    for task, solved in solved_by_task.items():
        lines += [
            f"[tasks.{task}]",
            f"solved = {solved!r}",
            "n = 3",
            "cost_usd = 0.10",
            "wall_s = 10.0",
            "",
        ]
    path = tmp_path / "baseline_custom.toml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_complementarity(reports):
    comp = complementarity(_synthetic_rows(reports))
    assert dict(comp["per_task"]) == {"t1": ["m1"], "t2": ["m1", "m2"], "t3": []}
    assert comp["union"] == 2
    assert comp["tasks"] == 3
    assert comp["oracle"] == pytest.approx(0.4444, abs=1e-3)
    assert comp["best_single"] == ("m1", 2)
    assert [c for _, _, c in comp["oracle_per_task"]] == pytest.approx(
        [0.01, 0.01, 0.01]
    )
    assert comp["oracle_spd"] == pytest.approx(44.44, abs=0.01)


def test_oracle_tie_cheapest():
    rows = [
        _row("a", "m1", "t1", True, 0.02),
        _row("a", "m1", "t1", True, 0.02),
        _row("a", "m1", "t1", True, 0.02),
        _row("a", "m2", "t1", True, 0.01),
        _row("a", "m2", "t1", True, 0.01),
        _row("a", "m2", "t1", True, 0.01),
    ]
    comp = complementarity(rows)
    assert [(t, mx) for t, mx, _ in comp["oracle_per_task"]] == [("t1", 1.0)]
    assert comp["oracle_per_task"][0][2] == pytest.approx(0.01)

    rows = [
        _row("a", "m1", "t1", False, 0.03),
        _row("a", "m1", "t1", False, 0.03),
        _row("a", "m1", "t1", False, 0.03),
        _row("a", "m2", "t1", False, 0.02),
        _row("a", "m2", "t1", False, 0.02),
        _row("a", "m2", "t1", False, 0.02),
    ]
    comp = complementarity(rows)
    assert comp["oracle_per_task"][0][1] == 0.0
    assert comp["oracle_per_task"][0][2] == pytest.approx(0.02)


def test_completeness():
    short_rows = [
        _row("a", "m1", "t1", True),
        _row("a", "m1", "t1", True),
        _row("a", "m1", "t1", True),
        _row("a", "m1", "t2", True),
        _row("a", "m1", "t2", True),
    ]
    kept, incomplete = completeness(short_rows)
    assert kept == []
    assert len(incomplete) == 1
    assert incomplete[0]["short"] == [("t2", 2)]

    hard_short = [
        _row("a", "m1", task, True)
        for task in ("e2e_h01", "e2e_h02", "e2e_h03", "e2e_h04", "e2e_h05", "e2e_h06")
        for _ in range(3)
    ]
    kept, incomplete = completeness(hard_short)
    assert kept == []
    assert incomplete[0]["missing"] == ["e2e_hx1", "e2e_hx2"]

    full = [
        _row("a", "m1", task, True)
        for task in (
            "e2e_h01",
            "e2e_h02",
            "e2e_h03",
            "e2e_h04",
            "e2e_h05",
            "e2e_h06",
            "e2e_hx1",
            "e2e_hx2",
        )
        for _ in range(3)
    ]
    kept, incomplete = completeness(full)
    assert len(kept) == 24
    assert incomplete == []


def test_label_task_filter(reports):
    rows = load_rows(f"d2@t1,t3={reports['a_m1']}")
    assert {r.arm for r in rows} == {"d2"}
    assert {r.task for r in rows} <= {"t1", "t3"}
    assert len(rows) == 6
    with pytest.raises(PanelError):
        load_rows(f"d2@={reports['a_m1']}")


def test_best_by_pooled_ratio(tmp_path):
    baseline = load_compare_baseline(
        _baseline_with(tmp_path, {"t1": 1.0, "t2": 0.3333333333333333})
    )
    rows = [
        _row("a", "m1", "t1", True),
        _row("a", "m1", "t1", True),
        _row("a", "m1", "t1", False),
        _row("b", "m1", "t2", True),
        _row("b", "m1", "t2", False),
        _row("b", "m1", "t2", False),
    ]
    items = classes(rows, baseline, (0.70, 0.40, 2.0))
    best = next(c for c in items if c["role"] == "best")
    assert best["arm"] == "a"


def test_s_cc_interval(reports):
    baseline = load_compare_baseline(reports["base"])
    items = classes(_synthetic_rows(reports), baseline, (0.70, 0.40, 2.0))
    normal = [c for c in items if c["cls"] != "blocked"]
    assert normal
    for c in normal:
        assert c["s_cc"] == pytest.approx(1.0)
        assert c["s_cc_wilson"] == wilson_interval(9, 9)


def test_classes_blocked_when_s_cc_zero(reports, tmp_path):
    baseline = load_compare_baseline(
        _baseline_with(tmp_path, {"t1": 0.0, "t2": 0.0, "t3": 0.0})
    )
    items = classes(_synthetic_rows(reports), baseline, (0.70, 0.40, 2.0))
    arm_a = [c for c in items if c["arm"] == "a"]
    assert arm_a
    assert all(c["cls"] == "blocked" for c in arm_a)
    assert not any(c["role"] == "best" for c in items)


def test_p1_table(reports):
    result = p1(_synthetic_rows(reports))
    row = next(
        r for r in result["rows"] if (r["mechanism"], r["model"]) == ("b", "m1")
    )
    assert row["decision"] == "ON"
    assert row["best_a_model"] == "m1"
    assert result["verdicts"] == {
        "b": "ON proposed",
        "c_s": "not measured",
        "c_cc": "not measured",
        "d1": "not measured",
    }


def test_baseline_none(reports, capsys):
    assert main([f"a={reports['a_m1']}", "--baseline", "none"]) == 0
    out = capsys.readouterr().out
    assert "blocked: no Claude Code baseline" in out
    assert "(f) P1" in out


def test_delegation_table(reports):
    items = delegation(load_rows(f"{reports['d']}"))

    on = next(i for i in items if (i["arm"], i["model"]) == ("deleg-on-par-on", "m1"))
    assert on["runs"] == 2
    assert on["attempts"] == 3
    assert on["attempts_unparsed"] == 1
    assert on["started"] == 1
    assert on["solved"] == 1
    assert on["cost_usd"] == pytest.approx(0.0300)
    assert on["wall_s"] == pytest.approx(50.0)

    off = next(i for i in items if (i["arm"], i["model"]) == ("deleg-off", "m1"))
    assert off["runs"] == 1
    assert off["attempts"] == 0
    assert off["attempts_unparsed"] == 0
    assert off["started"] == 0
    assert off["solved"] == 0
    assert off["cost_usd"] == pytest.approx(0.0100)
    assert off["wall_s"] == pytest.approx(10.0)


def test_auto_model_from_settings(reports):
    rows = load_rows(f"c={reports['ab_auto']}")
    assert len(rows) == 1
    assert rows[0].arm == "c"
    assert rows[0].model == "m1"


def test_thresholds_parse():
    assert parse_thresholds("0.70,0.40,2.0") == (0.7, 0.4, 2.0)
    for bad in ("0.4,0.7,2", "a,b,c", "0.7,0.4"):
        with pytest.raises(PanelError):
            parse_thresholds(bad)


def test_deterministic_and_out(reports, tmp_path, capsys):
    out = tmp_path / "panel.md"
    specs = [
        f"a={reports['a_m1']}",
        f"a={reports['a_m2']}",
        f"b={reports['b_m1']}",
    ]
    args = [*specs, "--baseline", str(reports["base"]), "--thresholds", "0.70,0.40,2.0"]

    assert main([*args, "--out", str(out)]) == 0
    first = capsys.readouterr().out
    assert main([*args, "--out", str(out)]) == 0
    second = capsys.readouterr().out

    assert first == second
    assert out.read_text(encoding="utf-8") == second
    assert "indeterminate" in second
    assert "union: 2 of 3 tasks" in second
    assert "oracle_ratio: 0.444" in second


@pytest.mark.parametrize(
    "case",
    [
        "missing_report",
        "malformed_json",
        "no_results",
        "missing_baseline_flag",
        "baseline_file_missing",
        "bad_thresholds",
    ],
)
def test_bad_input_exit_nonzero(reports, tmp_path, case):
    a_m1 = str(reports["a_m1"])
    base = str(reports["base"])
    if case == "missing_report":
        argv = [str(tmp_path / "missing.json"), "--baseline", base]
    elif case == "malformed_json":
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        argv = [str(bad), "--baseline", base]
    elif case == "no_results":
        bad = tmp_path / "no_results.json"
        bad.write_text(json.dumps({"settings": {}}), encoding="utf-8")
        argv = [str(bad), "--baseline", base]
    elif case == "missing_baseline_flag":
        argv = [a_m1]
    elif case == "baseline_file_missing":
        argv = [a_m1, "--baseline", str(tmp_path / "nope.toml")]
    else:
        argv = [a_m1, "--baseline", base, "--thresholds", "0.7,x,2"]

    result = subprocess.run(
        [sys.executable, str(PANEL), *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert result.stderr
    assert "Traceback" not in result.stderr


def test_default_output_golden(capsys, monkeypatch):
    monkeypatch.chdir(ROOT)
    args = (
        (ROOT / "tests/fixtures/m19/panel-golden-args.txt")
        .read_text(encoding="utf-8")
        .split()
    )
    assert main([*args, "--baseline", "none", "--thresholds", "0.70,0.40,2.0"]) == 0
    out = capsys.readouterr().out
    golden = (ROOT / "tests/fixtures/m19/panel-golden-default.md").read_text(
        encoding="utf-8"
    )
    assert out == golden


@pytest.fixture
def rerun_case(tmp_path):
    orig = _write_report(
        tmp_path,
        "orig.json",
        [
            _result(
                "t1",
                "m2",
                False,
                0.01,
                status="error",
                repeat_index=0,
                call_latencies_s=[10, 95, 100],
            ),
            _result("t1", "m2", True, 0.01, repeat_index=1),
            _result("t1", "m2", False, 0.01, repeat_index=2),
            _result("t2", "m2", True, 0.01, repeat_index=0),
            _result("t2", "m2", True, 0.01, repeat_index=1),
            _result("t2", "m2", True, 0.01, repeat_index=2),
        ],
    )
    rr = _write_report(
        tmp_path,
        "rr.json",
        [_result("t1", "m2", True, 0.02, repeat_index=0)],
    )
    data = {
        "reruns": [
            {
                "id": "RR-01",
                "of": "M19-08",
                "task": "t1",
                "repeat_index": 0,
                "orig_report": str(orig),
                "rerun_report": str(rr),
                "status": "executed",
            }
        ],
        "billed": [
            {
                "id": "M19-08",
                "report": str(orig),
                "report_cost": 0.06,
                "billed": 0.09,
            },
            {
                "id": "RR-01",
                "report": str(rr),
                "report_cost": 0.02,
                "billed": 0.02,
            },
        ],
    }
    extras = tmp_path / "extras.json"
    extras.write_text(json.dumps(data), encoding="utf-8")
    return {"orig": orig, "rr": rr, "extras": extras, "data": data}


def test_error_policies(rerun_case):
    raw = load_rows(f"a={rerun_case['orig']}")
    extras = load_extras(str(rerun_case["extras"]))

    def m2(policy):
        rows, _ = apply_error_policy(raw, extras, policy)
        return rows, _pool(pooled(rows), "a", "m2")

    rows, p = m2("unsolved")
    assert (p["k"], p["n"]) == (4, 6)
    assert p["cost_usd"] == pytest.approx(0.06)

    rows, p = m2("exclude")
    assert (p["k"], p["n"]) == (4, 5)
    assert p["cost_usd"] == pytest.approx(0.05)
    _, incomplete = completeness(rows)
    assert incomplete[0]["short"] == [("t1", 2)]

    rows, p = m2("replace")
    assert (p["k"], p["n"]) == (5, 6)
    assert p["cost_usd"] == pytest.approx(0.07)


def test_cost_basis_billed(rerun_case):
    raw = load_rows(f"a={rerun_case['orig']}")
    extras = load_extras(str(rerun_case["extras"]))
    expected = {"unsolved": 0.09, "exclude": 0.08, "replace": 0.10}
    for policy, cost in expected.items():
        rows, _ = apply_error_policy(raw, extras, policy)
        rows = apply_cost_basis(rows, extras, "billed")
        p = _pool(pooled(rows), "a", "m2")
        assert p["cost_usd"] == pytest.approx(cost, abs=1e-9)


def test_sensitivity_output(rerun_case, capsys):
    argv = [
        f"a={rerun_case['orig']}",
        "--baseline",
        "none",
        "--extras",
        str(rerun_case["extras"]),
        "--sensitivity",
    ]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "error policy: unsolved" in out
    assert "(g) sensitivity" in out
    assert "| a | m2 | replace/billed | 5/6 | 0.833 | 0.1000 |" in out
    assert "rerun RR-01 (of M19-08): a m2 t1 r0 -> solved" in out
    assert "billed extra total: 0.030000" in out
    assert "| a | m2 | t1 | 3 | 1 | 2 | 100.0 |" in out


def test_extras_required(rerun_case, capsys):
    argv = [f"a={rerun_case['orig']}", "--baseline", "none", "--error-policy", "replace"]
    assert main(argv) == 2
    assert "need --extras" in capsys.readouterr().err


def test_rerun_not_executed_keeps_original(rerun_case, tmp_path):
    data = rerun_case["data"]
    data["reruns"][0]["status"] = "not_measured"
    path = tmp_path / "not_executed.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    raw = load_rows(f"a={rerun_case['orig']}")
    extras = load_extras(str(path))
    unsolved, info = apply_error_policy(raw, extras, "unsolved")
    replaced, _ = apply_error_policy(raw, extras, "replace")
    assert replaced == unsolved
    assert info[0]["outcome"] == "not run (not_measured)"


@pytest.mark.parametrize(
    "case", ["original_solved", "rerun_two_results", "malformed_extras"]
)
def test_rerun_bad_inputs(rerun_case, tmp_path, case):
    data = json.loads(rerun_case["extras"].read_text(encoding="utf-8"))
    if case == "original_solved":
        data["reruns"][0]["repeat_index"] = 1
    elif case == "rerun_two_results":
        two = _write_report(
            tmp_path,
            "rr2.json",
            [
                _result("t1", "m2", True, 0.02, repeat_index=0),
                _result("t1", "m2", True, 0.02, repeat_index=1),
            ],
        )
        data["reruns"][0]["rerun_report"] = str(two)
    else:
        data = {"reruns": "bad", "billed": []}
    path = tmp_path / "bad_extras.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    argv = [
        f"a={rerun_case['orig']}",
        "--baseline",
        "none",
        "--extras",
        str(path),
        "--error-policy",
        "replace",
    ]
    assert main(argv) == 2


def test_replace_several_reruns_one_report(tmp_path):
    c = _write_report(
        tmp_path,
        "c.json",
        [
            _result("t1", "m2", False, 0.01, status="error", repeat_index=0),
            _result("t1", "m2", False, 0.01, status="error", repeat_index=1),
            _result("t1", "m2", False, 0.01, status="error", repeat_index=2),
            _result("t2", "m2", False, 0.01, status="failed", repeat_index=0),
            _result("t2", "m2", False, 0.01, status="failed", repeat_index=1),
            _result("t2", "m2", False, 0.01, status="error", repeat_index=2),
        ],
    )
    rr06 = _write_report(
        tmp_path, "rr06.json", [_result("t1", "m2", True, 0.02, repeat_index=0)]
    )
    rr07 = _write_report(
        tmp_path, "rr07.json", [_result("t1", "m2", False, 0.02, repeat_index=0)]
    )
    rr08 = _write_report(
        tmp_path, "rr08.json", [_result("t1", "m2", True, 0.02, repeat_index=0)]
    )
    rr09 = _write_report(
        tmp_path, "rr09.json", [_result("t2", "m2", True, 0.02, repeat_index=0)]
    )

    def rerun(rid, task, index, report):
        return {
            "id": rid,
            "of": "M19-43",
            "task": task,
            "repeat_index": index,
            "orig_report": str(c),
            "rerun_report": str(report),
            "status": "executed",
        }

    data = {
        "reruns": [
            rerun("RR-06", "t1", 0, rr06),
            rerun("RR-07", "t1", 1, rr07),
            rerun("RR-08", "t1", 2, rr08),
            rerun("RR-09", "t2", 2, rr09),
        ],
        "billed": [],
    }
    extras = tmp_path / "extras_several.json"
    extras.write_text(json.dumps(data), encoding="utf-8")

    rows = load_rows(f"c_s={c}")
    out, info = apply_error_policy(rows, load_extras(str(extras)), "replace")

    assert len(out) == 6
    assert sum(r.solved for r in out) == 3
    counts = {}
    for r in out:
        counts[r.task] = counts.get(r.task, 0) + 1
    assert counts == {"t1": 3, "t2": 3}
    assert [i["outcome"] for i in info] == ["solved", "failed", "solved", "solved"]
    assert completeness(out)[1] == []
    assert sum(r.cost_usd for r in out) == pytest.approx(0.10)
