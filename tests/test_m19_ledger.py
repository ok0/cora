from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import m19_ledger as M

NOW = "2026-10-19T00:00:00Z"
RESULTS_DOC = M.ROOT / ".docs/bench-results.md"


def run(ledger: Path, *argv: str, now: str = NOW) -> int:
    return M.main([argv[0], *argv[1:], "--ledger", str(ledger), "--now", now])


def init(ledger: Path, paid: float = 3.07, usage: float = 3.06, key: float = 5.0) -> None:
    rc = run(
        ledger,
        "init",
        "--paid-total",
        str(paid),
        "--usage",
        str(usage),
        "--key-remaining",
        str(key),
        "--balance",
        str(key),
        "--head",
        "abc1234",
        "--confirmed",
        "test",
    )
    assert rc == 0


def write_report(path: Path, cost: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"results": [{"cost_usd": cost}]}), encoding="utf-8")
    return path


def check_call(
    ledger: Path,
    call_id: str,
    *,
    plan: float | None = None,
    key: float = 5.0,
    usage: float | None = None,
    now: str = NOW,
) -> int:
    call = M.get_call(call_id)
    if plan is None:
        plan = call.plan_total if call.plan_total is not None else call.max_cost
    if usage is None:
        usage = M.fold(M.read_records(ledger)).last_usage
    return run(
        ledger,
        "check",
        call_id,
        "--plan-total",
        str(plan),
        "--key-remaining",
        str(key),
        "--balance",
        str(key),
        "--usage",
        str(usage),
        now=now,
    )


def execute(ledger: Path, tmp: Path, call_id: str, cost: float) -> None:
    before = M.fold(M.read_records(ledger)).last_usage
    assert before is not None
    assert check_call(ledger, call_id, usage=before) == 0
    report = write_report(tmp / f"{call_id}.json", cost)
    rc = run(
        ledger,
        "record",
        call_id,
        "--status",
        "executed",
        "--usage-before",
        str(before),
        "--usage-after",
        str(before + cost),
        "--report",
        str(report),
    )
    assert rc == 0


def mark(ledger: Path, call_id: str) -> None:
    assert run(ledger, "mark", call_id, "--status", "not_measured", "--reason", "test") == 0


def run_cell(ledger: Path, tmp: Path, name: str, executed: dict[str, float] | None = None) -> None:
    assert run(ledger, "cell", name) == 0
    for call in M.calls_of(name):
        if executed and call.id in executed:
            execute(ledger, tmp, call.id, executed[call.id])
        else:
            mark(ledger, call.id)


def statuses(ledger: Path) -> dict[str, str]:
    return M.fold(M.read_records(ledger)).status


def test_load_calls() -> None:
    calls = M.load_calls(M.PREREG.read_text(encoding="utf-8"))
    assert len(calls) == 51
    first = calls[0]
    assert first.id == "M19-01"
    assert first.cell == "a(m1)"
    assert first.tasks == ("e2e_h01", "e2e_h02")
    assert first.max_cost == 0.42
    assert first.plan_total == 0.330864
    assert first.out == ".cora/bench/m19/runs/a-m1-i01"
    assert "--sensor --sensor-source auto" in calls[34].command
    assert calls[34].id == "M19-35"
    sequence = list(dict.fromkeys(c.cell for c in calls))
    assert sequence == ["a(m1)", "a(m2)", "e", "c_s(m1)", "d1(m1)", "c_s(m2)", "d1(m2)", "a(m3)"]


def test_cell_order_matches_prereg() -> None:
    text = M.PREREG.read_text(encoding="utf-8")
    section = text.split("### 예상 비용과 절단선", 1)[1].split("### Claude Code 일정", 1)[0]
    rows = re.findall(r"^\| (\d+) \| (\S+) \| \d+ \| ([\d.]+) \|", section, re.MULTILINE)
    assert [(cell, float(expected)) for _, cell, expected in rows] == list(M.CELL_ORDER)


def test_plan_command() -> None:
    call = M.STATIC_CALLS[34]
    assert M.plan_command(call) == (
        "uv run cora bench plan -c .cora/bench/m19/cascade-strong.toml --suite e2e "
        "--models google/gemini-2.5-flash-lite --protocols react --ab auto-routed "
        "--tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42"
    )
    assert M.plan_command(M.get_call("M19-35")) == (
        "uv run cora bench plan -c .cora/bench/m19/deadline-cascade-strong.toml --suite e2e "
        "--models google/gemini-2.5-flash-lite --protocols react --ab auto-routed "
        "--tasks e2e_h01,e2e_h02 --repeats 3 --max-cost 0.42"
    )
    block = re.compile(
        r"^\[(M19-\d\d) · [^\]]*\][^\n]*\n  live: `[^`]*`\n  plan: `([^`]*)`",
        re.MULTILINE,
    )
    plans = dict(block.findall(RESULTS_DOC.read_text(encoding="utf-8")))
    assert len(plans) == 51
    for call in M.STATIC_CALLS:
        assert M.plan_command(call) == plans[call.id], call.id


def test_cell_rule(tmp_path: Path, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"
    init(ledger)
    run_cell(ledger, tmp_path, "a(m1)", {f"M19-{n:02d}": 0.17 for n in range(1, 6)})
    run_cell(ledger, tmp_path, "a(m2)", {f"M19-{n:02d}": 0.088 for n in range(6, 11)})
    run_cell(ledger, tmp_path, "e")
    assert run(ledger, "event", "checkpoint", "--note", "after e") == 0
    run_cell(ledger, tmp_path, "c_s(m1)", {f"M19-{n:02d}": 0.672 for n in range(35, 40)})
    capsys.readouterr()
    assert run(ledger, "cell", "b(m1)") == 0
    out = capsys.readouterr().out
    assert "remaining 1.350000 vs 1.5 x 1.1974 = 1.796100 -> SKIP" in out
    states = statuses(ledger)
    for n in range(1, 6):
        assert states[f"B1-{n:02d}"] == "not_measured"
    assert run(ledger, "cell", "c_s(m2)") == 1


def test_check_failures(tmp_path: Path, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"

    init(ledger)
    assert run(ledger, "cell", "a(m1)") == 0
    capsys.readouterr()
    assert check_call(ledger, "M19-01", plan=0.43) == 1
    assert "FAIL C3" in capsys.readouterr().out

    ledger = tmp_path / "c5.jsonl"
    init(ledger)
    assert run(ledger, "cell", "a(m1)") == 0
    capsys.readouterr()
    assert check_call(ledger, "M19-01", usage=3.07) == 1
    assert "FAIL C5" in capsys.readouterr().out

    ledger = tmp_path / "c6.jsonl"
    init(ledger)
    assert run(ledger, "cell", "a(m1)") == 0
    capsys.readouterr()
    assert check_call(ledger, "M19-01", key=0.30) == 1
    assert "FAIL C6" in capsys.readouterr().out

    ledger = tmp_path / "c10.jsonl"
    init(ledger)
    assert run(ledger, "cell", "a(m1)") == 0
    capsys.readouterr()
    assert check_call(ledger, "M19-01", now="2026-10-22T09:12:00Z") == 1
    assert "FAIL C10" in capsys.readouterr().out

    ledger = tmp_path / "c8.jsonl"
    init(ledger)
    run_cell(ledger, tmp_path, "a(m1)")
    run_cell(ledger, tmp_path, "a(m2)")
    assert run(ledger, "cell", "e") == 0
    execute(ledger, tmp_path, "M19-11", 2.20)
    capsys.readouterr()
    assert check_call(ledger, "M19-12") == 1
    assert "FAIL C8" in capsys.readouterr().out

    ledger = tmp_path / "c12.jsonl"
    init(ledger)
    run_cell(ledger, tmp_path, "a(m1)")
    run_cell(ledger, tmp_path, "a(m2)")
    run_cell(ledger, tmp_path, "e")
    assert run(ledger, "cell", "c_s(m1)") == 0
    capsys.readouterr()
    assert check_call(ledger, "M19-35") == 1
    assert "FAIL C12" in capsys.readouterr().out
    assert run(ledger, "event", "checkpoint", "--note", "after e") == 0
    capsys.readouterr()
    assert check_call(ledger, "M19-35") == 0
    assert "FAIL" not in capsys.readouterr().out


def test_record_mismatch_settle(tmp_path: Path, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"
    init(ledger)
    assert run(ledger, "cell", "a(m1)") == 0
    assert check_call(ledger, "M19-01", usage=3.06) == 0
    report = write_report(tmp_path / "m01.json", 0.010)
    rc = run(
        ledger,
        "record",
        "M19-01",
        "--status",
        "executed",
        "--usage-before",
        "3.06",
        "--usage-after",
        "3.066",
        "--report",
        str(report),
    )
    assert rc == 1
    assert "MISMATCH M19-01" in capsys.readouterr().out
    assert M.fold(M.read_records(ledger)).m19_total == 0.010
    assert run(ledger, "settle", "M19-01", "--usage", "3.0701") == 0
    state = M.fold(M.read_records(ledger))
    assert abs(state.m19_total - 0.0101) < 1e-9
    assert not state.unresolved


def test_table_deterministic(tmp_path: Path, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"
    init(ledger)
    run_cell(ledger, tmp_path, "a(m1)", {"M19-01": 0.1})
    capsys.readouterr()
    assert run(ledger, "table") == 0
    first = capsys.readouterr().out
    assert run(ledger, "table") == 0
    second = capsys.readouterr().out
    assert first == second
    assert "`uv run cora bench --live --suite e2e --models google/gemini-2.5-flash-lite" in first
    assert "M19 누적" in first


def _settings(**overrides: object) -> dict:
    settings: dict = {
        "max_cost_usd": 0.39,
        "max_task_cost_usd": 0.39,
        "max_iterations": 20,
        "stall_threshold_s": 600.0,
        "protocols": ["react"],
        "tool_groups": ["core"],
        "tools": ["read"],
        "sensor": {"enabled": False},
        "seed": 1,
        "suite": "e2e",
        "verify_attempts": None,
        "e2e": {
            "tasks": [
                {"id": "e2e_hx1", "wall_s": 300, "cost_usd": 0.1},
                {"id": "e2e_hx2", "wall_s": 300, "cost_usd": 0.1},
            ],
            "policy_profile": "strict",
        },
        "models": [{"id": "google/gemini-2.5-flash-lite", "provider": "openrouter"}],
        "ab": {"model": "google/gemini-2.5-flash-lite", "arms": ["deleg-on-par-on"]},
    }
    settings.update(overrides)
    return settings


def _report(path: Path, settings: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"settings": settings}), encoding="utf-8")
    return path


def test_d2check(tmp_path: Path, capsys) -> None:
    d1 = _report(tmp_path / "d1.json", _settings())
    a_same = _report(
        tmp_path / "a_same.json",
        _settings(
            ab={"model": "other"},
            max_cost_usd=0.42,
            tasks=["e2e_hx1"],
            repeats=3,
            models=[
                {"id": "google/gemini-2.5-flash-lite", "provider": "openrouter"},
                {"id": "x/other", "provider": "openrouter"},
            ],
        ),
    )
    assert M.main(["d2check", "--a", str(a_same), "--d1", str(d1)]) == 0
    assert capsys.readouterr().out.strip() == "MATCH"

    a_diff = _report(tmp_path / "a_diff.json", _settings(max_iterations=30))
    assert M.main(["d2check", "--a", str(a_diff), "--d1", str(d1)]) == 1
    out = capsys.readouterr().out
    assert "DIFF max_iterations: a=30 d1=20" in out


def test_panel_args(tmp_path: Path, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"
    init(ledger)
    run_cell(ledger, tmp_path, "a(m1)", {"M19-04": 0.0})
    run_cell(ledger, tmp_path, "a(m2)")
    run_cell(ledger, tmp_path, "e")
    assert run(ledger, "event", "checkpoint", "--note", "after e") == 0
    run_cell(ledger, tmp_path, "c_s(m1)")
    run_cell(ledger, tmp_path, "b(m1)")
    run_cell(ledger, tmp_path, "d1(m1)", {"M19-40": 0.0})
    capsys.readouterr()
    assert run(ledger, "panel-args", "--d2", "m1") == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == [
        "a=.cora/bench/m19/runs/a-m1-i04/report.json",
        "d1=.cora/bench/m19/runs/d1-m1-i01/report.json",
        "d2@e2e_hx1,e2e_hx2=.cora/bench/m19/runs/a-m1-i04/report.json",
        "d2@e2e_hx1,e2e_hx2=.cora/bench/m19/runs/a-m1-i05/report.json",
    ]


def test_earliest(tmp_path: Path, capsys) -> None:
    runs = tmp_path / "runs"
    for name, stamp in (
        ("a-m1-i01", "2026-10-19T01:00:00+00:00"),
        ("a-m1-i02", "2026-10-19T00:30:00+00:00"),
    ):
        (runs / name).mkdir(parents=True)
        (runs / name / "report.json").write_text(
            json.dumps({"generated_at": stamp}), encoding="utf-8"
        )
    assert M.main(["earliest", str(runs)]) == 0
    out = capsys.readouterr().out.strip()
    assert out == f"2026-10-19T00:30:00+00:00 {runs / 'a-m1-i02' / 'report.json'}"


def test_conditional_calls() -> None:
    calls = M.CONDITIONAL_CALLS
    assert len(calls) == 19
    assert all(c.max_cost <= M.MAX_COST_CAP_USD for c in calls)
    b1 = [c for c in calls if c.id.startswith("B1-")]
    assert all("--verify-attempts 3" in c.command and " -c " not in c.command for c in b1)
    cc = [c for c in calls if c.id.startswith("CC-")]
    assert all("cascade-m1-m2.toml" in c.command for c in cc)


DEADLINE_DETAIL = "ProviderError: openrouter request failed: RequestDeadlineExceeded: timed out"


def write_error_report(
    path: Path, rows: list[tuple[str, int, str, str, float]], settings: dict | None = None
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    results = [
        {"task": task, "repeat_index": index, "status": status, "detail": detail, "cost_usd": cost}
        for task, index, status, detail, cost in rows
    ]
    data: dict = {"results": results}
    if settings is not None:
        data["settings"] = settings
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def execute_rows(
    ledger: Path,
    tmp: Path,
    call_id: str,
    rows: list[tuple[str, int, str, str, float]],
    settings: dict | None = None,
) -> None:
    cost = sum(row[4] for row in rows)
    report = write_error_report(tmp / f"{call_id}.json", rows, settings)
    before = M.fold(M.read_records(ledger)).last_usage
    assert before is not None
    assert check_call(ledger, call_id, usage=before) == 0
    rc = run(
        ledger,
        "record",
        call_id,
        "--status",
        "executed",
        "--usage-before",
        str(before),
        "--usage-after",
        str(before + cost),
        "--report",
        str(report),
    )
    assert rc == 0


ROUTING_DETAIL = (
    'ProviderError: openrouter HTTP 400: {"error":{"message":"Provider returned error",'
    '"code":400,"metadata":{"raw":"This model doesn\'t support the stopSequences field. '
    'Remove stopSequences"}}}'
)
M43_SETTINGS = {
    "max_task_cost_usd": 0.1,
    "e2e": {"tasks": [{"id": "e2e_h04", "cost_usd": 0.1}, {"id": "e2e_h05", "cost_usd": 0.05}]},
}
R44 = (
    "uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live "
    "--suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed "
    "--sensor --sensor-source auto --tasks e2e_h06 --repeats 3 --max-cost 0.27 "
    "--out .cora/bench/m19/runs/c_s-m2-i04"
)
D44 = R44.replace("deadline-nobedrock-cascade-strong.toml", "deadline-cascade-strong.toml")
M44_SETTINGS = {"max_task_cost_usd": 0.09, "e2e": {"tasks": [{"id": "e2e_h06", "cost_usd": 0.09}]}}
RR10_COMMAND = (
    "uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live "
    "--suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react --ab auto-routed "
    "--sensor --sensor-source auto --tasks e2e_h06 --repeats 1 --max-cost 0.09 "
    "--out .cora/bench/m19/runs/rerun-10"
)


def rerun_ledger(tmp: Path, h04: tuple[str, str] = ("error", DEADLINE_DETAIL)) -> Path:
    ledger = tmp / "ledger.jsonl"
    init(ledger)
    assert run(ledger, "cell", "a(m1)") == 0
    for call in M.calls_of("a(m1)"):
        mark(ledger, call.id)
    assert run(ledger, "cell", "a(m2)") == 0
    for call in M.calls_of("a(m2)"):
        if call.id == "M19-08":
            execute_rows(
                ledger,
                tmp,
                call.id,
                [
                    ("e2e_h04", 0, h04[0], h04[1], 0.02),
                    ("e2e_h05", 0, "solved", "", 0.02),
                    ("e2e_h05", 2, "error", DEADLINE_DETAIL, 0.02),
                ],
            )
        elif call.id == "M19-09":
            execute_rows(
                ledger,
                tmp,
                call.id,
                [
                    ("e2e_h06", 0, "error", DEADLINE_DETAIL, 0.03),
                    ("e2e_hx1", 0, "solved", "", 0.02),
                ],
            )
        else:
            mark(ledger, call.id)
    assert run(ledger, "cell", "e") == 0
    for call in M.calls_of("e"):
        if call.id == "M19-21":
            execute_rows(ledger, tmp, call.id, [("e2e_h04", 0, "error", DEADLINE_DETAIL, 0.10)])
        elif call.id == "M19-26":
            execute_rows(ledger, tmp, call.id, [("e2e_h06", 0, "error", DEADLINE_DETAIL, 0.10)])
        else:
            mark(ledger, call.id)
    return ledger


def routing_ledger(
    tmp: Path, h04_detail: str = ROUTING_DETAIL, settings: dict | None = M43_SETTINGS
) -> Path:
    ledger = rerun_ledger(tmp)
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    for n in range(1, 6):
        mark(ledger, f"RR-{n:02d}")
    assert run(ledger, "event", "checkpoint", "--note", "after e") == 0
    for name in ("c_s(m1)", "b(m1)", "d1(m1)", "c_cc(m1→m2)"):
        run_cell(ledger, tmp, name)
    assert run(ledger, "cell", "c_s(m2)") == 0
    mark(ledger, "M19-41")
    mark(ledger, "M19-42")
    execute_rows(
        ledger,
        tmp,
        "M19-43",
        [
            ("e2e_h04", 0, "error", h04_detail, 0.005),
            ("e2e_h05", 0, "failed", "", 0.03),
            ("e2e_h04", 1, "error", ROUTING_DETAIL, 0.0),
            ("e2e_h05", 1, "failed", "", 0.008),
            ("e2e_h04", 2, "error", ROUTING_DETAIL, 0.0003),
            ("e2e_h05", 2, "error", ROUTING_DETAIL, 0.0),
        ],
        settings=settings,
    )
    return ledger


def test_amendments_loaded() -> None:
    call = M.get_call("M19-29")
    assert call.command == (
        "uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e "
        "--models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 "
        "--tasks e2e_hx1 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/e-i19"
    )
    assert call.registered == (
        "uv run cora bench --live --suite e2e --models deepseek/deepseek-v3.2 "
        "--protocols react --e2e-task-cost 0.30 --tasks e2e_hx1 --repeats 1 "
        "--max-cost 0.30 --out .cora/bench/m19/runs/e-strong-i19"
    )
    assert call.amended == "수정"
    deviation = M.get_call("M19-11")
    assert deviation.out == ".cora/bench/m19/runs/e-i01"
    assert deviation.amended == "편차"
    assert M.get_call("M19-40").amended == ""
    assert M.get_call("M19-47").amended == ""
    amended = [c.amended for c in M.EFFECTIVE_STATIC]
    assert amended.count("편차") == 18
    assert amended.count("수정") == 17
    assert len(M.ALL_CALLS) == 70
    assert all(not c.id.startswith("RR-") for c in M.calls_of("a(m2)"))


def test_routing_amendments_loaded() -> None:
    assert M.get_call("M19-44").command == R44
    assert M.get_call("M19-44").amended == "수정"
    assert "deadline-cascade-strong.toml" in M.get_call("M19-43").command
    assert M._config_of(M.get_call("M19-46").command) == (
        ".cora/bench/m19/deadline-nobedrock-deleg-nudge.toml"
    )
    assert M.get_call("M19-47").amended == ""
    amended = [c.amended for c in M.EFFECTIVE_STATIC]
    assert amended.count("수정") == 17
    assert len(M.ALL_CALLS) == 70


def test_routing_amendment_validation() -> None:
    d44 = f"| 수정 M19-44 | `{D44}` |"
    r44 = f"| 수정 M19-44 | `{R44}` |"
    effective = M.apply_amendments(M.STATIC_CALLS, f"{d44}\n{r44}")
    assert effective[43].command == R44
    with pytest.raises(M.LedgerError):
        M.apply_amendments(M.STATIC_CALLS, f"{r44}\n{d44}")
    with pytest.raises(M.LedgerError):
        M.apply_amendments(M.STATIC_CALLS, r44)
    reg29 = M.STATIC_CALLS[28].command
    good = reg29.replace(" bench ", " bench -c .cora/bench/m19/deadline.toml ", 1).replace(
        "e-strong-i19", "e-i19"
    )
    routing29 = good.replace(
        "-c .cora/bench/m19/deadline.toml",
        "-c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml",
    )
    with pytest.raises(M.LedgerError):
        M.apply_amendments(
            M.STATIC_CALLS, f"| 수정 M19-29 | `{good}` |\n| 수정 M19-29 | `{routing29}` |"
        )


def test_routing_reruns_registry() -> None:
    assert M.get_call("RR-06").cause == "routing"
    assert M.get_call("RR-01").cause == "deadline"
    assert M.plan_command(M.get_call("RR-06")) == (
        "uv run cora bench plan -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml "
        "--suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react "
        "--ab auto-routed --tasks e2e_h04 --repeats 1 --max-cost 0.10"
    )
    registered = {c.id: c for c in M.STATIC_CALLS}
    row = re.search(r"^\| 재실행 RR-06 .*$", M.PREREG_TEXT, re.MULTILINE).group(0)
    row = row.replace("RR-06", "RR-01").replace("rerun-06", "rerun-01")
    reruns = M.load_reruns(row, registered)
    assert len(reruns) == 1
    assert reruns[0].cause == "routing"
    raised = row.replace("0.10", "0.46")
    with pytest.raises(M.LedgerError):
        M.load_reruns(raised, registered)
    other = row.replace(
        "deadline-nobedrock-cascade-strong.toml", "deadline-nobedrock-deleg-nudge.toml"
    )
    with pytest.raises(M.LedgerError):
        M.load_reruns(other, registered)


def test_routing_rerun_flow(tmp_path: Path, capsys) -> None:
    ledger = routing_ledger(tmp_path)
    capsys.readouterr()
    assert check_call(ledger, "RR-06", plan=0.10) == 1
    assert "FAIL C11" in capsys.readouterr().out
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    assert check_call(ledger, "RR-07", plan=0.10) == 1
    assert "FAIL C1" in capsys.readouterr().out
    assert check_call(ledger, "RR-06", plan=0.10) == 0
    out = capsys.readouterr().out
    assert "PASS C12" in out
    assert "PASS C14" in out
    usage = M.fold(M.read_records(ledger)).last_usage
    assert usage is not None
    report = write_error_report(tmp_path / "rr-06.json", [("e2e_h04", 0, "solved", "", 0.02)])
    rc = run(
        ledger,
        "record",
        "RR-06",
        "--status",
        "executed",
        "--usage-before",
        str(usage),
        "--usage-after",
        str(usage + 0.02),
        "--report",
        str(report),
    )
    assert rc == 0
    record = [r for r in M.read_records(ledger) if r["type"] == "call" and r["call"] == "RR-06"]
    assert record[-1]["of"] == "M19-43"
    assert record[-1]["outcome"] == "solved"
    execute_rows(ledger, tmp_path, "RR-07", [("e2e_h04", 0, "solved", "", 0.02)])
    execute_rows(ledger, tmp_path, "RR-08", [("e2e_h04", 0, "solved", "", 0.02)])
    before = M.fold(M.read_records(ledger)).last_usage
    assert before is not None
    assert check_call(ledger, "RR-09", plan=0.05, usage=before) == 0
    report = write_error_report(tmp_path / "rr-09.json", [("e2e_h05", 0, "solved", "", 0.02)])
    rc = run(
        ledger,
        "record",
        "RR-09",
        "--status",
        "executed",
        "--usage-before",
        str(before),
        "--usage-after",
        str(before + 0.02),
        "--report",
        str(report),
    )
    assert rc == 0

    (tmp_path / "x").mkdir()
    ledger = routing_ledger(tmp_path / "x")
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    mark(ledger, "M19-44")
    mark(ledger, "M19-45")
    assert run(ledger, "cell", "b(m2)") == 0
    capsys.readouterr()
    assert check_call(ledger, "RR-06", plan=0.10) == 1
    assert "FAIL C1" in capsys.readouterr().out


def test_routing_rerun_c12_needs_stopsequences(tmp_path: Path, capsys) -> None:
    ledger = routing_ledger(tmp_path, h04_detail=DEADLINE_DETAIL)
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    capsys.readouterr()
    assert check_call(ledger, "RR-06", plan=0.10) == 1
    assert "FAIL C12" in capsys.readouterr().out


def test_routing_rerun_c14_task_cap(tmp_path: Path, capsys) -> None:
    settings = {"max_task_cost_usd": 0.08, "e2e": {"tasks": [{"id": "e2e_h04", "cost_usd": 0.1}]}}
    ledger = routing_ledger(tmp_path, settings=settings)
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    capsys.readouterr()
    assert check_call(ledger, "RR-06", plan=0.10) == 1
    assert "FAIL C14" in capsys.readouterr().out


def test_panel_extras_routing(tmp_path: Path, capsys) -> None:
    ledger = routing_ledger(tmp_path)
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    assert check_call(ledger, "RR-06", plan=0.10) == 0
    usage = M.fold(M.read_records(ledger)).last_usage
    assert usage is not None
    report = write_error_report(tmp_path / "rr-06.json", [("e2e_h04", 0, "solved", "", 0.02)])
    assert (
        run(
            ledger,
            "record",
            "RR-06",
            "--status",
            "executed",
            "--usage-before",
            str(usage),
            "--usage-after",
            str(usage + 0.02),
            "--report",
            str(report),
        )
        == 0
    )
    capsys.readouterr()
    assert run(ledger, "panel-extras") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["reruns"][5] == {
        "id": "RR-06",
        "of": "M19-43",
        "task": "e2e_h04",
        "repeat_index": 0,
        "orig_report": ".cora/bench/m19/runs/c_s-m2-i03/report.json",
        "rerun_report": ".cora/bench/m19/runs/rerun-06/report.json",
        "status": "executed",
    }


def test_live_cmd_routing(capsys) -> None:
    assert M.main(["live-cmd", "RR-09"]) == 0
    assert capsys.readouterr().out.strip() == (
        "uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live "
        "--suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react "
        "--ab auto-routed --sensor --sensor-source auto --tasks e2e_h05 --repeats 1 "
        "--max-cost 0.05 --out .cora/bench/m19/runs/rerun-09"
    )
    assert M.main(["live-cmd", "M19-45"]) == 0
    assert capsys.readouterr().out.strip() == (
        "uv run cora bench -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml --live "
        "--suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react "
        "--ab auto-routed --sensor --sensor-source auto --tasks e2e_hx2 --repeats 3 "
        "--max-cost 0.24 --out .cora/bench/m19/runs/c_s-m2-i05"
    )


def rr10_ledger(
    tmp: Path, r2_detail: str = DEADLINE_DETAIL, settings: dict | None = M44_SETTINGS
) -> Path:
    ledger = routing_ledger(tmp)
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    for n in range(6, 10):
        mark(ledger, f"RR-{n:02d}")
    execute_rows(
        ledger,
        tmp,
        "M19-44",
        [
            ("e2e_h06", 0, "solved", "", 0.009),
            ("e2e_h06", 1, "failed", "", 0.017),
            ("e2e_h06", 2, "error", r2_detail, 0.017),
        ],
        settings=settings,
    )
    return ledger


def test_rr10_registry() -> None:
    rr = M.get_call("RR-10")
    assert (rr.of, rr.tasks, rr.repeat_index, rr.max_cost, rr.plan_total, rr.cause) == (
        "M19-44",
        ("e2e_h06",),
        2,
        0.09,
        0.09,
        "deadline-nobedrock",
    )
    assert rr.command == RR10_COMMAND
    assert M.get_call("RR-06").cause == "routing"
    assert M.plan_command(rr) == (
        "uv run cora bench plan -c .cora/bench/m19/deadline-nobedrock-cascade-strong.toml "
        "--suite e2e --models qwen/qwen3-coder-30b-a3b-instruct --protocols react "
        "--ab auto-routed --tasks e2e_h06 --repeats 1 --max-cost 0.09"
    )
    registered = {c.id: c for c in M.STATIC_CALLS}
    effective = {c.id: c for c in M.EFFECTIVE_STATIC}
    row = re.search(r"^\| 재실행 RR-10 .*$", M.PREREG_TEXT, re.MULTILINE).group(0)
    row = row.replace("RR-10", "RR-01").replace("rerun-10", "rerun-01")
    assert M.load_reruns(row, registered, effective)[0].cause == "deadline-nobedrock"
    assert M.load_reruns(row, registered)[0].cause == "routing"
    with pytest.raises(M.LedgerError):
        M.load_reruns(row.replace("0.09", "0.10"), registered, effective)


def test_rr10_rerun_flow(tmp_path: Path, capsys) -> None:
    ledger = rr10_ledger(tmp_path)
    capsys.readouterr()
    assert check_call(ledger, "RR-10", plan=0.09) == 1
    assert "FAIL C11" in capsys.readouterr().out
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    assert check_call(ledger, "RR-10", plan=0.09) == 0
    out = capsys.readouterr().out
    assert "PASS C12" in out
    assert "RequestDeadlineExceeded error run" in out
    assert "PASS C14" in out
    assert "original task cap 0.090000" in out
    usage = M.fold(M.read_records(ledger)).last_usage
    assert usage is not None
    report = write_error_report(
        tmp_path / "rr-10.json", [("e2e_h06", 0, "error", DEADLINE_DETAIL, 0.02)]
    )
    rc = run(
        ledger,
        "record",
        "RR-10",
        "--status",
        "executed",
        "--usage-before",
        str(usage),
        "--usage-after",
        str(usage + 0.02),
        "--report",
        str(report),
    )
    assert rc == 0
    record = [r for r in M.read_records(ledger) if r["type"] == "call" and r["call"] == "RR-10"]
    assert record[-1]["of"] == "M19-44"
    assert record[-1]["outcome"] == "error"
    capsys.readouterr()
    assert check_call(ledger, "RR-10", plan=0.09) == 1
    assert "FAIL C13" in capsys.readouterr().out
    assert run(ledger, "panel-extras") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["reruns"][9] == {
        "id": "RR-10",
        "of": "M19-44",
        "task": "e2e_h06",
        "repeat_index": 2,
        "orig_report": ".cora/bench/m19/runs/c_s-m2-i04/report.json",
        "rerun_report": ".cora/bench/m19/runs/rerun-10/report.json",
        "status": "executed",
    }


def test_rr10_c12_needs_deadline_error(tmp_path: Path, capsys) -> None:
    ledger = rr10_ledger(tmp_path, r2_detail=ROUTING_DETAIL)
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    capsys.readouterr()
    assert check_call(ledger, "RR-10", plan=0.09) == 1
    assert "FAIL C12" in capsys.readouterr().out


def test_rr10_c14_task_cap(tmp_path: Path, capsys) -> None:
    settings = {"max_task_cost_usd": 0.08, "e2e": {"tasks": [{"id": "e2e_h06", "cost_usd": 0.09}]}}
    ledger = rr10_ledger(tmp_path, settings=settings)
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    capsys.readouterr()
    assert check_call(ledger, "RR-10", plan=0.09) == 1
    assert "FAIL C14" in capsys.readouterr().out


def test_rr10_blocked_after_b_m2(tmp_path: Path, capsys) -> None:
    ledger = rr10_ledger(tmp_path)
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    mark(ledger, "M19-45")
    assert run(ledger, "cell", "b(m2)") == 0
    capsys.readouterr()
    assert check_call(ledger, "RR-10", plan=0.09) == 1
    assert "FAIL C1" in capsys.readouterr().out


def test_live_cmd_rr10(capsys) -> None:
    assert M.main(["live-cmd", "RR-10"]) == 0
    assert capsys.readouterr().out.strip() == RR10_COMMAND


def test_amendment_validation() -> None:
    reg29 = M.STATIC_CALLS[28].command
    good = reg29.replace(" bench ", " bench -c .cora/bench/m19/deadline.toml ", 1).replace(
        "e-strong-i19", "e-i19"
    )
    row = f"| 수정 M19-29 | `{good}` |"
    assert M.apply_amendments(M.STATIC_CALLS, row)[28].amended == "수정"
    with pytest.raises(M.LedgerError):
        M.apply_amendments(M.STATIC_CALLS, f"| 수정 M19-29 | `{good.replace('0.30', '0.31')}` |")
    with pytest.raises(M.LedgerError):
        M.apply_amendments(M.STATIC_CALLS, f"{row}\n{row}")
    reg35 = M.STATIC_CALLS[34].command
    wrong = reg35.replace("cascade-strong.toml", "deadline.toml")
    with pytest.raises(M.LedgerError):
        M.apply_amendments(M.STATIC_CALLS, f"| 수정 M19-35 | `{wrong}` |")


def test_reruns_registry() -> None:
    assert len(M.RERUNS) == 10
    assert [(c.of, c.tasks[0], c.repeat_index, c.max_cost, c.plan_total) for c in M.RERUNS] == [
        ("M19-08", "e2e_h04", 0, 0.08, 0.042202),
        ("M19-08", "e2e_h05", 2, 0.08, 0.042202),
        ("M19-09", "e2e_h06", 0, 0.07, 0.035168),
        ("M19-21", "e2e_h04", 0, 0.30, 0.147302),
        ("M19-26", "e2e_h06", 0, 0.30, 0.122752),
        ("M19-43", "e2e_h04", 0, 0.10, 0.1),
        ("M19-43", "e2e_h04", 1, 0.10, 0.1),
        ("M19-43", "e2e_h04", 2, 0.10, 0.1),
        ("M19-43", "e2e_h05", 2, 0.05, 0.05),
        ("M19-44", "e2e_h06", 2, 0.09, 0.09),
    ]
    assert M.plan_command(M.get_call("RR-01")) == (
        "uv run cora bench plan -c .cora/bench/m19/deadline.toml --suite e2e "
        "--models qwen/qwen3-coder-30b-a3b-instruct --protocols react --tasks e2e_h04 "
        "--repeats 1 --max-cost 0.08"
    )
    registered = {c.id: c for c in M.STATIC_CALLS}
    row = re.search(r"^\| 재실행 RR-01 .*$", M.PREREG_TEXT, re.MULTILINE).group(0)
    with pytest.raises(M.LedgerError):
        M.load_reruns(row.replace("qwen/qwen3-coder-30b-a3b-instruct", "x/other"), registered)
    with pytest.raises(M.LedgerError):
        M.load_reruns(f"{row}\n{row.replace('RR-01', 'RR-02')}", registered)


def test_rerun_flow(tmp_path: Path, capsys) -> None:
    ledger = rerun_ledger(tmp_path)
    capsys.readouterr()
    assert check_call(ledger, "RR-01") == 1
    assert "FAIL C11" in capsys.readouterr().out
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    assert check_call(ledger, "RR-03") == 1
    assert "FAIL C1" in capsys.readouterr().out
    assert check_call(ledger, "RR-01", plan=0.042202) == 0
    capsys.readouterr()
    state = M.fold(M.read_records(ledger))
    before_total = state.m19_total
    usage = state.last_usage
    assert usage is not None
    report = write_error_report(tmp_path / "rr-01.json", [("e2e_h04", 0, "solved", "", 0.02)])
    rc = run(
        ledger,
        "record",
        "RR-01",
        "--status",
        "executed",
        "--usage-before",
        str(usage),
        "--usage-after",
        str(usage + 0.02),
        "--report",
        str(report),
    )
    assert rc == 0
    assert M.fold(M.read_records(ledger)).m19_total == pytest.approx(before_total + 0.02)
    record = [r for r in M.read_records(ledger) if r["type"] == "call" and r["call"] == "RR-01"]
    assert record[-1]["outcome"] == "solved"
    assert record[-1]["of"] == "M19-08"
    assert check_call(ledger, "RR-01") == 1
    assert "FAIL C13" in capsys.readouterr().out

    assert check_call(ledger, "RR-02") == 0
    capsys.readouterr()
    lines_before = len(M.read_records(ledger))
    two = write_error_report(
        tmp_path / "rr-02.json",
        [("e2e_h05", 2, "solved", "", 0.02), ("e2e_h05", 0, "solved", "", 0.02)],
    )
    rc = run(
        ledger,
        "record",
        "RR-02",
        "--status",
        "executed",
        "--usage-before",
        str(usage),
        "--usage-after",
        str(usage + 0.04),
        "--report",
        str(two),
    )
    assert rc == 2
    assert len(M.read_records(ledger)) == lines_before
    assert run(ledger, "mark", "RR-02", "--status", "not_measured", "--reason", "test") == 0

    execute_rows(ledger, tmp_path, "RR-03", [("e2e_h06", 0, "solved", "", 0.03)])
    e_before = M.fold(M.read_records(ledger)).e_total
    execute_rows(ledger, tmp_path, "RR-04", [("e2e_h04", 0, "solved", "", 0.10)])
    assert M.fold(M.read_records(ledger)).e_total == pytest.approx(e_before + 0.10)

    assert run(ledger, "event", "checkpoint", "--note", "after e") == 0
    capsys.readouterr()
    assert check_call(ledger, "RR-05") == 1
    assert "FAIL C1" in capsys.readouterr().out


def test_rerun_c12_original_not_deadline_error(tmp_path: Path, capsys) -> None:
    ledger = rerun_ledger(tmp_path, h04=("failed", "ProviderError: other"))
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    capsys.readouterr()
    assert check_call(ledger, "RR-01") == 1
    assert "FAIL C12" in capsys.readouterr().out


def test_table_reruns(tmp_path: Path, capsys) -> None:
    ledger = rerun_ledger(tmp_path)
    capsys.readouterr()
    assert run(ledger, "table") == 0
    first = capsys.readouterr().out
    assert run(ledger, "table") == 0
    second = capsys.readouterr().out
    assert first == second
    assert "### 호출" in first
    assert "### 재실행" in first
    assert "| RR-01 | M19-08 | a(m2) | e2e_h04 | 0 |" in first


def test_panel_extras(tmp_path: Path, capsys) -> None:
    ledger = rerun_ledger(tmp_path)
    assert run(ledger, "event", "amend", "--cell", "rerun", "--note", "test") == 0
    execute_rows(ledger, tmp_path, "RR-01", [("e2e_h04", 0, "solved", "", 0.02)])
    capsys.readouterr()
    assert run(ledger, "panel-extras") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["reruns"][0] == {
        "id": "RR-01",
        "of": "M19-08",
        "task": "e2e_h04",
        "repeat_index": 0,
        "orig_report": ".cora/bench/m19/runs/a-m2-i03/report.json",
        "rerun_report": ".cora/bench/m19/runs/rerun-01/report.json",
        "status": "executed",
    }
    assert run(ledger, "panel-extras", "--root", "tests/fixtures/m19/reports") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["reruns"][0]["orig_report"].endswith("tests/fixtures/m19/reports/a-m2-i03.json")
    assert data["reruns"][0]["rerun_report"].endswith("tests/fixtures/m19/reports/rerun-01.json")


def test_panel_extras_billed_delta(tmp_path: Path, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"
    init(ledger)
    assert run(ledger, "cell", "a(m1)") == 0
    assert check_call(ledger, "M19-01", usage=3.06) == 0
    report = write_report(tmp_path / "m01.json", 0.005)
    rc = run(
        ledger,
        "record",
        "M19-01",
        "--status",
        "executed",
        "--usage-before",
        "3.06",
        "--usage-after",
        "3.07",
        "--report",
        str(report),
    )
    assert rc == 1
    capsys.readouterr()
    assert run(ledger, "panel-extras") == 0
    data = json.loads(capsys.readouterr().out)
    entry = next(e for e in data["billed"] if e["id"] == "M19-01")
    assert entry["billed"] == pytest.approx(0.01)
    assert entry["report_cost"] == pytest.approx(0.005)


def test_live_cmd(capsys) -> None:
    assert M.main(["live-cmd", "M19-29"]) == 0
    assert capsys.readouterr().out.strip() == M.get_call("M19-29").command
    assert M.main(["live-cmd", "RR-04"]) == 0
    assert capsys.readouterr().out.strip() == (
        "uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e "
        "--models deepseek/deepseek-v3.2 --protocols react --e2e-task-cost 0.30 "
        "--tasks e2e_h04 --repeats 1 --max-cost 0.30 --out .cora/bench/m19/runs/rerun-04"
    )


def test_real_ledger_compatible(capsys) -> None:
    records = M.read_records(M.LEDGER)
    state = M.fold(records)
    assert not state.unresolved
    for n in range(1, 29):
        assert state.status[f"M19-{n:02d}"] == "executed"
    for n in range(11, 29):
        call = M.get_call(f"M19-{n:02d}")
        last = [r for r in records if r["type"] == "call" and r["call"] == call.id][-1]
        assert last["report"] == call.out + "/report.json"
        tracked = M.ROOT / f"tests/fixtures/m19/reports/e-i{n - 10:02d}.json"
        settings = json.loads(tracked.read_text(encoding="utf-8"))["settings"]
        assert settings["tasks"] == list(call.tasks)
        assert settings["max_cost_usd"] == 0.3
        assert settings["models"][0]["id"] == "deepseek/deepseek-v3.2"
    capsys.readouterr()
    assert M.main(["table"]) == 0
    capsys.readouterr()
    reports = str(M.ROOT / "tests/fixtures/m19/reports")
    assert M.main(["panel-extras", "--root", reports]) == 0
    extras = json.loads(capsys.readouterr().out)
    assert len(extras["billed"]) == sum(1 for s in state.status.values() if s == "executed")
    assert all(entry["status"] == state.status.get(entry["id"]) for entry in extras["reruns"])
    assert M.main(["panel-args", "--root", reports]) == 0
    for line in capsys.readouterr().out.strip().splitlines():
        assert Path(line.split("=", 1)[1]).exists()
