from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
README = ROOT / "README.md"
CHECKLIST = ROOT / ".docs" / "tui-checklist.md"
NEEDLES = (
    "[ui]",
    "/theme",
    "/expand",
    "Shift+Tab",
    "Ctrl+T",
    "Ctrl+L",
    "NO_COLOR",
    "### 터미널 화면",
)
TUI_NEEDLES = (
    "### TUI (전체 화면)",
    "--no-tui",
    "CORA_TUI",
    "TERM=dumb",
    "exit_summary",
    "scrollback_blocks",
    "/mouse",
    "/copy",
    "F2",
    "Ctrl+O",
    "PageUp",
    "Ctrl+End",
    "Alt+Enter",
    "Ctrl+J",
    "Ctrl+R",
    "OSC 52",
    "Shift",
    "stty sane",
    "set-clipboard",
    "uv tool install <repo 경로>",
    "uv tool install --editable <repo 경로>",
    "uv tool upgrade cora",
    "uv tool install --reinstall <repo 경로>",
    "uv tool uninstall cora",
    "uv tool update-shell",
    "which cora",
    "cora --version",
)
CHECKLIST_NEEDLES = (
    "kill -TERM",
    "kill -HUP",
    "창 닫기",
    "stty -a",
    "tmux",
    "iTerm2",
    "Terminal.app",
    "$1",
    "uv tool install",
    "/mouse",
    "/copy",
    "리사이즈",
)
CUI_TERM = re.compile(r"\bCUI\b")


def test_usage_documents_terminal_ui() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in NEEDLES:
        assert needle in text, f"USAGE.md missing {needle!r}"


def test_usage_documents_tui_and_install() -> None:
    text = USAGE.read_text(encoding="utf-8")
    for needle in TUI_NEEDLES:
        assert needle in text, f"USAGE.md missing {needle!r}"


def test_tui_checklist_exists() -> None:
    assert CHECKLIST.is_file()
    assert not (ROOT / ".docs" / "cui-checklist.md").exists()
    assert not (ROOT / ".docs" / "cui-reference.md").exists()


def test_tui_checklist_items() -> None:
    text = CHECKLIST.read_text(encoding="utf-8")
    for needle in CHECKLIST_NEEDLES:
        assert needle in text, f"tui-checklist.md missing {needle!r}"


def test_no_cui_term_in_docs() -> None:
    paths = [USAGE, README, *sorted((ROOT / ".docs").glob("*.md"))]
    paths += sorted((ROOT / "src" / "cora").rglob("*.py"))
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert CUI_TERM.search(text) is None, f"CUI found in {path}"
