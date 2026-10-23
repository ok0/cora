from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import typer.main

from cora.cli.main import app
from cora.cli.repl import COMMANDS

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "USAGE.md"
README = ROOT / "README.md"
LONG_OPT = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")
SHORT_OPT = re.compile(r"`(-[a-zA-Z])`")
SLASH = re.compile(r"(?<![\w./~:<>-])/([a-z][a-z-]*)")
TABLE_CMD = re.compile(r"^\|\s*`(/[a-z][a-z-]*)`")
REQUIRED = (
    "uv sync", "OPENROUTER_API_KEY", "커밋", "uv run cora", "cora -p", "cora run",
    "cora chat", "cora resume", "cora bench", "--delegate", "종료 코드", "130",
    "/tools", "/check", "tripwire", "/model", "baseline.toml", "cora.toml",
    "~/.config/cora/cora.toml", ".cora/models.toml", "[[models]]", "[agent]",
    "[tool_groups]", "[bench]", "uv run pytest", "uv run ruff check src tests",
)


def _usage() -> str:
    return USAGE.read_text(encoding="utf-8")


BENCH_V2_M1 = (
    "cora bench plan", "--repeats", "--seed", "--resume", "--trim-to-budget", "Wilson",
    "bootstrap", "low_n", "solved-per-dollar", "partial", "insufficient data",
    "difference not significant",
)


def _cli() -> dict[str, tuple[set[str], set[str]]]:
    group = typer.main.get_command(app)
    cmds: dict[str, list] = {"cora": group.params}

    def walk(prefix: str, grp) -> None:
        for n, c in grp.commands.items():
            label = f"{prefix} {n}"
            cmds[label] = c.params
            if hasattr(c, "commands"):
                walk(label, c)

    walk("cora", group)
    out: dict[str, tuple[set[str], set[str]]] = {}
    for label, params in cmds.items():
        opts = [
            o for p in params if p.param_type_name == "option"
            for o in (*p.opts, *p.secondary_opts)
        ]
        out[label] = (
            {o for o in opts if o.startswith("--")} | {"--help"},
            {o for o in opts if not o.startswith("--")},
        )
    return out


def _section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = lines.index(heading)
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith(("## ", "### ")):
            break
        body.append(line)
    return "\n".join(body)


def test_readme_stays_short_and_has_no_usage_text() -> None:
    # The README is hand-edited by the user (intro + references). Usage lives in USAGE.md.
    text = README.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[:2] == ["# CORA", "Cost-Oriented Routing Agent."]
    assert len(lines) <= 40
    assert "```" not in text


def test_usage_exists_and_not_ignored() -> None:
    assert USAGE.is_file()
    if shutil.which("git") and (ROOT / ".git").exists():
        assert subprocess.run(
            ["git", "check-ignore", "-q", "USAGE.md"], cwd=ROOT
        ).returncode == 1


def test_usage_is_korean() -> None:
    assert len(re.findall(r"[가-힣]", _usage())) >= 500


def test_usage_covers_required_topics() -> None:
    text = _usage()
    for needle in REQUIRED:
        assert needle in text, f"missing topic: {needle!r}"


def test_usage_documents_bench_v2_m1() -> None:
    text = _usage()
    for needle in BENCH_V2_M1:
        assert needle in text, f"missing bench v2 topic: {needle!r}"


BENCH_V2_M2 = (
    "cora bench compare", "baseline.example.toml", "synthetic", "SYNTHETIC", "baseline 없음",
    "solved-per-dollar ratio", "wall_s",
)


def test_usage_documents_bench_v2_m2() -> None:
    text = _usage()
    for needle in BENCH_V2_M2:
        assert needle in text, f"missing bench v2 topic: {needle!r}"


BENCH_V2_M3 = (
    "--suite", "e2e", "task.toml", "grader", "reference", "human_interventions", "grader_error",
    "full_pass", "REQUIREMENTS.md",
)


def test_usage_documents_bench_v2_m3() -> None:
    text = _usage()
    for needle in BENCH_V2_M3:
        assert needle in text, f"missing bench v2 topic: {needle!r}"


PROJECT_M4 = (
    "cora project run", "cora project resume", "[[milestones]]", "checkpoint.json",
    ".cora/projects", "run_id", "milestones", "pending", "interrupted", "conditions",
)


def test_usage_documents_project_runner() -> None:
    text = _usage()
    for needle in PROJECT_M4:
        assert needle in text, f"missing project topic: {needle!r}"


def test_usage_documents_every_cli_option_per_command() -> None:
    text = _usage()
    for label, (longs, shorts) in _cli().items():
        sec = _section(text, f"### `{label}`")
        for o in longs:
            assert f"`{o}`" in sec, f"{label}: missing {o}"
        for s in shorts:
            assert f"`{s}`" in sec, f"{label}: missing {s}"
        assert set(LONG_OPT.findall(sec)) <= longs, f"{label}: unknown long option"
        assert set(SHORT_OPT.findall(sec)) <= shorts, f"{label}: unknown short option"


def test_usage_has_no_unknown_long_options() -> None:
    known = set().union(*(lg for lg, _ in _cli().values())) | {"--run-live"} | (
        {"--all"} if "/reset" in COMMANDS else set()
    ) | {"--editable", "--reinstall"}
    assert set(LONG_OPT.findall(_usage())) <= known


def test_usage_slash_table_matches_repl_commands() -> None:
    sec = _section(_usage(), "### 슬래시 명령")
    rows = [m.group(1) for ln in sec.splitlines() if (m := TABLE_CMD.match(ln))]
    assert sorted(rows) == sorted(COMMANDS)
    assert len(rows) == len(set(rows))


def test_usage_mentions_no_unknown_slash_command() -> None:
    assert {"/" + n for n in SLASH.findall(_usage())} <= set(COMMANDS)


def test_docs_contain_no_api_key_values() -> None:
    for p in (USAGE, README):
        t = p.read_text(encoding="utf-8")
        assert not re.search(r"sk-or-v1-[0-9A-Za-z]{16,}", t)
        assert not re.search(r"\bsk-[A-Za-z0-9_-]{20,}", t)
        for m in re.finditer(r"OPENROUTER_API_KEY=([^\s`]*)", t):
            assert m.group(1) in ("", "...") or m.group(1).startswith("<")
