from __future__ import annotations

import pytest
from typer.testing import CliRunner

from conftest import COMPLEX_PROMPT, run_repl
from cora.cli.main import app
from cora.core.config import (
    ModelOverride,
    ModelSpec,
    load_user_overrides,
    resolve_config,
    save_user_overrides,
    unpriced_models,
    user_models_path,
)
from cora.core.errors import ConfigError
from cora.core.metering import CostMeter, format_summary
from cora.core.observability import read_events

STRONG_TASK = COMPLEX_PROMPT


def _out(result) -> str:
    return result.output + (result.stderr if hasattr(result, "stderr") else "")


def _events(ws) -> list[dict]:
    logs = list((ws / ".cora" / "sessions").glob("*/events.jsonl"))
    assert len(logs) == 1
    return read_events(logs[0])


def test_unpriced_meter_summary():
    meter = CostMeter()
    meter.record(ModelSpec("u/x", "p", "strong", None, None), "strong", "react", 100, 10)
    summary = meter.summary()
    assert summary["by_model"]["u/x"]["price_known"] is False
    assert summary["unknown_cost_calls"] == 1
    assert summary["total_cost_usd"] == 0.0
    assert "cost=unknown" in format_summary(summary)


def test_precedence_flag_over_user_over_default(mock_config):
    def strong(cfg):
        return next(m for m in cfg.models if m.tier == "strong")

    def cheap(cfg):
        return next(m for m in cfg.models if m.tier == "cheap")

    default_cfg = resolve_config(mock_config, {}, [])
    assert strong(default_cfg).id == "mock/strong"
    assert strong(default_cfg).source == "default"

    user = {"strong": ModelOverride("strong", "user/x")}
    user_cfg = resolve_config(mock_config, user, [])
    assert strong(user_cfg).id == "user/x"
    assert strong(user_cfg).source == "user"

    flag_cfg = resolve_config(mock_config, user, [ModelOverride("strong", "flag/y")])
    assert strong(flag_cfg).id == "flag/y"
    assert strong(flag_cfg).source == "flag"
    assert strong(flag_cfg).provider == "scripted"
    assert "flag/y" in [m.id for m in unpriced_models(flag_cfg)]
    assert cheap(flag_cfg).id == "mock/cheap"
    assert cheap(flag_cfg).source == "default"


def test_user_file_roundtrip(tmp_path):
    path = user_models_path(tmp_path)
    overrides = {"cheap": ModelOverride("cheap", 'a/"b', "openrouter", 0.5, 1.5)}
    save_user_overrides(path, overrides)
    assert load_user_overrides(path) == overrides
    save_user_overrides(path, {})
    assert not path.exists()


def test_unknown_provider_in_user_file_exit2(scripted, ws, cfg_file):
    user_models_path(ws).parent.mkdir(parents=True)
    user_models_path(ws).write_text(
        '[tiers.strong]\nid = "a/b"\nprovider = "nope"\n', encoding="utf-8"
    )
    result = CliRunner().invoke(
        app,
        ["run", "x", "-w", str(ws), "-c", str(cfg_file), "--approval", "auto"],
    )
    assert result.exit_code == 2
    assert "unknown provider 'nope'" in _out(result)


def test_override_invalid_tier_core(mock_config):
    with pytest.raises(ConfigError):
        resolve_config(mock_config, {}, [ModelOverride("medium", "a/b")])


def test_model_command_switches_persists_and_resets(scripted, ws, cfg_file):
    before = cfg_file.read_bytes()
    scripted.script[:] = ["Final Answer: ok"] * 3
    run_repl(ws, cfg_file, ["/model strong foo/bar 1,2", STRONG_TASK, "/exit"])
    assert scripted.calls[0].model == "foo/bar"
    assert 'id = "foo/bar"' in user_models_path(ws).read_text(encoding="utf-8")
    models = [e for e in _events(ws) if e["type"] == "models"]
    assert models
    assert any(
        m["tier"] == "strong" and m["id"] == "foo/bar" and m["source"] == "user"
        for m in models[0]["models"]
    )

    out = run_repl(
        ws,
        cfg_file,
        ["/status", STRONG_TASK, "/model reset", STRONG_TASK, "/exit"],
    )
    assert "foo/bar" in out
    assert scripted.calls[1].model == "foo/bar"
    assert scripted.calls[2].model == "mock/strong"
    assert not user_models_path(ws).exists()
    assert cfg_file.read_bytes() == before


def test_model_interactive_flow(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: ok"]
    out = run_repl(ws, cfg_file, ["/model", "2", "x/y", "3,4", STRONG_TASK, "/exit"])
    assert "1) cheap" in out
    assert "2) strong" in out
    assert "Known models:" in out
    assert scripted.calls[-1].model == "x/y"
    assert load_user_overrides(user_models_path(ws))["strong"].input_usd_per_mtok == 3.0


def test_model_interactive_pick_from_list(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: ok"]
    run_repl(ws, cfg_file, ["/model", "strong", "1", "", STRONG_TASK, "/exit"])
    assert scripted.calls[-1].model == "mock/cheap"


def test_model_interactive_cancel(ws, cfg_file):
    out = run_repl(ws, cfg_file, ["/model", "", "/exit"])
    assert "cancelled" in out
    assert not user_models_path(ws).exists()


def test_unpriced_model_warns_and_reports_unknown(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: ok"]
    out = run_repl(ws, cfg_file, ["/model strong foo/bar", STRONG_TASK, "/cost", "/exit"])
    assert "warning: model 'foo/bar'" in out
    assert "cost=unknown" in out
    assert "unknown_cost_calls: 1" in out


def test_model_command_errors_keep_repl(ws, cfg_file):
    out = run_repl(
        ws,
        cfg_file,
        ["/model medium x/y", "/model reset medium", "/model strong a/b 1", "/status", "/exit"],
    )
    assert out.count("invalid tier 'medium'") == 2
    assert "price must be IN,OUT" in out
    assert "workdir:" in out


def test_user_override_used_by_run(scripted, ws, cfg_file):
    scripted.script[:] = ["Final Answer: ok"]
    run_repl(ws, cfg_file, ["/model strong foo/bar 1,2", "/exit"])
    result = CliRunner().invoke(
        app,
        ["run", STRONG_TASK, "-w", str(ws), "-c", str(cfg_file), "--approval", "auto"],
    )
    assert result.exit_code == 0, _out(result)
    assert scripted.calls[-1].model == "foo/bar"
