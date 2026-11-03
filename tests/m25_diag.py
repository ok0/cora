"""M25 Step 0 diagnosis helpers (offline, $0). Editor-run; not part of the product.

Usage (repo root):
    uv run python tests/m25_diag.py inventory --dst tests/fixtures/m25
    uv run python tests/m25_diag.py refcheck --config tests/fixtures/m20/artifacts/cora-m20-deepseek.toml --out tests/fixtures/m25/refcheck.jsonl
    uv run python tests/m25_diag.py tripcheck --out tests/fixtures/m25/tripcheck.jsonl
    uv run python tests/m25_diag.py denials --out tests/fixtures/m25/denials.jsonl
    uv run python tests/m25_diag.py golden --out tests/fixtures/m25/planner_prompts_off.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))

import m20_trial  # noqa: E402
from m20a_artifacts import _sanitize  # noqa: E402
from cora.bench import e2e  # noqa: E402
from cora.core.agent import Agent  # noqa: E402
from cora.core.config import load_config  # noqa: E402
from cora.core.milestones import Condition, load_plan, run_condition  # noqa: E402
from cora.core.planner import (  # noqa: E402
    PolicyIssue,
    plan_messages,
    plan_project,
    policy_repair_messages,
    repair_messages,
    validate_plan_policy,
)
from cora.core.policy import approval_mode_of, planning_policy  # noqa: E402
from cora.core.tools import ApprovalPolicy  # noqa: E402

ROOT = m20_trial.ROOT
FIX_DIR = ROOT / "tests/fixtures/m25"
CONFIG = ROOT / "tests/fixtures/m20/artifacts/cora-m20-deepseek.toml"
M20_ARTIFACTS = ROOT / "tests/fixtures/m20/artifacts"
M20D_ARTIFACTS = ROOT / "tests/fixtures/m20d/artifacts"
M20D_RUNS = M20D_ARTIFACTS / "m20d-deepseek-v2"
REPO_M20 = ROOT / ".cora" / "m20"
TMP_M20 = Path(tempfile.gettempdir()) / "cora-m20"
OUTSIDE_SOURCES = (("repo-cora-m20", REPO_M20), ("tmp-cora-m20", TMP_M20))
SEARCH_NAMES = ("fix3", "fix3p", "e2e_n08-r2", "records")
VERDICT_FIXED_M20A = (
    "fixed (M20a validate_plan_policy; M25 regression test test_m20_planner_checks_flagged)"
)
VERDICT_FIXED_HERE_PLANNER = "fixed here (planner validation gap)"
VERDICT_TRIPWIRE = "fixed here (tripwire counts once per response; [agent] tripwire_per_response, default OFF)"
GOLDEN_GOAL = "Build a CSV report tool."
VALID_REPLY = json.dumps(
    {"goal": "g", "milestones": [{"id": "m1", "title": "t", "task": "do it"}]}
)
INVALID_REPLY = "not json"
CAUSE_ERROR = "model reply is not valid JSON: Expecting value (line 1, column 1)"


def _rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT.resolve()).as_posix()


def _task_of(run_name: str) -> str:
    return re.sub(r"-r\d+$", "", run_name)


def _pairs() -> list[tuple[str, str]]:
    pairs = {
        str(ROOT): "<REPO>",
        os.path.expanduser("~"): "<HOME>",
        tempfile.gettempdir(): "<TMP>",
    }
    return sorted(pairs.items(), key=lambda kv: len(kv[0]), reverse=True)


def clean(text: str) -> str:
    return _sanitize(text, _pairs())[0]


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(clean(text), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    body = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows)
    _write_text(path, body)


def _prepared(task_id: str) -> tuple[Path, Path]:
    tmp = Path(tempfile.mkdtemp())
    ws = e2e.prepare_workspace(m20_trial._task(task_id), tmp)
    return tmp, ws


def _cmd_output(command: str, agent: Agent) -> tuple[bool, bool, str]:
    gate = agent.ctx.gate
    verdict = (
        gate.check("run_shell", {"command": command}, approval_mode_of(agent.ctx.approval))
        if gate is not None
        else None
    )
    if verdict is not None and verdict.blocked:
        return False, False, verdict.message
    ok, out = asyncio.run(
        run_condition(Condition(kind="command", cmd=command), agent.ctx, timeout_s=60, max_chars=2000)
    )
    executable = (
        not out.startswith(("denied:", "invalid command:", "error:"))
        and "command not found" not in out
        and m20_trial.TIMEOUT_MARKER not in out
    )
    return ok, executable, out


def refcheck_details(task_id: str, plan_path: Path, config_path: Path) -> list[dict]:
    tmp, ws = _prepared(task_id)
    try:
        task = m20_trial._task(task_id)
        e2e.apply_reference(task, ws)
        cfg = load_config(config_path)
        agent = Agent(cfg, ws, ApprovalPolicy("policy"))
        plan_rel = _rel(plan_path)
        rows: list[dict] = []
        for m in load_plan(plan_path).milestones:
            for i, c in enumerate(m.conditions):
                if c.kind == "command":
                    ok, executable, out = _cmd_output(c.cmd or "", agent)
                else:
                    ok, out = asyncio.run(
                        run_condition(c, agent.ctx, timeout_s=60, max_chars=2000)
                    )
                    executable = True
                rows.append(
                    {
                        "plan": plan_rel,
                        "task": task_id,
                        "milestone": m.id,
                        "field": f"conditions[{i}]",
                        "kind": c.kind,
                        "condition": c.describe(),
                        "executable": executable,
                        "pass_ref": bool(ok),
                        "output_head": out[:300],
                    }
                )
            if m.check is not None:
                ok, executable, out = _cmd_output(m.check, agent)
                rows.append(
                    {
                        "plan": plan_rel,
                        "task": task_id,
                        "milestone": m.id,
                        "field": "check",
                        "kind": "command",
                        "condition": m.check,
                        "executable": executable,
                        "pass_ref": bool(ok),
                        "output_head": out[:300],
                    }
                )
        return rows
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def plan_files() -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for p in M20D_RUNS.glob("*/projects/*/plan.toml"):
        found.append((p, _task_of(p.parents[2].name)))
    for g in ("p1", "p1b", "p1c"):
        for p in (M20_ARTIFACTS / g).glob("*/plan.toml"):
            found.append((p, p.parent.name))
    for p in (M20_ARTIFACTS / "v2").glob("*/projects/*/plan.toml"):
        found.append((p, _task_of(p.parents[2].name)))
    return sorted(found, key=lambda pt: _rel(pt[0]))


def refcheck(config_path: Path, out: Path) -> int:
    rows: list[dict] = []
    for plan, task in plan_files():
        rows.extend(refcheck_details(task, plan, config_path))
    rows.sort(key=lambda r: (r["plan"], r["milestone"], r["field"]))
    _write_jsonl(out, rows)
    return 0


def _load_events(path: Path) -> list[tuple[int, dict]]:
    out: list[tuple[int, dict]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            out.append((n, json.loads(line)))
    return out


def _response_of(evs: list[tuple[int, dict]], line_no: int) -> int:
    resp = 0
    for n, ev in evs:
        if n >= line_no:
            break
        if ev.get("type") == "llm_call":
            resp = n
    return resp


def _event_files() -> list[Path]:
    files = [*M20_ARTIFACTS.rglob("events.jsonl"), *M20D_ARTIFACTS.rglob("events.jsonl")]
    return sorted(files, key=_rel)


def tripwire_hits() -> list[dict]:
    hits: list[dict] = []
    for path in _event_files():
        evs = _load_events(path)
        for pos, (ln, ev) in enumerate(evs):
            if ev.get("type") != "tripwire" or ev.get("action") != "stop":
                continue
            tool = ev.get("tool")
            count = int(ev["count"])
            fails = [
                (n2, e2)
                for n2, e2 in evs[:pos]
                if e2.get("type") == "tool_call" and e2.get("ok") is False and e2.get("tool") == tool
            ]
            selected = fails[-count:]
            responses = {_response_of(evs, n2) for n2, _ in selected}
            hits.append(
                {
                    "events": _rel(path),
                    "line": ln,
                    "tool": tool,
                    "count": count,
                    "responses": len(responses),
                    "same_response": len(responses) == 1,
                    "_selected": selected,
                    "_error_head": ev.get("error_head", ""),
                }
            )
    hits.sort(key=lambda h: (h["events"], h["line"]))
    return hits


def tripcheck(out: Path) -> int:
    rows = []
    for h in tripwire_hits():
        rows.append({k: v for k, v in h.items() if not k.startswith("_")})
    _write_jsonl(out, rows)
    return 0


def _run_dir_plan(events_rel: Path) -> Path:
    run_dir = events_rel.parents[2]
    found = sorted(run_dir.glob("projects/*/plan.toml"))
    if len(found) != 1:
        raise SystemExit(2)
    return found[0]


def _policy_flagged(task_id: str, plan: Path, cfg: Any, ws: Path, command: str) -> bool:
    policy = planning_policy(cfg.policy, ws, "policy")
    if policy is None:
        raise SystemExit(2)
    issues = validate_plan_policy(load_plan(plan), policy)
    return any(i.command == command for i in issues)


def _denial(id_: str, cite: str, rule: str, source: str, command: str, verdict: str, evidence: str) -> dict:
    return {
        "id": id_,
        "cite": cite,
        "rule": rule,
        "source": source,
        "command": command[:120],
        "verdict": verdict,
        "evidence": evidence,
    }


PLANNER_DENIALS = (
    ("D1", "tests/fixtures/m20/artifacts/p2/e2e_h01-r0/sessions/20261023-212556-2e6756/events.jsonl", 30),
    ("D2", "tests/fixtures/m20/artifacts/rr/e2e_h01-r2/sessions/20261025-204419-2e971a/events.jsonl", 27),
    ("D3", "tests/fixtures/m20/artifacts/v2/e2e_n08-r0/sessions/20261025-225819-9e8303/events.jsonl", 24),
    ("D4", "tests/fixtures/m20/artifacts/v2/e2e_n08-r1/sessions/20261025-225924-4737d9/events.jsonl", 40),
)
M20D_STOP = ("tests/fixtures/m20d/artifacts/m20d-deepseek-v2/e2e_n08-r2/sessions/20261028-120515-8eca84/events.jsonl", 37)


def _event_line(path: Path, n: int) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    return json.loads(lines[n - 1])


def denials(out: Path) -> int:
    cfg = load_config(CONFIG)
    rows: list[dict] = []
    for id_, cite, n in PLANNER_DENIALS:
        ev_path = ROOT / cite
        ev = _event_line(ev_path, n)
        if ev.get("type") != "check":
            raise SystemExit(2)
        prev = _event_line(ev_path, n - 1)
        plan = _run_dir_plan(ev_path)
        task_id = _task_of(ev_path.parents[2].name)
        tmp, ws = _prepared(task_id)
        try:
            flagged = _policy_flagged(task_id, plan, cfg, ws, ev["command"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        verdict = VERDICT_FIXED_M20A if flagged else VERDICT_FIXED_HERE_PLANNER
        rows.append(
            _denial(
                id_,
                f"{cite}:{n}",
                prev.get("rule", ""),
                "planner check",
                ev["command"],
                verdict,
                f"type=check ok={ev['ok']} output_head={ev['output_head'][:120]!r}; "
                f"plan={_rel(plan)} validate_plan_policy_flagged={flagged}",
            )
        )
    stop_path = ROOT / M20D_STOP[0]
    stop_hits = [h for h in tripwire_hits() if h["events"] == M20D_STOP[0] and h["line"] == M20D_STOP[1]]
    if len(stop_hits) != 1:
        raise SystemExit(2)
    d5 = stop_hits[0]
    sel_lines = [n for n, _ in d5["_selected"]]
    rows.append(
        _denial(
            "D5",
            f"{M20D_STOP[0]}:{M20D_STOP[1]}",
            "confine:cd",
            "agent run_shell",
            str(_event_line(stop_path, sel_lines[0])["target"]),
            VERDICT_TRIPWIRE,
            f"tripwire count={d5['count']} responses={d5['responses']}; one model response "
            f"llm_call :{_response_of(_load_events(stop_path), sel_lines[0])}; "
            f"5 parallel run_shell policy denials :24-28; tool_call failures :{sel_lines[0]}-{sel_lines[-1]}",
        )
    )
    next_id = 6
    for h in tripwire_hits():
        if not h["same_response"]:
            continue
        if h["events"] == M20D_STOP[0] and h["line"] == M20D_STOP[1]:
            continue
        if any(r["cite"] == f"{h['events']}:{h['line']}" for r in rows):
            continue
        first = h["_selected"][0][1]
        rows.append(
            _denial(
                f"D{next_id}",
                f"{h['events']}:{h['line']}",
                _rule_from_error(h["_error_head"]),
                "agent run_shell",
                str(first.get("target", "")),
                VERDICT_TRIPWIRE,
                f"tripwire count={h['count']} responses={h['responses']} tool={h['tool']}",
            )
        )
        next_id += 1
    _write_jsonl(out, rows)
    return 0


def _rule_from_error(head: str) -> str:
    m = re.search(r"denied by policy \(([^)]*)\)", head)
    return m.group(1) if m else ""


def capture() -> dict:
    def dump(msgs: list) -> list:
        return [[m.role, m.content] for m in msgs]

    def run(replies: list[str]) -> list:
        seen: list = []
        queue = list(replies)

        async def call(msgs: list) -> str:
            seen.append(dump(msgs))
            return queue.pop(0)

        asyncio.run(plan_project(GOLDEN_GOAL, call, lenient=True, policy=None))
        return seen

    base = plan_messages(GOLDEN_GOAL, 8)
    rules = plan_messages(GOLDEN_GOAL, 8, policy_rules="- rule A\n- rule B")
    return {
        "plan": dump(base),
        "plan_rules": dump(rules),
        "repair": dump(repair_messages(rules, "not json", CAUSE_ERROR)),
        "policy_repair": dump(
            policy_repair_messages(
                rules,
                '{"goal":"g"}',
                [PolicyIssue("m1", "check", "cd x && ls", "confine:cd", "use paths")],
            )
        ),
        "run_valid": run([VALID_REPLY]),
        "run_repair": run([INVALID_REPLY, VALID_REPLY]),
    }


def golden(out: Path) -> int:
    _write_text(out, json.dumps(capture(), indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return 0


def _count_files(d: Path) -> int:
    return sum(1 for p in d.rglob("*") if p.is_file()) if d.is_dir() else 0


def _searched(names: tuple[str, ...]) -> list[dict]:
    out: list[dict] = []
    for label, base in OUTSIDE_SOURCES:
        for name in names:
            dirs = sorted(p for p in base.glob(f"**/{name}") if p.is_dir()) if base.is_dir() else []
            files = sum(_count_files(d) for d in dirs)
            out.append(
                {
                    "dir": f"{label}/**/{name}",
                    "dirs": len(dirs),
                    "regular_files": files,
                }
            )
    return out


def _search_text(entries: list[dict]) -> str:
    return "; ".join(f"{e['dir']}: {e['dirs']} dirs, {e['regular_files']} regular files" for e in entries)


def _needed(parts: tuple[str, ...]) -> bool:
    if any(p in ("fix3", "fix3p", "e2e_n08-r2") for p in parts[:-1]):
        return True
    return "records" in parts[:-1] and parts[-1].endswith(".json")


def _key_hit(rel: str, text: str) -> list[str]:
    hits = []
    for rx in m20_trial.KEY_SCAN_RES:
        if rx.search(text):
            hits.append(rel)
    for var in m20_trial.KEY_ENV_VARS:
        val = os.environ.get(var)
        if val and len(val) >= 6 and val in text:
            hits.append(rel)
    return hits


def inventory(dst: Path) -> int:
    copied: list[str] = []
    partial: list[dict] = []
    scanned = 0
    for label, base in OUTSIDE_SOURCES:
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(base)
            if not _needed(rel.parts):
                continue
            raw = p.read_text(encoding="utf-8")
            text, part_lines = _sanitize(raw, _pairs())
            if _key_hit(str(rel), text):
                print(f"key scan hit, file not written: outside/{label}/{rel.as_posix()}", file=sys.stderr)
                return 6
            dest_rel = f"outside/{label}/{rel.as_posix()}"
            _write_text(dst / dest_rel, raw)
            copied.append(dest_rel)
            scanned += 1
            partial.extend({"file": dest_rel, "line": n} for n in part_lines)
    blocked = [
        {
            "item": "D8 raw planner reply + events",
            "affected": "R2/R6",
            "reason": (
                "the raw planner reply behind the n08 r2 final error (Expecting value, line 1 column 1) "
                "was not saved: the outside sources hold only outcome.json for e2e_n08-r2 (the committed "
                "events are the m20d copies), and no searched dir holds a planner reply record. Searched: " + _search_text(_searched(("e2e_n08-r2", "records", "fix3p")))
            ),
            "searched": _searched(("e2e_n08-r2", "records", "fix3p")),
        },
        {
            "item": "deepseek-fix3 plan.toml x5 + per-condition reference details",
            "affected": "R3 h01/h05",
            "reason": (
                "no deepseek-fix3 plan.toml and no per-condition reference details exist in any "
                "searched dir. Searched: " + _search_text(_searched(("fix3", "fix3p", "records")))
            ),
            "searched": _searched(("fix3", "fix3p", "records")),
        },
        {
            "item": "gemini-rehearsal-fix3 plan.toml x5",
            "affected": "R3, R11",
            "reason": (
                "no gemini-rehearsal-fix3 plan.toml exists in any searched dir. Searched: "
                + _search_text(_searched(("fix3", "fix3p", "records")))
            ),
            "searched": _searched(("fix3", "fix3p", "records")),
        },
    ]
    derived = [
        {"file": "refcheck.jsonl", "command": "TERM=xterm-256color uv run python tests/m25_diag.py refcheck --config tests/fixtures/m20/artifacts/cora-m20-deepseek.toml --out tests/fixtures/m25/refcheck.jsonl"},
        {"file": "tripcheck.jsonl", "command": "uv run python tests/m25_diag.py tripcheck --out tests/fixtures/m25/tripcheck.jsonl"},
        {"file": "denials.jsonl", "command": "uv run python tests/m25_diag.py denials --out tests/fixtures/m25/denials.jsonl"},
        {"file": "planner_prompts_off.json", "command": "uv run python tests/m25_diag.py golden --out tests/fixtures/m25/planner_prompts_off.json"},
        {"file": "refcheck_classes.jsonl", "command": "hand-written classification of refcheck.jsonl rows with pass_ref false"},
    ]
    manifest = {
        "source": "outside-repo, read-only: <REPO>/.cora/m20 (repo-cora-m20) and <TMP>/cora-m20 (tmp-cora-m20); copied through m20a_artifacts._sanitize",
        "files": copied,
        "blocked": blocked,
        "derived": derived,
        "not_copied": [],
        "key_scan": {"files": scanned, "matches": 0},
        "placeholders": {
            "<REPO>": "repository root",
            "<HOME>": "home directory",
            "<TMP>": "system temp directory",
            "<TMP-PARTIAL>": "truncated fragment of a system temp path cut off by the recorder",
        },
        "partial_tmp": sorted(partial, key=lambda e: (e["file"], e["line"])),
        "redactions": [],
    }
    _write_text(dst / "MANIFEST.json", json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M25 Step 0 diagnosis helpers.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("inventory")
    s.add_argument("--dst", required=True)
    s = sub.add_parser("refcheck")
    s.add_argument("--config", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("tripcheck")
    s.add_argument("--out", required=True)
    s = sub.add_parser("denials")
    s.add_argument("--out", required=True)
    s = sub.add_parser("golden")
    s.add_argument("--out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "inventory":
        return inventory(Path(args.dst).resolve())
    if args.cmd == "refcheck":
        return refcheck(Path(args.config).resolve(), Path(args.out).resolve())
    if args.cmd == "tripcheck":
        return tripcheck(Path(args.out).resolve())
    if args.cmd == "denials":
        return denials(Path(args.out).resolve())
    if args.cmd == "golden":
        return golden(Path(args.out).resolve())
    return 2


if __name__ == "__main__":
    sys.exit(main())
