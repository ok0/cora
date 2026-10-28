from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m20_trial  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "m20d"
ART = FIX / "artifacts" / "m20d-deepseek-v2"
RUNS = FIX / "runs.jsonl"
EXTRACT = FIX / "extract.jsonl"
N08_RUNS = ("e2e_n08-r0", "e2e_n08-r1", "e2e_n08-r2")
H03_RUNS = ("e2e_h03-r0", "e2e_h03-r1")


def _outcome(name: str) -> dict:
    return json.loads((ART / name / "outcome.json").read_text(encoding="utf-8"))


def _planning(name: str) -> dict:
    out = _outcome(name)
    cp = m20_trial.cora_dir(ART / name) / "projects" / str(out["run_id"]) / "checkpoint.json"
    return (json.loads(cp.read_text(encoding="utf-8")).get("planning") or {}) if cp.exists() else {}


def _read_rows(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_extract_reproduces_saved_rows():
    rows = _read_rows(RUNS)
    saved = _read_rows(EXTRACT)
    assert len(rows) == len(saved) == 5
    for r, saved_row in zip(rows, saved, strict=True):
        got = m20_trial.extract_row(r, ART / f"{r['task']}-r{r['run']}")
        assert list(got)[: len(saved_row)] == list(saved_row)
        for k in saved_row:
            if k != "cap_bound":
                assert got[k] == saved_row[k], k
        assert got["cap_bound_m20d"] == saved_row["cap_bound"]


def test_extract_cli(capsys):
    rc = m20_trial.main(["extract", "--rows", str(RUNS), "--runs-root", str(ART)])
    assert rc == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.strip()]
    expected = [
        m20_trial.extract_row(r, ART / f"{r['task']}-r{r['run']}") for r in _read_rows(RUNS)
    ]
    assert lines == expected


def test_plan_quality_parse_repair_only():
    for name in m20_trial.M20D_RUNS:
        outcome = _outcome(name)
        planning = _planning(name)
        errors = list(outcome.get("errors") or [])
        assert planning.get("calls") == 1, name
        assert (planning.get("policy") or {}).get("rounds") in (None, 0), name
        old = {1: "first_try", 2: "after_repair"}.get(planning["calls"])
        assert m20_trial.plan_quality_of(planning, errors) == "first_try", name
        assert old == "first_try", name
    assert m20_trial.plan_quality_of({"calls": 2, "policy": {"rounds": 1}}, []) == "first_try"
    assert m20_trial.plan_quality_of({"calls": 3, "policy": {"rounds": 1}}, []) == "after_repair"
    assert m20_trial.plan_quality_of({"calls": 2}, []) == "after_repair"
    assert m20_trial.plan_quality_of({"calls": 1}, ["planner reply invalid: x"]) == "failed"
    assert m20_trial.plan_quality_of({}, []) is None


def test_policy_columns_match_fixtures():
    for name in m20_trial.M20D_RUNS:
        outcome = _outcome(name)
        planning = _planning(name)
        cdir = m20_trial.cora_dir(ART / name)
        events = m20_trial.project_events(cdir, outcome.get("run_id"))
        evs = [e for e in events if e.get("type") == "plan_policy"]
        assert len(evs) == 1, name
        ev = evs[0]
        expected = {
            "policy_dropped": ev["dropped"],
            "policy_rounds": ev["rounds"],
            "ungated": outcome["ungated_milestones"],
        }
        assert m20_trial.policy_columns(outcome, planning) == expected, name
        assert expected == {"policy_dropped": 0, "policy_rounds": 0, "ungated": []}, name


def test_cap_columns():
    h03 = _outcome("e2e_h03-r0")
    assert m20_trial.cap_columns(h03) == {"cap_tripped": "tool_calls", "cap_bound": True}
    assert m20_trial.cap_columns(_outcome("e2e_h03-r1")) == {
        "cap_tripped": "tool_calls",
        "cap_bound": True,
    }
    for name in N08_RUNS:
        assert m20_trial.cap_columns(_outcome(name)) == {"cap_tripped": None, "cap_bound": False}
    assert m20_trial.cap_columns({**h03, "stop_reason": "final_answer"})["cap_bound"] is False
    assert (
        m20_trial.cap_columns({**h03, "budget": {**h03["budget"], "tripped": None}})["cap_bound"]
        is False
    )


def test_gate_columns_fixtures():
    expected = {
        "e2e_n08-r0": (True, False, False, ["m5"]),
        "e2e_n08-r1": (True, False, False, ["final_validation"]),
        "e2e_n08-r2": (True, False, False, ["normalize_email"]),
        "e2e_h03-r0": (True, False, False, ["m7"]),
        "e2e_h03-r1": (False, False, False, []),
    }
    for name, want in expected.items():
        outcome = _outcome(name)
        cdir = m20_trial.cora_dir(ART / name)
        events = m20_trial.project_events(cdir, outcome.get("run_id"))
        got = m20_trial.gate_columns(outcome.get("milestones") or [], events)
        assert (
            got["gate_failed"],
            got["gate_failed_any"],
            got["gate_failed_final"],
            got["gate_unrun"],
        ) == want, name


def test_gate_columns_synthetic():
    milestones = [{"id": "a", "gate": {"attempts": 2, "passed": True}}]
    events = [
        {"type": "gate", "id": "a", "passed": False},
        {"type": "gate", "id": "a", "passed": True},
    ]
    got = m20_trial.gate_columns(milestones, events)
    assert got["gate_failed_any"] is True
    assert got["gate_failed_final"] is False
    assert got["gate_failed"] is False
    final = m20_trial.gate_columns([{"id": "a", "gate": {"attempts": 3, "passed": False}}], [])
    assert final["gate_failed_final"] is True


def test_run_row_new_columns(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(m20_trial, "OUT_ROOT", tmp_path / "out")
    (tmp_path / "w").mkdir()
    ws = m20_trial.prepare("e2e_h03", tmp_path / "w")
    shutil.copytree(ART / "e2e_h03-r0" / "projects", ws / ".cora" / "projects", dirs_exist_ok=True)
    outcome = _outcome("e2e_h03-r0")
    row = m20_trial.run_row("e2e_h03", ws, outcome, m20_trial.M20D_LABEL, 0, 0)
    assert row["plan_quality"] == "first_try"
    assert row["policy_dropped"] == 0
    assert row["policy_rounds"] == 0
    assert row["ungated"] == []
    assert row["cap_tripped"] == "tool_calls"
    assert row["cap_bound"] is True
    assert row["gate_failed"] is True
    assert row["gate_failed_any"] is False
    assert row["gate_failed_final"] is False
    assert row["gate_unrun"] == ["m7"]


def test_summary_m20d_label(tmp_path, capsys):
    bench = (ROOT / ".docs/bench-results.md").read_text(encoding="utf-8")
    start = bench.index("## M20d 결과 (")
    nxt = bench.find("\n## ", start + 1)
    section = bench[start : nxt if nxt != -1 else len(bench)]
    block = section[section.index("### (2) Per-run (deepseek-v2)") :]
    block = block[: block.index("```", 1)]
    note = m20_trial.RUN_LABEL_NOTES["deepseek-v2"]
    lines = [ln for ln in block.rstrip().splitlines() if ln.strip() != note]
    expected = "\n".join(lines).replace("(deepseek-v2)", "(m20d-deepseek-v2)").rstrip("\n")
    rows = _read_rows(RUNS)
    baseline = ROOT / ".docs/baselines/claude-code-m19.toml"
    out = m20_trial.summary([], rows, baseline, run_labels=[m20_trial.M20D_LABEL])
    assert out[out.index("### (2)") :].rstrip("\n") == expected
    out_none = m20_trial.summary([], rows, baseline, run_labels=None)
    assert out_none == out
    planq = tmp_path / "planq.jsonl"
    planq.write_text("", encoding="utf-8")
    rc = m20_trial.main(
        [
            "summary",
            "--planq",
            str(planq),
            "--runs",
            str(RUNS),
            "--baseline",
            str(baseline),
            "--run-label",
            m20_trial.M20D_LABEL,
        ]
    )
    assert rc == 0
    cli_out = capsys.readouterr().out
    assert cli_out[cli_out.index("### (2)") :].rstrip("\n") == expected


def test_summary_m20_unchanged():
    m20 = ROOT / "tests/fixtures/m20"
    planq = _read_rows(m20 / "planq.jsonl")
    runs = _read_rows(m20 / "runs.jsonl")
    checks = _read_rows(m20 / "checks.jsonl")
    baseline = ROOT / ".docs/baselines/claude-code-m19.toml"
    base = m20_trial.summary(planq, runs, baseline, checks_rows=checks)
    labeled = m20_trial.summary(
        planq, runs, baseline, checks_rows=checks, run_labels=["deepseek", "deepseek-v2"]
    )
    assert base == labeled


def test_deny_table_matches_outcome():
    for name in N08_RUNS:
        outcome = _outcome(name)
        rows = m20_trial.deny_table(ART / name)
        assert sum(r["decision"] == "deny" for r in rows) == outcome["policy"]["deny"], name
        assert (
            sum(r["decision"] != "deny" for r in rows) == outcome["policy"]["ask_resolved_deny"]
        ), name


def test_n08_stops_are_tripwire():
    for name in N08_RUNS:
        rows = m20_trial.stop_rows(ART / name)
        assert len(rows) >= 2, name
        trip, stop = rows[-2], rows[-1]
        assert trip["type"] == "tripwire" and trip["action"] == "stop" and trip["count"] == 3, name
        assert stop["type"] == "stop" and stop["reason"] == "tripwire", name
        assert _outcome(name)["stop_reason"] == "policy_blocked", name


def test_cost_check_h03():
    prices = m20_trial.model_prices(
        FIX / "artifacts/cora-m20d-deepseek-deadline.toml", "deepseek/deepseek-v3.2"
    )
    for name in H03_RUNS:
        run_dir = ART / name
        outcome = _outcome(name)
        cc = m20_trial.cost_check(run_dir, outcome, prices)
        assert abs(cc["outcome_minus_metered"]) < 1e-9, name
        n = sum(
            1
            for _, evs in m20_trial.session_logs(run_dir)
            for e in evs
            if e.get("type") == "llm_call"
        )
        assert cc["cost_sources"] == {"provider_usage": n}, name
