from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cora.bench import e2e
from cora.cli.main import app
from cora.core.config import find_model, load_config
from m15_sheet import CHEAP, E2E, ENTRIES, MULTI, STRONG, Entry

ROOT = Path(__file__).resolve().parents[1]


def rehearsal_toml(tmp_path: Path) -> Path:
    lines = (ROOT / "cora.toml").read_text(encoding="utf-8").splitlines()
    rewritten = [
        'provider = "scripted"' if line == 'provider = "openrouter"' else line for line in lines
    ]
    out = tmp_path / "rehearsal.toml"
    out.write_text("\n".join(rewritten) + "\n", encoding="utf-8")
    return out


def _opt(argv: tuple[str, ...], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def _tasks(argv: tuple[str, ...]) -> list[str]:
    return _opt(argv, "--tasks").split(",")


def _is_e2e(argv: tuple[str, ...]) -> bool:
    return "--suite" in argv and _opt(argv, "--suite") == "e2e"


def _plan_argv(e: Entry) -> list[str]:
    cleaned: list[str] = []
    argv = list(e.argv)
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in ("--live", "--sensor"):
            i += 1
            continue
        if tok == "--sensor-source":
            i += 2
            continue
        if tok == "--out":
            i += 2
            continue
        cleaned.append(tok)
        i += 1
    return ["bench", "plan", *cleaned[1:], "-c", str(ROOT / "cora.toml")]


def test_sheet_entries_resolve() -> None:
    cfg = load_config(ROOT / "cora.toml")
    for e in ENTRIES:
        model_id = _opt(e.argv, "--models")
        spec = find_model(cfg.models, model_id)
        assert spec is not None, e.id
        assert spec.provider == "openrouter", e.id
        if e.tier == "strong":
            assert model_id == STRONG == spec.id, e.id
            assert spec.input_usd_per_mtok == 0.28, e.id
            assert spec.output_usd_per_mtok == 0.42, e.id
        else:
            assert model_id == CHEAP == spec.id, e.id
            assert spec.input_usd_per_mtok == 0.10, e.id
            assert spec.output_usd_per_mtok == 0.40, e.id

        assert 0 < e.max_cost <= 0.50, e.id
        assert float(_opt(e.argv, "--max-cost")) == e.max_cost, e.id

        if e.arm == "A":
            assert "--sensor" not in e.argv, e.id
            assert model_id == CHEAP, e.id
        elif e.arm == "B":
            assert "--sensor" in e.argv, e.id
            assert _opt(e.argv, "--sensor-source") == "auto", e.id
            assert model_id == CHEAP, e.id
        elif e.arm == "C":
            assert model_id == STRONG, e.id

        if e.arm == "C" and _is_e2e(e.argv):
            assert float(_opt(e.argv, "--e2e-task-cost")) == 0.1, e.id

        if e.stage == "arm":
            assert _opt(e.argv, "--repeats") == "3", e.id

    arm_entries = [e for e in ENTRIES if e.stage == "arm"]
    multi_union = {t for e in arm_entries if not _is_e2e(e.argv) for t in _tasks(e.argv)}
    e2e_union = {t for e in arm_entries if _is_e2e(e.argv) for t in _tasks(e.argv)}
    assert multi_union == set(MULTI)
    assert e2e_union == set(E2E)


def test_sheet_plan_estimates(no_network) -> None:
    for e in ENTRIES:
        result = CliRunner().invoke(app, _plan_argv(e))
        assert result.exit_code == 0, (e.id, result.output)
        assert f"total_max_usd: {e.estimate_usd:.6f}" in result.output, e.id
        assert "OVER CAP" not in result.output, e.id


@pytest.mark.slow
@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.id)
def test_rehearse_every_entry(
    entry: Entry,
    scripted,
    no_network,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = CliRunner().invoke(
        app,
        [*entry.argv, "-c", str(rehearsal_toml(tmp_path)), "-w", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output

    out = tmp_path / ".cora" / "bench" / "m15" / entry.id
    report_path = out / "report.json"
    assert report_path.is_file()
    assert (out / "report.md").is_file()
    obj = json.loads(report_path.read_text(encoding="utf-8"))
    settings = obj["settings"]
    argv = entry.argv

    assert [m["id"] for m in settings["models"]] == [_opt(argv, "--models")]
    repeats = int(_opt(argv, "--repeats")) if "--repeats" in argv else 1
    assert settings["repeats"] == repeats
    assert settings["tasks"] == _tasks(argv)
    assert (settings["suite"] == "e2e") == _is_e2e(argv)

    if entry.arm == "B":
        assert settings["sensor"]["enabled"] is True
        assert settings["sensor"]["source"] == "auto"
    else:
        assert settings["sensor"]["enabled"] is False

    if _is_e2e(argv):
        applied = {t["id"]: t["cost_usd"] for t in settings["e2e"]["tasks"]}
        if entry.arm == "C":
            assert all(v == 0.10 for v in applied.values()), entry.id
        else:
            defaults = {t.id: t.cost_usd for t in e2e.load_e2e_tasks()}
            assert applied == {tid: defaults[tid] for tid in applied}, entry.id

    results = obj["results"]
    assert len(results) == repeats * len(_tasks(argv))
    assert all(r["status"] != "error" for r in results)

    compared = CliRunner().invoke(app, ["bench", "compare", str(report_path)])
    assert compared.exit_code == 0, compared.output
