from __future__ import annotations

import asyncio
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from conftest import CFG_TOML, ScriptedProvider, act
from cora.core import prompts
from cora.core.agent import Agent
from cora.core.config import ConfigError, CoraConfig, load_config, parse_config
from cora.core.policy import PolicySettings, load_policy, render_policy_rules
from cora.core.tools import ApprovalPolicy
from test_headless import base, run_cli, write_cfg

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "m20b_off_prompts.json"
MODELS = [
    {
        "id": "mock/cheap",
        "provider": "scripted",
        "tier": "cheap",
        "input_usd_per_mtok": 1.0,
        "output_usd_per_mtok": 2.0,
    },
    {
        "id": "mock/strong",
        "provider": "scripted",
        "tier": "strong",
        "input_usd_per_mtok": 5.0,
        "output_usd_per_mtok": 10.0,
    },
]


def _config(approval: str, policy: dict | None) -> CoraConfig:
    return parse_config(
        {
            "models": MODELS,
            "agent": {"approval": approval},
            "delegation": {"enabled": True},
            **({"policy": policy} if policy is not None else {}),
        }
    )


def capture(root: Path, approval: str = "policy", policy: dict | None = None) -> list[str]:
    ScriptedProvider.script.clear()
    ScriptedProvider.calls.clear()
    ws = root / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    ScriptedProvider.script[:] = [
        act("delegate", {"task": "list the files"}),
        act("list_files", {}),
        "Final Answer: s",
        "Final Answer: m",
    ]
    asyncio.run(Agent(_config(approval, policy), ws, ApprovalPolicy(approval)).run("main task"))

    def norm(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        text = text.replace(sys.executable, "<PYTHON>")
        for token in (str(ws.resolve()), str(ws), str(root)):
            text = text.replace(token, "<WS>")
        return text

    return [
        norm(ScriptedProvider.calls[0].messages[0].content),
        norm(ScriptedProvider.calls[1].messages[0].content),
    ]


def test_off_prompts_match_pinned(tmp_path):
    assert capture(tmp_path) == json.loads(FIXTURE.read_text("utf-8"))


def test_explicit_false_matches_pinned(tmp_path):
    result = capture(tmp_path, policy={"prompt_rules": False})
    assert result == json.loads(FIXTURE.read_text("utf-8"))


def test_on_appends_rendered_rules(tmp_path):
    pinned = json.loads(FIXTURE.read_text("utf-8"))
    on = capture(tmp_path, policy={"prompt_rules": True})
    rules = render_policy_rules(PolicySettings(), approval_mode="policy", workspace=tmp_path / "ws")
    for i in (0, 1):
        assert on[i] == pinned[i] + prompts.POLICY_RULES_HEADER + rules
        assert on[i].endswith(rules)


def test_on_uses_user_policy_file(tmp_path):
    ws = tmp_path / "ws"
    (ws / ".cora").mkdir(parents=True)
    (ws / ".cora" / "policy.toml").write_text(
        '[[rules]]\nid = "allow-make"\ndecision = "allow"\n'
        'tool = "run_shell"\ncommand = "make *"\n',
        encoding="utf-8",
    )
    on = capture(tmp_path, policy={"prompt_rules": True})
    rules = render_policy_rules(
        load_policy(PolicySettings(), ws), approval_mode="policy", workspace=ws
    )
    assert "make *" in rules
    for prompt in on:
        assert prompt.endswith(rules)


def test_on_without_gate_unchanged(tmp_path):
    on = capture(tmp_path / "a", approval="auto", policy={"prompt_rules": True})
    off = capture(tmp_path / "b", approval="auto")
    assert on == off


def test_prompt_rules_default_and_parse():
    assert parse_config({"models": MODELS}).policy.prompt_rules is False
    off = parse_config({"models": MODELS, "policy": {"prompt_rules": False}})
    assert off.policy == PolicySettings()
    on = parse_config({"models": MODELS, "policy": {"prompt_rules": True}})
    assert on.policy.prompt_rules is True
    assert on.policy.source == "builtin"
    assert load_config(ROOT / "cora.toml").policy == PolicySettings()


@pytest.mark.parametrize("bad", ["yes", 1])
def test_prompt_rules_invalid_raises(bad):
    with pytest.raises(ConfigError, match="prompt_rules"):
        parse_config({"models": MODELS, "policy": {"prompt_rules": bad}})


def test_prompt_rules_unknown_key_raises():
    with pytest.raises(ConfigError, match="unknown keys"):
        parse_config({"models": MODELS, "policy": {"prompt_rule": True}})


def test_prompt_rules_invalid_exit_2(ws, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML + '\n[policy]\nprompt_rules = "yes"\n')
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    assert result.exit_code == 2
    assert "prompt_rules" in result.stdout


def test_unknown_policy_key_exit_2(ws, tmp_path):
    cfg = write_cfg(tmp_path, CFG_TOML + "\n[policy]\nprompt_rule = true\n")
    result = run_cli(["run", "q", "--headless", "--json", *base(ws, cfg)])
    assert result.exit_code == 2


def test_user_policy_file_rejects_prompt_rules(tmp_path):
    (tmp_path / ".cora").mkdir(parents=True)
    (tmp_path / ".cora" / "policy.toml").write_text("prompt_rules = true\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_policy(PolicySettings(), tmp_path)


def test_toml_copies_prompt_rules_false():
    root_copy = ROOT / "cora.toml"
    data_copy = ROOT / "src" / "cora" / "data" / "cora.toml"
    root_text = root_copy.read_text(encoding="utf-8")
    assert data_copy.read_text(encoding="utf-8") == root_text
    assert re.search(r"^prompt_rules = false", root_text, re.M)
    assert load_config(root_copy).policy.prompt_rules is False
    assert load_config(data_copy).policy.prompt_rules is False


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        result = capture(Path(tmp))
    FIXTURE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
