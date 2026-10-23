from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cora.bench.live_tasks import MULTI_TASKS
from cora.core.prerouter import RouteInputs, features, read_inputs
from cora.core.shellguard import PathGuard
from m15_baseline import prepare, task_prompt
from m19_oracle import read_args_file, view_rows
from m19_panel import HARD_F, HARD_X

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/m19e"
BENCH = ROOT / ".cora/bench"
PANEL_ARGS = ROOT / "tests/fixtures/m19/panel-args.txt"
PREREG_PREFIX = "## M19e 1단계 사전 등록 ("
RUNS_OUT = FIX / "runs.jsonl"
INPUTS_OUT = FIX / "inputs.jsonl"

MULTI_IDS: tuple[str, ...] = tuple(t.id for t in MULTI_TASKS)
E2E_IDS: tuple[str, ...] = (
    "e2e_todo_cli",
    "e2e_text_stats",
    "e2e_rest_notes",
    "e2e_md_to_html",
    "e2e_refactor_inventory",
)
HARD_IDS: tuple[str, ...] = HARD_F + HARD_X
SETS: dict[str, tuple[str, ...]] = {"multi": MULTI_IDS, "e2e": E2E_IDS, "hard": HARD_IDS}
ALL_TASKS: tuple[str, ...] = MULTI_IDS + E2E_IDS + HARD_IDS
SET_OF: dict[str, str] = {t: name for name, ids in SETS.items() for t in ids}

ARM_CHEAP = "a"
ARM_STRONG = "e"
M15_CHEAP_ARM = "A cheap"
M15_STRONG_ARM = "C strong"


@dataclass(frozen=True)
class Group:
    cell: str
    tier: str
    rows: list[dict]
    events_rows: list[dict]
    events_dir: Path | None
    check_multiset: bool = False


def committed_bench_results() -> str:
    try:
        proc = subprocess.run(
            ["git", "show", "HEAD:.docs/bench-results.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def prereg_committed() -> bool:
    return any(line.startswith(PREREG_PREFIX) for line in committed_bench_results().splitlines())


def require_prereg() -> None:
    if not prereg_committed():
        print("error: pre-registration not committed", file=sys.stderr)
        raise SystemExit(2)


def prefix_markers(events: list[dict]) -> dict:
    start = 0
    for i, ev in enumerate(events):
        if ev.get("type") == "attempt_start":
            start = i + 1
            break
    parse_error = 0
    tool_error = 0
    edit_old = 0
    read_missing = 0
    prefix_cost = 0.0
    react = 0
    for ev in events[start:]:
        kind = ev.get("type")
        if kind == "llm_call" and ev.get("purpose") == "react":
            react += 1
            if react == 3:
                break
            prefix_cost += float(ev.get("cost_usd") or 0.0)
            continue
        if kind == "parse_error":
            parse_error += 1
        elif kind == "tool_call" and _is_false(ev.get("ok")):
            tool_error += 1
            if ev.get("tool") == "read_file":
                read_missing += 1
            if str(ev.get("output_head", "")).startswith("edit_file failed: 'old' text not found"):
                edit_old += 1
    return {
        "markers": parse_error + tool_error,
        "parse_error": parse_error,
        "tool_error": tool_error,
        "edit_old_not_found": edit_old,
        "read_missing": read_missing,
        "prefix_cost_usd": prefix_cost,
    }


def _is_false(value: Any) -> bool:
    return value is False or str(value) == "False"


def match_sessions(
    results: Sequence[Mapping[str, Any]],
    sessions: Sequence[Mapping[str, Any]],
    prompt_of: Callable[[str], str],
) -> list[str | None]:
    pool = sorted(
        (s for s in sessions if s.get("attempt") == 0), key=lambda s: str(s["id"])
    )
    candidates: dict[str, list[str]] = {}
    seen: dict[str, int] = defaultdict(int)
    out: list[str | None] = []
    for r in results:
        task = str(r["task"])
        if task not in candidates:
            text = prompt_of(task)
            candidates[task] = [str(s["id"]) for s in pool if s.get("task") == text]
        i = seen[task]
        seen[task] += 1
        ids = candidates[task]
        out.append(ids[i] if i < len(ids) else None)
    return out


def render_judge_input(inp: RouteInputs) -> str:
    repo = inp.repo
    spec = inp.spec_text or "(none)"
    named = ", ".join(repo.named_paths) or "(none)"
    return (
        "TASK PROMPT:\n"
        f"{inp.prompt}\n\n"
        "SPEC FILES (named in the prompt, capped at 6000 chars):\n"
        f"{spec}\n\n"
        "REPOSITORY PROBE:\n"
        f"files: {repo.n_files}; python files: {repo.n_py_files}; "
        f"total lines: {repo.total_lines}\n"
        f"paths named in the prompt: {named}; missing: {repo.named_missing}\n"
        f"files matching spec identifiers: {repo.scope_files}"
    )


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _solved(row: Mapping[str, Any]) -> bool:
    if row["task"] in MULTI_IDS:
        return row.get("status") == "solved"
    value = row.get("full_pass")
    if not isinstance(value, bool):
        raise ValueError(f"full_pass is not a bool for {row['task']}")
    return value


def _json_rows(path: Path, arm: str | None, tasks: Sequence[str]) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict] = []
    for r in data["results"]:
        if r.get("task") not in tasks:
            continue
        if arm is not None and r.get("arm") != arm:
            continue
        out.append(
            {
                "task": r["task"],
                "model": r["model"],
                "solved": _solved(r),
                "cost_usd": float(r["cost_usd"]),
                "status": r.get("status"),
            }
        )
    return out


def _panel_rows(arm: str, tasks: Sequence[str]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for r in view_rows(read_args_file(PANEL_ARGS), None, "unsolved", "report"):
        if r.arm != arm or r.task not in tasks:
            continue
        grouped.setdefault(r.source, []).append(
            {"task": r.task, "model": r.model, "solved": r.solved, "cost_usd": r.cost_usd}
        )
    return grouped


def _load_sessions(root: Path) -> list[dict]:
    sessions: list[dict] = []
    for d in sorted(root.iterdir()):
        meta_path = d / "session.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        events_path = d / "events.jsonl"
        events: list[dict] = []
        if events_path.is_file():
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        sessions.append(
            {
                "id": d.name,
                "task": meta.get("task"),
                "attempt": meta.get("attempt"),
                "events": events,
            }
        )
    return sessions


def _events_pairs(
    rows: Sequence[Mapping[str, Any]], events_dir: Path
) -> list[tuple[str, dict | None]]:
    root = events_dir / "state" / "sessions"
    if not root.is_dir():
        return [("no_events", None) for _ in rows]
    sessions = _load_sessions(root)
    ids = match_sessions(rows, sessions, task_prompt)
    by_id = {s["id"]: s for s in sessions}
    out: list[tuple[str, dict | None]] = []
    for sid in ids:
        if sid is None:
            out.append(("unmatched", None))
        else:
            out.append(("ok", prefix_markers(by_id[sid]["events"])))
    return out


def _check_multiset(reg: Sequence[dict], ev: Sequence[dict]) -> None:
    for task in MULTI_IDS:
        a = sorted(r["solved"] for r in reg if r["task"] == task)
        b = sorted(r["solved"] for r in ev if r["task"] == task)
        if a != b:
            raise ValueError(f"multi check failed for {task}: registered {a} vs events {b}")


def _groups() -> list[Group]:
    groups: list[Group] = []

    multi_reg = _json_rows(BENCH / "m15/merged/report.json", M15_CHEAP_ARM, MULTI_IDS)
    multi_ev = _json_rows(BENCH / "m15/A-multi/report.json", None, MULTI_IDS)
    _check_multiset(multi_reg, multi_ev)
    groups.append(
        Group("M15 A cheap", "cheap", multi_reg, multi_ev, BENCH / "m15/A-multi", True)
    )

    for sub in ("m16d/A-e2e", "m16d/A2-e2e"):
        rows = _json_rows(BENCH / sub / "report.json", None, E2E_IDS)
        groups.append(Group("M16d A''", "cheap", rows, rows, BENCH / sub))

    md_rows = _json_rows(BENCH / "m17/OFF-md/report.json", None, E2E_IDS)
    groups.append(Group("M17 OFF", "cheap", md_rows, md_rows, BENCH / "m17/OFF-md"))

    refactor_rows = _json_rows(BENCH / "m15b/retest-cheap/report.json", None, E2E_IDS)
    groups.append(
        Group(
            "M15b retest-cheap",
            "cheap",
            refactor_rows,
            refactor_rows,
            BENCH / "m15b/retest-cheap",
        )
    )

    strong_rows = _json_rows(
        BENCH / "m15/merged/report.json", M15_STRONG_ARM, MULTI_IDS + E2E_IDS
    )
    groups.append(Group("M15 C strong", "strong", strong_rows, strong_rows, None))

    for arm, cell, tier in (
        (ARM_CHEAP, "M19 arm a", "cheap"),
        (ARM_STRONG, "M19 arm e", "strong"),
    ):
        for source, rows in _panel_rows(arm, HARD_IDS).items():
            events_dir = BENCH / "m19/runs" / Path(source).stem if tier == "cheap" else None
            groups.append(Group(cell, tier, rows, rows, events_dir))
    return groups


def _group_records(group: Group) -> list[dict]:
    queues: dict[str, list[tuple[str, dict | None]]] = defaultdict(list)
    if group.tier == "cheap" and group.events_dir is not None:
        pairs = _events_pairs(group.events_rows, group.events_dir)
        for ev, pair in zip(group.events_rows, pairs, strict=True):
            queues[ev["task"]].append(pair)
    records: list[dict] = []
    for r in group.rows:
        if group.tier == "cheap":
            queue = queues[r["task"]]
            status, s4 = queue.pop(0) if queue else ("unmatched", None)
        else:
            status, s4 = "n/a", None
        records.append(
            {
                "task": r["task"],
                "set": SET_OF[r["task"]],
                "tier": group.tier,
                "cell": group.cell,
                "model": r["model"],
                "solved": r["solved"],
                "cost_usd": r["cost_usd"],
                "s4": s4,
                "s4_status": status,
            }
        )
    return records


def build_runs() -> list[dict]:
    records: list[dict] = []
    for group in _groups():
        records.extend(_group_records(group))
    return records


def _report_runs(records: Sequence[dict]) -> None:
    counts: dict[str, dict[str, int]] = {}
    for r in records:
        if r["tier"] != "cheap":
            continue
        c = counts.setdefault(r["cell"], {"matched": 0, "unmatched": 0})
        if r["s4_status"] == "ok":
            c["matched"] += 1
        else:
            c["unmatched"] += 1
    for cell, c in counts.items():
        print(f"{cell}: matched {c['matched']}, unmatched {c['unmatched']}")
    for r in records:
        if r["tier"] == "cheap" and r["s4_status"] != "ok":
            print(f"  unmatched: {r['task']} ({r['cell']}, {r['model']}, {r['s4_status']})")


def _write_jsonl(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    path.write_text(text, encoding="utf-8")


def build_inputs() -> list[dict]:
    rows: list[dict] = []
    for task in ALL_TASKS:
        prompt = task_prompt(task)
        with tempfile.TemporaryDirectory() as tmp:
            ws = prepare(task, Path(tmp) / "t")
            inp = read_inputs(prompt, ws, guard=PathGuard(ws, ()))
        judge_input = render_judge_input(inp)
        rows.append(
            {
                "task": task,
                "set": SET_OF[task],
                "prompt_sha": _sha16(prompt),
                "probe": asdict(inp.repo),
                "features": features(inp),
                "judge_input": judge_input,
                "judge_input_sha": _sha16(judge_input),
            }
        )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m19e_data")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_runs = sub.add_parser("runs")
    p_runs.add_argument("--out", type=Path, default=RUNS_OUT)
    p_inputs = sub.add_parser("inputs")
    p_inputs.add_argument("--out", type=Path, default=INPUTS_OUT)
    args = parser.parse_args(argv)
    try:
        require_prereg()
    except SystemExit as exc:
        return int(exc.code or 2)
    try:
        if args.cmd == "runs":
            records = build_runs()
            _write_jsonl(args.out, records)
            _report_runs(records)
        else:
            _write_jsonl(args.out, build_inputs())
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
