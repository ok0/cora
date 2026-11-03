from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import m20_trial
import m25_diag
import m25_planq
from cora.core.config import find_model, load_config
from m20_trial import ROOT

FIX = ROOT / "tests/fixtures/m25"
DEEPSEEK = "deepseek/deepseek-v3.2"
FREE = m25_planq.FREE_MODEL
FAKE_KEY = "fake-test-key-value-000"
ACCOUNT_KEYS = {
    "ts",
    "segment",
    "when",
    "key_usage",
    "key_limit",
    "key_limit_remaining",
    "key_expires_at",
    "total_credits",
    "total_usage",
}


class FakeRunner:
    def __init__(self, outcomes, on_call=None):
        self.outcomes = list(outcomes)
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.on_call = on_call

    def __call__(self, argv, env):
        self.calls.append((list(argv), dict(env)))
        if self.on_call is not None:
            self.on_call(env)
        return self.outcomes.pop(0)


def _config(tmp_path: Path, name: str, *args: str) -> Path:
    out = tmp_path / name
    assert m25_planq.main(["config", str(out), *args]) == 0
    return out


def _paid_config(tmp_path: Path, name: str = "paid.toml", *extra: str) -> Path:
    return _config(tmp_path, name, "--model", DEEPSEEK, "--paid", "--deadline", *extra)


def _priced_config(tmp_path: Path) -> Path:
    cfg = _paid_config(tmp_path, "priced.toml")
    text = cfg.read_text(encoding="utf-8")
    assert text.count("output_usd_per_mtok = 0.42") >= 1
    cfg.write_text(text.replace("output_usd_per_mtok = 0.42", "output_usd_per_mtok = 4.2", 1))
    assert find_model(load_config(cfg).models, DEEPSEEK).output_usd_per_mtok == 4.2
    return cfg


def _run_args(tmp_path: Path, cfg: Path, *extra: str) -> list[str]:
    return [
        "run",
        "e2e_h01",
        "--label",
        "deepseek-fix4-off",
        "--config",
        str(cfg),
        "--root",
        str(tmp_path / "root"),
        "--planq-out",
        str(tmp_path / "planq.jsonl"),
        "--fixtures",
        str(tmp_path / "fx"),
        *extra,
    ]


def _paid_args(tmp_path: Path, cfg: Path) -> list[str]:
    return _run_args(tmp_path, cfg, "--paid", "--attempts", "1", "--max-cost", "0.05")


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.mark.parametrize(
    "text", ["HTTP 429 Too Many Requests", "RESOURCE_EXHAUSTED", "rate limit exceeded"]
)
def test_plan_error_re_429(text):
    assert m20_trial.PLAN_ERROR_RE.search(text)


def test_plan_error_re_ignores_invalid_json():
    assert m20_trial.PLAN_ERROR_RE.search("model reply is not valid JSON") is None


def test_planq_row_429_is_blocked(tmp_path):
    outcome = {"ok": False, "errors": ["HTTP 429 Too Many Requests"]}
    row = m20_trial.planq_row(
        "e2e_h01", outcome, tmp_path / "plan.toml", tmp_path / "records", "x", tmp_path / "c.toml"
    )
    assert row["plan_quality"] == "blocked"


def test_config_paid_requires_flag(tmp_path):
    out = tmp_path / "out.toml"
    assert m25_planq.main(["config", str(out), "--model", DEEPSEEK]) == 2
    assert not out.exists()
    paid = _paid_config(tmp_path, "paid.toml")
    cfg = load_config(paid)
    prov = cfg.providers["openrouter"]
    assert prov["timeout_s"] == 300
    assert prov["request_deadline_s"] == 300
    assert cfg.agent.call_timeout_s == 960
    assert cfg.project.goal_paths is False
    assert cfg.project.plan_repair_hint is False
    assert cfg.agent.tripwire_per_response is False
    assert m25_planq.main(["config", str(tmp_path / "g.toml"), "--model", FREE, "--paid"]) == 2
    assert not (tmp_path / "g.toml").exists()


def test_estimate_within_cap(tmp_path, capsys):
    off = _paid_config(tmp_path, "off.toml")
    capsys.readouterr()
    assert m25_planq.main(["estimate", "--config", str(off), "--tasks", "e2e_h01,e2e_h05"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert all(v["calls"] == 3 for v in doc["per_task"].values())
    assert doc["segment_worst_usd"] <= 0.05
    on = _paid_config(tmp_path, "on.toml", "--on", "goal_paths,plan_repair_hint")
    capsys.readouterr()
    out = tmp_path / "est.jsonl"
    assert (
        m25_planq.main(
            ["estimate", "--config", str(on), "--tasks", "e2e_h01,e2e_h05", "--out", str(out)]
        )
        == 0
    )
    doc_on = json.loads(capsys.readouterr().out)
    assert all(v["calls"] == 3 for v in doc_on["per_task"].values())
    assert doc_on["segment_worst_usd"] <= 0.05
    assert len(_rows(out)) == 1


def test_estimate_over_cap_exits_2(tmp_path, capsys):
    priced = _priced_config(tmp_path)
    capsys.readouterr()
    assert m25_planq.main(["estimate", "--config", str(priced), "--tasks", "e2e_h01"]) == 2
    doc = json.loads(capsys.readouterr().out)
    assert doc["segment_worst_usd"] > m25_planq.PAID_CAP_SEGMENT_USD


@pytest.mark.parametrize(
    "case",
    [
        "no_key",
        "task",
        "label",
        "max_cost_missing",
        "max_cost_zero",
        "max_cost_too_big",
        "repeat",
        "attempts",
        "gemini_with_paid",
        "deepseek_without_paid",
    ],
)
def test_run_paid_guards(tmp_path, monkeypatch, case):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    paid = _paid_config(tmp_path)
    free = _config(tmp_path, "free.toml")
    args = _paid_args(tmp_path, paid)
    if case == "no_key":
        monkeypatch.delenv("OPENROUTER_API_KEY")
    elif case == "task":
        args[1] = "e2e_h02"
    elif case == "label":
        args[args.index("--label") + 1] = "x"
    elif case == "max_cost_missing":
        i = args.index("--max-cost")
        del args[i : i + 2]
    elif case == "max_cost_zero":
        args[args.index("--max-cost") + 1] = "0"
    elif case == "max_cost_too_big":
        args[args.index("--max-cost") + 1] = "0.06"
    elif case == "repeat":
        args += ["--repeat", "2"]
    elif case == "attempts":
        args += ["--attempts", "2"]
    elif case == "gemini_with_paid":
        args[args.index("--config") + 1] = str(free)
    elif case == "deepseek_without_paid":
        args = [a for a in args if a not in ("--paid", "--max-cost", "0.05")]
        args[args.index("--config") + 1] = str(paid)
    runner = FakeRunner([])
    assert m25_planq.main(args, runner=runner, sleep=lambda s: None) == 2
    assert runner.calls == []


def test_run_paid_env_and_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    paid = _paid_config(tmp_path)
    runner = FakeRunner(
        [{"ok": False, "errors": ["planner reply invalid after one repair attempt: x"]}]
    )
    assert m25_planq.main(_paid_args(tmp_path, paid), runner=runner, sleep=lambda s: None) == 0
    argv, env = runner.calls[0]
    assert env["OPENROUTER_API_KEY"] == FAKE_KEY
    assert tuple(argv[:5]) == m25_planq.PLANNING_ARGV
    assert FAKE_KEY not in " ".join(argv)


def test_run_free_env_has_no_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    free = _config(tmp_path, "free.toml")
    runner = FakeRunner(
        [{"ok": False, "errors": ["planner reply invalid after one repair attempt: x"]}]
    )
    assert m25_planq.main(_run_args(tmp_path, free), runner=runner, sleep=lambda s: None) == 0
    argv, env = runner.calls[0]
    assert "OPENROUTER_API_KEY" not in env
    assert tuple(argv[:5]) == m25_planq.PLANNING_ARGV


def test_run_paid_budget_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    paid = _paid_config(tmp_path)
    planq = tmp_path / "planq.jsonl"
    planq.write_text(json.dumps({"label": "deepseek-fix4-off", "cost_usd": 0.049}) + "\n")
    runner = FakeRunner([])
    assert m25_planq.main(_paid_args(tmp_path, paid), runner=runner, sleep=lambda s: None) == 3
    assert runner.calls == []


@pytest.mark.parametrize(
    ("error", "code", "quality"),
    [
        ("HTTP 402 Payment Required", 5, "blocked"),
        ("HTTP 503 UNAVAILABLE", 4, "blocked"),
        ("planner reply invalid after one repair attempt: x", 0, "invalid"),
    ],
)
def test_run_paid_error_stops(tmp_path, monkeypatch, error, code, quality):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    paid = _paid_config(tmp_path)
    runner = FakeRunner([{"ok": False, "errors": [error]}])
    sleeps: list[float] = []
    rc = m25_planq.main(_paid_args(tmp_path, paid), runner=runner, sleep=sleeps.append)
    assert rc == code
    assert len(runner.calls) == 1
    assert sleeps == []
    assert _rows(tmp_path / "planq.jsonl")[-1]["plan_quality"] == quality


def test_account_fields_only(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    paid = _paid_config(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("Authorization")
        if request.url.path.endswith("/credits"):
            data = {"total_credits": 20, "total_usage": 11.5, "extra": auth}
        else:
            data = {
                "usage": 1.5,
                "limit": 10,
                "limit_remaining": 8.5,
                "expires_at": "2026-12-01T00:00:00Z",
                "label": auth,
            }
        return httpx.Response(200, json={"data": data, "echo": auth})

    out = tmp_path / "acct.jsonl"
    rc = m25_planq.main(
        [
            "account",
            "--config",
            str(paid),
            "--segment",
            "S1",
            "--when",
            "before",
            "--out",
            str(out),
        ],
        transport=httpx.MockTransport(handler),
    )
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    rows = _rows(out)
    assert len(rows) == 1
    assert set(rows[0]) == ACCOUNT_KEYS
    assert FAKE_KEY not in text
    assert "Bearer" not in text


def test_run_key_scan_deletes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    paid = _paid_config(tmp_path)

    def write_record(env):
        rec = Path(env["CORA_RECORD_DIR"]) / "call.json"
        rec.parent.mkdir(parents=True, exist_ok=True)
        rec.write_text(
            json.dumps({"request": {"messages": []}, "response": {"text": FAKE_KEY}}),
            encoding="utf-8",
        )

    runner = FakeRunner(
        [{"ok": False, "errors": ["planner reply invalid after one repair attempt: x"]}],
        on_call=write_record,
    )
    rc = m25_planq.main(_paid_args(tmp_path, paid), runner=runner, sleep=lambda s: None)
    assert rc == 6
    assert not (tmp_path / "fx" / "e2e_h01-0" / "records" / "call.json").exists()
    assert FAKE_KEY not in capsys.readouterr().out


def test_config_on_flips(tmp_path):
    out = _config(tmp_path, "out.toml", "--on", "goal_paths,plan_repair_hint")
    cfg = load_config(out)
    assert cfg.project.goal_paths is True
    assert cfg.project.plan_repair_hint is True
    assert cfg.agent.tripwire_per_response is False
    base = tmp_path / "base.toml"
    m20_trial.make_config(FREE, base)
    base_lines = base.read_text(encoding="utf-8").splitlines()
    out_lines = out.read_text(encoding="utf-8").splitlines()
    assert len(base_lines) == len(out_lines)
    changed = [(b, o) for b, o in zip(base_lines, out_lines, strict=True) if b != o]
    assert len(changed) == 2
    assert all(" = false" in b and " = true" in o for b, o in changed)
    assert [o.split(" = ")[0] for _, o in changed] == ["goal_paths", "plan_repair_hint"]


def test_run_retry_backoff(tmp_path):
    free = _config(tmp_path, "free.toml")
    limited = {"ok": False, "errors": ["HTTP 429 Too Many Requests"]}
    runner = FakeRunner(
        [
            limited,
            limited,
            {"ok": False, "errors": ["planner reply invalid after one repair attempt: x"]},
        ]
    )
    sleeps: list[float] = []
    rc = m25_planq.main(
        _run_args(tmp_path, free, "--attempts", "5"), runner=runner, sleep=sleeps.append
    )
    assert rc == 0
    assert len(runner.calls) == 3
    assert sleeps == [60, 120]
    assert len(_rows(tmp_path / "planq.jsonl")) == 1
    assert len(_rows(tmp_path / "root" / "attempts.jsonl")) == 3


def test_run_all_blocked(tmp_path):
    free = _config(tmp_path, "free.toml")
    limited = {"ok": False, "errors": ["HTTP 429 Too Many Requests"]}
    runner = FakeRunner([limited, limited, limited])
    sleeps: list[float] = []
    rc = m25_planq.main(
        _run_args(tmp_path, free, "--attempts", "3"), runner=runner, sleep=sleeps.append
    )
    assert rc == 0
    assert len(runner.calls) == 3
    assert sleeps == [60, 120]
    row = _rows(tmp_path / "planq.jsonl")[-1]
    assert row["plan_quality"] == "blocked"
    assert row["attempts"] == 3


def test_replay_rows(tmp_path):
    out = tmp_path / "replay.jsonl"
    assert m25_diag.replay(out) == 0
    rows = _rows(out)
    refcheck = _rows(FIX / "refcheck.jsonl")
    assert len(rows) == len({r["plan"] for r in refcheck})
    for r in rows:
        assert r["flagged_failing"] + r["failing_unflagged"] == len(r["failing"])
    assert sum(r["failing_unflagged"] for r in rows) == 1
    assert sum(r["flagged_passing"] for r in rows) == 0
    assert sum(r["policy_flagged"] for r in rows) >= 114
    assert rows == _rows(FIX / "replay.jsonl")


OUTSIDE_PLAN = (
    'goal = "g"\n\n[[milestones]]\nid = "m1"\ntitle = "t"\ntask = "do it"\n'
    'conditions = [\n  { kind = "file_exists", path = "nope.txt" },\n]\n'
)


def test_refcheck_details_plan_outside_root(tmp_path):
    plan = tmp_path / "e2e_h01-0" / "plan.toml"
    plan.parent.mkdir()
    plan.write_text(OUTSIDE_PLAN, encoding="utf-8")
    rows = m25_diag.refcheck_details("e2e_h01", plan, m25_diag.CONFIG)
    assert rows
    assert {r["plan"] for r in rows} == {"e2e_h01-0/plan.toml"}
    assert str(tmp_path) not in json.dumps(rows)


def test_run_outside_root_refcheck_rows_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    free = _config(tmp_path, "free.toml")

    def write_plan(argv, env):
        out = Path(argv[argv.index("-o") + 1])
        out.write_text(OUTSIDE_PLAN, encoding="utf-8")
        return {"ok": True, "exit_code": 0, "errors": []}

    rc = m25_planq.main(_run_args(tmp_path, free), runner=write_plan, sleep=lambda s: None)
    assert rc == 0
    dest = tmp_path / "fx" / "e2e_h01-0"
    text = (dest / "refcheck.jsonl").read_text(encoding="utf-8")
    rows = _rows(dest / "refcheck.jsonl")
    assert rows
    assert {r["plan"] for r in rows} == {"e2e_h01-0/plan.toml"}
    assert str(tmp_path) not in text
    assert "/var/folders/" not in text and "/private/var/" not in text
