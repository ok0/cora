from __future__ import annotations

import json
import re
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path

import m19_ledger as M
import m19_panel as P
from cora.bench.compare import load_compare_baseline

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / ".docs" / "bench-results.md"
FIXTURES = ROOT / "tests" / "fixtures" / "m19"
RESULTS = FIXTURES / "results.md"
REPORTS = FIXTURES / "reports"
BASELINE = FIXTURES / "claude-code-m19.toml"
BASELINE_DOCS = ROOT / ".docs" / "baselines" / "claude-code-m19.toml"
ARGS = FIXTURES / "panel-args.txt"
EXTRAS = FIXTURES / "panel-extras.json"
PANEL = FIXTURES / "panel.md"
PANEL_REGISTERED = FIXTURES / "panel-registered.md"
MEASURE_RE = r"^## M19 측정 \(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\)$"
AMEND_HEADING_RE = r"^## M19 사전 등록 수정 \(.*\)$"
HARD_TASKS = (
    "e2e_h01", "e2e_h02", "e2e_h03", "e2e_h04", "e2e_h05", "e2e_h06", "e2e_hx1", "e2e_hx2",
)
QWEN = "qwen/qwen3-coder-30b-a3b-instruct"
DEEPSEEK = "deepseek/deepseek-v3.2"
ORDER = [cell for cell, _ in M.CELL_ORDER]


def _section(text: str, heading_regex: str) -> str:
    match = re.search(heading_regex, text, re.M)
    assert match is not None, heading_regex
    rest = text[match.start():]
    nxt = re.search(r"^## M19", rest[1:], re.M)
    end = len(rest) if nxt is None else nxt.start() + 1
    return rest[:end].rstrip("\n")


def _block(text: str, start_regex: str, end_regex: str) -> str:
    match = re.search(start_regex, text, re.M)
    assert match is not None, start_regex
    rest = text[match.start():]
    nxt = re.search(end_regex, rest[1:], re.M)
    end = len(rest) if nxt is None else nxt.start() + 1
    return rest[:end]


def _tables(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        if line.startswith("|"):
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def _family(cell: str) -> str:
    return cell.split("(", 1)[0]


def _model_of(call: M.Call) -> str:
    match = re.search(r"--models (\S+)", call.command)
    assert match is not None, call.id
    return match.group(1)


def _values(node: object, key: str):
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key:
                yield value
            yield from _values(value, key)


def test_results_mirror_identical() -> None:
    bench = BENCH.read_text(encoding="utf-8")
    results = RESULTS.read_text(encoding="utf-8")
    assert len(re.findall(MEASURE_RE, results, re.M)) == 1
    assert _section(results, MEASURE_RE) == _section(bench, MEASURE_RE)
    headings = re.findall(AMEND_HEADING_RE, results, re.M)
    assert headings
    for heading in headings:
        pattern = r"^" + re.escape(heading) + r"$"
        assert _section(results, pattern) == _section(bench, pattern), heading
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(RESULTS)], cwd=ROOT, check=False
    )
    assert result.returncode == 1


def test_results_subsections() -> None:
    section = _section(RESULTS.read_text(encoding="utf-8"), MEASURE_RE)
    for number in range(12):
        assert re.search(rf"^### §{number}(?!\d)", section, re.M), f"§{number}"


def test_ledger_table_in_results() -> None:
    results = RESULTS.read_text(encoding="utf-8")
    measure = _section(results, MEASURE_RE)
    calls_section = _block(results, r"^### §4 ", r"^### §5 ")
    blocks = _tables(M.render_table(M.read_records(M.LEDGER)))
    assert len(blocks) == 4
    for block in blocks:
        assert block in measure
    assert blocks[0] in calls_section


def test_ledger_invariants() -> None:
    records = M.read_records(M.LEDGER)
    state = M.fold(records)
    assert state.m19_total <= M.ALLOCATION_USD + 1e-9
    assert state.paid_total is not None
    assert state.paid_total <= M.PAID_CAP_USD + 1e-9
    assert state.unresolved == []

    for index, record in enumerate(records):
        if record["type"] == "call" and record["status"] == "executed":
            call = M.BY_ID[record["call"]]
            checks = [
                r for r in records[:index] if r["type"] == "check" and r["call"] == call.id
            ]
            assert checks and checks[-1]["ok"] is True, call.id
            assert checks[-1]["plan_total"] <= call.max_cost + 1e-9, call.id
            assert call.max_cost <= M.MAX_COST_CAP_USD + 1e-9, call.id

    e_index = ORDER.index("e")
    executed_e = [
        r["call"]
        for r in records
        if r["type"] == "call" and r["cell"] == "e" and r["status"] == "executed"
    ]
    assert executed_e
    assert state.e_total <= M.E_STOP_USD + M.BY_ID[executed_e[-1]].max_cost + 1e-9
    over = False
    for index, record in enumerate(records):
        if record["type"] == "call" and record["cell"] == "e" and over:
            assert record["status"] == "not_measured", record["call"]
        if not over and M.fold(records[: index + 1]).e_total > M.E_STOP_USD:
            over = True

    cell_records = [r["cell"] for r in records if r["type"] == "cell"]
    assert cell_records == ORDER

    checkpoints = [
        i for i, r in enumerate(records) if r["type"] == "event" and r["kind"] == "checkpoint"
    ]
    assert checkpoints
    after_e = set(ORDER[e_index + 1:])
    first_after_e = next(
        i for i, r in enumerate(records) if r["type"] == "call" and r["cell"] in after_e
    )
    assert checkpoints[0] < first_after_e

    rerun_ids = {c.id for c in M.RERUNS}
    for rerun_id in rerun_ids:
        calls = [r for r in records if r["type"] == "call" and r["call"] == rerun_id]
        assert len(calls) <= 1, rerun_id
    rr_checks = [
        i for i, r in enumerate(records) if r["type"] == "check" and r["call"] in rerun_ids
    ]
    amends = [
        i for i, r in enumerate(records) if r["type"] == "event" and r["kind"] == "amend"
        and r["cell"] == "rerun"
    ]
    assert rr_checks and amends and amends[0] < rr_checks[0]
    early_cells = set(ORDER[: e_index + 1])
    for index, record in enumerate(records):
        call_id = record.get("call")
        if call_id in rerun_ids and M.BY_ID[call_id].cell in early_cells:
            assert index < checkpoints[0], call_id

    without = M.fold([r for r in records if r.get("call") not in rerun_ids])
    assert state.m19_total - without.m19_total > 0
    assert state.e_total - without.e_total > 0


def test_report_copies_and_settings() -> None:
    state = M.fold(M.read_records(M.LEDGER))
    executed = [cid for cid, status in state.status.items() if status == "executed"]
    assert executed
    for cid in executed:
        call = M.BY_ID[cid]
        path = REPORTS / f"{Path(call.out).name}.json"
        assert path.exists(), cid
        data = json.loads(path.read_text(encoding="utf-8"))
        settings = data["settings"]
        family = _family(call.cell)
        if family in ("a", "g"):
            assert settings.get("ab") is None, cid
            assert settings.get("verify_attempts") is None, cid
            assert settings["sensor"]["enabled"] is False, cid
        elif family == "e":
            assert settings["models"][0]["id"] == DEEPSEEK, cid
            assert all(task["cost_usd"] == 0.3 for task in settings["e2e"]["tasks"]), cid
        elif family == "c_s":
            assert settings["ab"]["arms"] == ["auto-routed"], cid
            assert settings["ab"]["escalation_target"] == DEEPSEEK, cid
            assert settings["sensor"]["source"] == "auto", cid
        elif family == "c_cc":
            assert settings["ab"]["escalation_target"] == QWEN, cid
        elif family == "d1":
            assert settings["ab"]["arms"] == ["deleg-on-par-on"], cid
        elif family == "b":
            assert settings["verify_attempts"] == 3, cid
        generated = datetime.fromisoformat(data["generated_at"])
        assert generated > datetime.fromisoformat("2026-10-18T08:25:28+00:00"), cid
        if cid.startswith("RR-"):
            assert len(data["results"]) == 1, cid
            result = data["results"][0]
            assert result["task"] == call.tasks[0], cid
            expected_model = (
                "auto" if settings.get("ab") and settings["ab"]["arms"] == ["auto-routed"]
                else _model_of(M.BY_ID[call.of])
            )
            assert result["model"] == expected_model, cid


def _panel_specs() -> list[str]:
    return [line for line in ARGS.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_panel_reproducible(capsys, monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    specs = _panel_specs()
    baseline = str(BASELINE.relative_to(ROOT))
    extras = str(EXTRAS.relative_to(ROOT))
    code = P.main(
        [
            *specs,
            "--baseline", baseline,
            "--thresholds", "0.70,0.40,2.0",
            "--extras", extras,
            "--error-policy", "replace",
            "--cost-basis", "billed",
            "--sensitivity",
        ]
    )
    assert code == 0
    assert capsys.readouterr().out == PANEL.read_text(encoding="utf-8")

    code = P.main([*specs, "--baseline", baseline, "--thresholds", "0.70,0.40,2.0"])
    assert code == 0
    assert capsys.readouterr().out == PANEL_REGISTERED.read_text(encoding="utf-8")

    section7 = _block(RESULTS.read_text(encoding="utf-8"), r"^### §7 ", r"^### §8 ")
    assert PANEL.read_text(encoding="utf-8").rstrip("\n") in section7
    assert PANEL_REGISTERED.read_text(encoding="utf-8").rstrip("\n") in section7


def test_baseline_file() -> None:
    baseline = load_compare_baseline(BASELINE)
    assert set(HARD_TASKS) <= set(baseline.tasks)
    assert BASELINE.read_bytes() == BASELINE_DOCS.read_bytes()


def test_p1_and_keys() -> None:
    lines = RESULTS.read_text(encoding="utf-8").split("\n")
    for mechanism in ("b", "c_s", "c_cc", "d1"):
        assert any(line.startswith(f"- P1 {mechanism}:") for line in lines), mechanism
    root_toml = ROOT / "cora.toml"
    data_toml = ROOT / "src" / "cora" / "data" / "cora.toml"
    assert root_toml.read_bytes() == data_toml.read_bytes()
    for path in (root_toml, data_toml):
        config = tomllib.loads(path.read_text(encoding="utf-8"))
        for key in ("raw_file_body", "repeat_breaker", "located_errors"):
            assert list(_values(config, key)) == [False], (path.name, key)
        assert config["memory"]["ledger"] is False, path.name


def test_no_key_material() -> None:
    for path in FIXTURES.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert re.search(r"sk-or-[A-Za-z0-9_-]{8,}", text) is None, path
