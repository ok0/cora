from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
ARCHITECTURE = ROOT / ".docs" / "architecture.md"
USAGE_NEEDLES = (
    "[policy]", ".cora/policy.toml", "--approval", "shell_confinement", "sandbox-exec",
    "policy_decision", "TOCTOU", "OS 샌드박스", "strict", "policy_denies", "python script.py",
    "~/.ssh", ".git/config",
)


def test_usage_documents_policy_mode() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in USAGE_NEEDLES:
        assert needle in text, f"missing policy topic: {needle!r}"


def test_architecture_documents_policy_layer() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "G2-8" in text
    assert "policy.py" in text


def test_cora_toml_copies_are_identical() -> None:
    assert (ROOT / "cora.toml").read_bytes() == (
        ROOT / "src" / "cora" / "data" / "cora.toml"
    ).read_bytes()
