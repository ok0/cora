from __future__ import annotations

import re
from pathlib import Path

from cora.core import policy, shellguard
from cora.core.policy import (
    ALLOW_PREFIX,
    ASK_SENTENCE,
    CONFINE_ONLY,
    DEFAULT_RULES,
    RULE_HINTS,
    SHELL_ALLOW,
    STRICT_RULES,
    PolicySettings,
    Rule,
    Verdict,
    builtin_shell_allow,
    hint_for,
    load_policy,
    planning_policy,
    render_policy_rules,
)

NEUTRAL_RE = re.compile(
    r"\b(python\d*|pypy|pytest|pip|uv|node(js)?|npm|deno|bun|ruby|perl|php|lua|rscript|"
    r"javascript|typescript|java|rust|cargo|go(lang)?|bash|zsh|sh|pwsh|powershell|linux|"
    r"macos|darwin|windows|unix|posix)\b",
    re.I,
)


def _ids_in(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r'"((?:confine|floor):[A-Za-z0-9_.-]+)"', text))


def _scanned_ids() -> set[str]:
    src = Path(policy.__file__).parent
    return (_ids_in(Path(shellguard.__file__)) | _ids_in(src / "policy.py")
            | {r.id for r in DEFAULT_RULES + STRICT_RULES} | {"default"})


def _missing(hints) -> set[str]:
    return _scanned_ids() - set(hints)


def test_every_rule_id_has_hint() -> None:
    ids = _scanned_ids()
    assert ids - set(RULE_HINTS) == set()
    assert {"confine:empty", "confine:cd", "floor:network"} <= ids


def test_scan_detects_missing_hint(monkeypatch) -> None:
    monkeypatch.setattr(policy, "RULE_HINTS",
                        {k: v for k, v in RULE_HINTS.items() if k != "confine:cd"})
    assert _missing(policy.RULE_HINTS) == {"confine:cd"}


def test_scan_detects_missing_default_delete_hint(monkeypatch) -> None:
    monkeypatch.setattr(policy, "RULE_HINTS",
                        {k: v for k, v in RULE_HINTS.items() if k != "default:delete"})
    assert _missing(policy.RULE_HINTS) == {"default:delete"}


def test_hint_texts_neutral() -> None:
    for h in RULE_HINTS.values():
        assert not NEUTRAL_RE.search(h.text)
        assert not NEUTRAL_RE.search(h.remedy)


def test_hint_for_fallback() -> None:
    assert hint_for(Verdict("deny", "nope")) == hint_for(Verdict("deny", "default"))
    assert "workspace root" in hint_for(Verdict("deny", "confine:cd"))


def test_render_deterministic_and_bounded(tmp_path: Path) -> None:
    cases = [
        (PolicySettings(), "policy"),
        (PolicySettings(shell_confinement=True), "ask"),
    ]
    for settings, mode in cases:
        first = render_policy_rules(settings, approval_mode=mode, workspace=tmp_path)
        assert first == render_policy_rules(settings, approval_mode=mode, workspace=tmp_path)
        assert len(first) <= 1500
    many = PolicySettings(rules=tuple(
        Rule(f"u{i}", "allow", ("run_shell",), commands=(f"tool{i} *",), index=i)
        for i in range(300)))
    text = render_policy_rules(many, approval_mode="policy", workspace=tmp_path)
    assert text == render_policy_rules(many, approval_mode="policy", workspace=tmp_path)
    assert len(text) <= 1500
    assert "… and " in text
    assert " more" in text


def test_render_builtin_lists_all_patterns(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    text = render_policy_rules(PolicySettings(), approval_mode="policy", workspace=tmp_path)
    for pattern in builtin_shell_allow(tmp_path):
        assert pattern in text
    assert set(SHELL_ALLOW) < set(builtin_shell_allow(tmp_path))
    assert ASK_SENTENCE in text
    assert "… and" not in text


def test_render_user_file_pattern(tmp_path: Path) -> None:
    (tmp_path / ".cora").mkdir()
    (tmp_path / ".cora" / "policy.toml").write_text(
        '[[rules]]\nid = "mk"\ndecision = "allow"\ntool = "run_shell"\ncommand = "make test"\n',
        encoding="utf-8")
    s = load_policy(PolicySettings(), tmp_path)
    assert "make test" in render_policy_rules(s, approval_mode="policy", workspace=tmp_path)


def test_render_confine_mode(tmp_path: Path) -> None:
    text = render_policy_rules(
        PolicySettings(shell_confinement=True), approval_mode="ask", workspace=tmp_path
    )
    assert text.startswith(CONFINE_ONLY)
    assert ASK_SENTENCE not in text
    assert "Network access is denied." not in text
    assert ALLOW_PREFIX not in text


def test_gate_verdict_matches_check_without_tally(tmp_path: Path) -> None:
    gate = policy.PolicyGate(PolicySettings(shell_confinement=True), tmp_path)
    for command in ["ls", "cd src && ls", "python -c 'x'", "test -f a", ""]:
        for mode in ["policy", "ask"]:
            before = gate.tally.total
            v = gate.verdict("run_shell", {"command": command}, mode)
            assert gate.tally.total == before
            c = gate.check("run_shell", {"command": command}, mode)
            assert v == c
            assert gate.tally.total == before + 1


def test_planning_policy_none_without_gate(tmp_path: Path) -> None:
    assert planning_policy(PolicySettings(), tmp_path, "ask") is None
    assert planning_policy(PolicySettings(), tmp_path, "policy") is not None
    pol = planning_policy(PolicySettings(shell_confinement=True), tmp_path, "ask")
    assert pol is not None
    assert pol.verdict("cd x").blocked
