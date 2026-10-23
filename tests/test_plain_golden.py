from __future__ import annotations

import re

from conftest import CFG_TOML, GATES_OFF_TOML, act, run_repl

GOLDEN = (
    "CORA - Cost-Oriented Routing Agent\nworkdir: <WS>\n"
    "models: cheap=mock/cheap  strong=mock/strong\n"
    "approval: auto\n"
    "guide: none (run /init to create CORA.md)\n"
    "Type a request, or /help for commands. Ctrl-C interrupts a turn; Ctrl-D or /exit quits.\n"
    "> No TODO items.\n"
    "> ● list_files (1 lines)\n"
    "● todo_write (2 lines)\n"
    "● edit_file a.txt (1 lines)\n"
    "done\n"
    "⎿ cheap:mock/cheap · <T> · 4 calls · <USAGE>\n"
    "> [~] a\n"
    "> --- a/a.txt\n"
    "+++ b/a.txt\n"
    "@@ -1 +1 @@\n"
    "-hello\n"
    "+bye\n"
    "> == CORA cost summary ==\n"
    "calls: 4\n"
    "model mock/cheap: calls=4 <MU>\n"
    "total_estimated_cost_usd: <TOTAL>\n"
    "session: <SID> (resume with /resume <SID>)\n"
)

LINES = ["/todo", "do it", "/todo", "/diff", "/exit"]


def _script(scripted) -> None:
    scripted.script[:] = [
        act("list_files", {}),
        act("todo_write", {"todos": [{"content": "a", "status": "in_progress"}]}),
        act("edit_file", {"path": "a.txt", "old": "hello", "new": "bye"}),
        "Final Answer: done",
    ]


def _normalize(out: str, ws) -> str:
    out = out.replace(str(ws.resolve()), "<WS>")
    rules = [
        (r"· \d+\.\d+s ·", "· <T> ·"),
        (r"\d+ in / \d+ out tokens · \$\d+\.\d+ \(session \$\d+\.\d+\)", "<USAGE>"),
        (r"in=\d+ out=\d+ cost=\$\d+\.\d+", "<MU>"),
        (r"total_estimated_cost_usd: \d+\.\d+", "total_estimated_cost_usd: <TOTAL>"),
        (r"\d{8}-\d{6}-[0-9a-f]{6}", "<SID>"),
    ]
    for pattern, repl in rules:
        out = re.sub(pattern, repl, out)
    return out


def test_plain_transcript_golden(scripted, ws, cfg_file_gates_off):
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    _script(scripted)
    out = run_repl(ws, cfg_file_gates_off, LINES)
    assert _normalize(out, ws) == GOLDEN
    assert "\x1b" not in out
    assert not any("─" <= ch <= "╿" for ch in out)
    assert len(scripted.calls) == 4


def test_ui_config_keeps_plain_output_and_calls(scripted, ws, tmp_path):
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    _script(scripted)
    cfg = tmp_path / "ui.toml"
    cfg.write_text(
        CFG_TOML + '\n[ui]\ntheme = "mono"\nascii = true\ncolor = "never"\n' + GATES_OFF_TOML,
        encoding="utf-8",
    )
    out = run_repl(ws, cfg, LINES)
    assert _normalize(out, ws) == GOLDEN
    assert len(scripted.calls) == 4
