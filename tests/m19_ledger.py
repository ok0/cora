from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "tests/fixtures/m19/ledger.jsonl"
PREREG = ROOT / "tests/fixtures/m19/preregistration.md"
ALLOCATION_USD = 6.00
PAID_CAP_USD = 10.00
MAX_COST_CAP_USD = 0.50
E_STOP_USD = 2.16
SKIP_FACTOR = 1.5
MATCH_TOL_USD = 0.001
KEY_EXPIRY = datetime(2026, 10, 22, 9, 11, tzinfo=UTC)
CELL_ORDER: tuple[tuple[str, float], ...] = (
    ("a(m1)", 0.8506),
    ("a(m2)", 0.4424),
    ("e", 2.1551),
    ("c_s(m1)", 1.1974),
    ("b(m1)", 1.1974),
    ("d1(m1)", 0.2365),
    ("c_cc(m1→m2)", 1.1974),
    ("c_s(m2)", 0.6228),
    ("b(m2)", 0.6228),
    ("d1(m2)", 0.1230),
    ("a(m3)", 0.1021),
    ("g(m2)", 0.3604),
)
CELL_NAMES: tuple[str, ...] = tuple(name for name, _ in CELL_ORDER)
CELL_EXPECTED: dict[str, float] = dict(CELL_ORDER)
CONDITIONAL_CELLS = ("b(m1)", "c_cc(m1→m2)", "b(m2)", "g(m2)")
HARD_X = ("e2e_hx1", "e2e_hx2")
D2_SETTINGS_KEYS = (
    "max_task_cost_usd",
    "max_iterations",
    "stall_threshold_s",
    "protocols",
    "tool_groups",
    "tools",
    "sensor",
    "seed",
    "suite",
    "verify_attempts",
)
ROW_RE = re.compile(
    r"^\| (M19-\d\d) \| (\S+) \| (\S+) \| (\d+) \| ([\d.]+) \| ([\d.]+) \| `(uv run [^`]+)` \|$",
    re.MULTILINE,
)
AMEND_RE = re.compile(r"^\| (수정|편차) (M19-\d\d) \| `(uv run [^`]+)` \|$", re.MULTILINE)
RERUN_RE = re.compile(
    r"^\| 재실행 (RR-\d\d) \| (M19-\d\d) \| (\S+) \| (\d+) \| ([\d.]+) \| ([\d.]+) "
    r"\| `(uv run [^`]+)` \|$",
    re.MULTILINE,
)
DEADLINE_OF: dict[str | None, str] = {
    None: ".cora/bench/m19/deadline.toml",
    ".cora/bench/m19/cascade-strong.toml": ".cora/bench/m19/deadline-cascade-strong.toml",
    ".cora/bench/m19/cascade-m1-m2.toml": ".cora/bench/m19/deadline-cascade-m1-m2.toml",
    ".cora/bench/m19/deleg-nudge.toml": ".cora/bench/m19/deadline-deleg-nudge.toml",
    ".cora/bench/m19/keys-on.toml": ".cora/bench/m19/deadline-keys-on.toml",
}
DEADLINE_ERROR = "RequestDeadlineExceeded"
ROUTING_OF: dict[str | None, str] = {
    ".cora/bench/m19/cascade-strong.toml": ".cora/bench/m19/deadline-nobedrock-cascade-strong.toml",
    ".cora/bench/m19/deleg-nudge.toml": ".cora/bench/m19/deadline-nobedrock-deleg-nudge.toml",
}
ROUTING_ERROR_MARKERS = ("HTTP 400", "stopSequences")
RERUN_MARKERS = {
    "deadline": (DEADLINE_ERROR,),
    "routing": ROUTING_ERROR_MARKERS,
    "deadline-nobedrock": (DEADLINE_ERROR,),
}
TASK_CAP_CAUSES = ("routing", "deadline-nobedrock")
AMEND_NOTE = {
    "수정": "명령 수정 (사전 등록 수정 참조)",
    "편차": "출력 경로 편차 (사전 등록 수정 참조)",
}
GEN_MODEL = "google/gemini-2.5-flash-lite"
QWEN_MODEL = "qwen/qwen3-coder-30b-a3b-instruct"
ABSENT = object()


class LedgerError(Exception):
    pass


@dataclass(frozen=True)
class Call:
    id: str
    cell: str
    tasks: tuple[str, ...]
    repeats: int
    max_cost: float
    plan_total: float | None
    command: str
    out: str
    registered: str = ""
    amended: str = ""
    of: str | None = None
    repeat_index: int | None = None
    cause: str = ""


def _out_of(command: str) -> str:
    tokens = command.split()
    return tokens[tokens.index("--out") + 1]


def _strip(command: str, keys: tuple[str, ...] = ("-c", "--out")) -> list[str]:
    tokens = command.split()
    kept: list[str] = []
    index = 0
    while index < len(tokens):
        if tokens[index] in keys:
            index += 2
        else:
            kept.append(tokens[index])
            index += 1
    return kept


def _config_of(command: str) -> str | None:
    tokens = command.split()
    if "-c" not in tokens:
        return None
    return tokens[tokens.index("-c") + 1]


def _set_config(tokens: list[str], path: str) -> list[str]:
    result = list(tokens)
    if "-c" in result:
        result[result.index("-c") + 1] = path
    else:
        result[result.index("bench") + 1 : result.index("bench") + 1] = ["-c", path]
    return result


def _set_opt(tokens: list[str], key: str, value: str) -> list[str]:
    result = list(tokens)
    if key in result:
        result[result.index(key) + 1] = value
    else:
        result += [key, value]
    return result


def _ceil_cent(x: float) -> float:
    return math.ceil(x * 100 - 1e-9) / 100


def _deadline_config(config: str | None) -> str:
    if config not in DEADLINE_OF:
        raise LedgerError(f"no deadline config for {config}")
    return DEADLINE_OF[config]


def load_calls(text: str) -> list[Call]:
    calls: list[Call] = []
    for match in ROW_RE.finditer(text):
        call_id, cell, tasks, repeats, max_cost, plan_total, command = match.groups()
        calls.append(
            Call(
                id=call_id,
                cell=cell,
                tasks=tuple(tasks.split(",")),
                repeats=int(repeats),
                max_cost=float(max_cost),
                plan_total=float(plan_total),
                command=command,
                out=_out_of(command),
                registered=command,
            )
        )
    expected_ids = [f"M19-{n:02d}" for n in range(1, 52)]
    if [c.id for c in calls] != expected_ids:
        raise LedgerError(f"registered calls must be M19-01..M19-51 in order, got {len(calls)}")
    return calls


def apply_amendments(calls: Sequence[Call], text: str) -> list[Call]:
    by_id = {c.id: c for c in calls}
    rows: dict[str, list[tuple[str, str]]] = {}
    for match in AMEND_RE.finditer(text):
        kind, call_id, new = match.groups()
        if call_id not in by_id:
            raise LedgerError(f"amendment for unregistered call {call_id}")
        rows.setdefault(call_id, []).append((kind, new))
    replaced: dict[str, Call] = {}
    for call_id, entries in rows.items():
        registered = by_id[call_id]
        for _, new in entries:
            if _strip(new) != _strip(registered.command):
                raise LedgerError(f"amendment {call_id} changes more than -c/--out")
        if len(entries) == 1:
            kind, new = entries[0]
            if kind == "수정":
                if _config_of(new) != _deadline_config(_config_of(registered.command)):
                    raise LedgerError(f"amendment {call_id} uses the wrong deadline config")
            elif _config_of(new) != _config_of(registered.command):
                raise LedgerError(f"deviation {call_id} changes the -c config")
            effective_kind, effective = kind, new
        elif len(entries) == 2:
            reg_cfg = _config_of(registered.command)
            (kind1, new1), (kind2, new2) = entries
            valid = (
                kind1 == "수정"
                and _config_of(new1) == _deadline_config(reg_cfg)
                and kind2 == "수정"
                and reg_cfg in ROUTING_OF
                and _config_of(new2) == ROUTING_OF[reg_cfg]
            )
            if not valid:
                raise LedgerError(f"amendment for {call_id} appears more than once")
            effective_kind, effective = "수정", new2
        else:
            raise LedgerError(f"amendment for {call_id} appears more than once")
        replaced[call_id] = replace(
            registered, command=effective, out=_out_of(effective), amended=effective_kind
        )
    return [replaced.get(c.id, c) for c in calls]


def load_reruns(
    text: str,
    registered_by_id: dict[str, Call],
    effective_by_id: dict[str, Call] | None = None,
) -> list[Call]:
    reruns: list[Call] = []
    seen: set[tuple[str, str, int]] = set()
    for index, match in enumerate(RERUN_RE.finditer(text), start=1):
        rr_id, of_id, task, repeat, max_cost, plan, command = match.groups()
        if rr_id != f"RR-{index:02d}":
            raise LedgerError(f"reruns must be RR-01..RR-NN consecutive, got {rr_id}")
        if of_id not in registered_by_id:
            raise LedgerError(f"{rr_id}: original {of_id} is not a registered call")
        of = registered_by_id[of_id]
        if task not in of.tasks:
            raise LedgerError(f"{rr_id}: task {task} is not in {of_id}")
        key = (of_id, task, int(repeat))
        if key in seen:
            raise LedgerError(f"{rr_id}: {of_id} {task} r{repeat} is already rerun")
        seen.add(key)
        reg_cfg = _config_of(of.command)
        cfg = _config_of(command)
        eff_cfg = _config_of((effective_by_id or registered_by_id).get(of_id, of).command)
        if cfg == _deadline_config(reg_cfg):
            cause = "deadline"
            expected_max = _ceil_cent(of.max_cost / (len(of.tasks) * of.repeats))
            if abs(float(max_cost) - expected_max) > 1e-9:
                raise LedgerError(f"{rr_id}: --max-cost {max_cost} != {expected_max:.2f}")
        elif reg_cfg in ROUTING_OF and cfg == ROUTING_OF[reg_cfg]:
            if eff_cfg == cfg:
                cause = "deadline-nobedrock"
                expected_max = _ceil_cent(of.max_cost / (len(of.tasks) * of.repeats))
                if abs(float(max_cost) - expected_max) > 1e-9:
                    raise LedgerError(f"{rr_id}: --max-cost {max_cost} != {expected_max:.2f}")
            else:
                cause = "routing"
                if not 0 < float(max_cost) <= of.max_cost + 1e-9:
                    raise LedgerError(
                        f"{rr_id}: --max-cost {max_cost} exceeds the original {of.max_cost:.2f}"
                    )
        else:
            raise LedgerError(f"{rr_id}: command differs from the rerun rule")
        tokens = _set_config(_strip(of.command), cfg)
        tokens = _set_opt(tokens, "--tasks", task)
        tokens = _set_opt(tokens, "--repeats", "1")
        tokens = _set_opt(tokens, "--max-cost", f"{float(max_cost):.2f}")
        tokens = _set_opt(tokens, "--out", f".cora/bench/m19/runs/rerun-{index:02d}")
        if " ".join(tokens) != command:
            raise LedgerError(f"{rr_id}: command differs from the rerun rule")
        reruns.append(
            Call(
                id=rr_id,
                cell=of.cell,
                tasks=(task,),
                repeats=1,
                max_cost=float(max_cost),
                plan_total=float(plan),
                command=command,
                out=_out_of(command),
                registered=command,
                of=of_id,
                repeat_index=int(repeat),
                cause=cause,
            )
        )
    return reruns


def _conditional_calls() -> tuple[Call, ...]:
    splits = (
        ("e2e_h01,e2e_h02", 0.42),
        ("e2e_h03", 0.36),
        ("e2e_h04,e2e_h05", 0.45),
        ("e2e_h06", 0.27),
        ("e2e_hx2", 0.24),
    )
    calls: list[Call] = []

    def add(
        prefix: str, cell: str, template: str, tasks_splits: Sequence[tuple[str, float]]
    ) -> None:
        for index, (tasks, max_cost) in enumerate(tasks_splits, start=1):
            nn = f"{index:02d}"
            command = template.format(tasks=tasks, cost=f"{max_cost:.2f}", nn=nn)
            calls.append(
                Call(
                    id=f"{prefix}-{nn}",
                    cell=cell,
                    tasks=tuple(tasks.split(",")),
                    repeats=3,
                    max_cost=max_cost,
                    plan_total=None,
                    command=command,
                    out=_out_of(command),
                )
            )

    add(
        "B1",
        "b(m1)",
        "uv run cora bench --live --suite e2e --models "
        + GEN_MODEL
        + " --protocols react --verify-attempts 3 --tasks {tasks} --repeats 3 "
        "--max-cost {cost} --out .cora/bench/m19/runs/b-m1-i{nn}",
        splits,
    )
    add(
        "CC",
        "c_cc(m1→m2)",
        "uv run cora bench -c .cora/bench/m19/deadline-cascade-m1-m2.toml --live "
        "--suite e2e --models "
        + GEN_MODEL
        + " --protocols react --ab auto-routed --sensor --sensor-source auto --tasks {tasks} "
        "--repeats 3 --max-cost {cost} --out .cora/bench/m19/runs/c_cc-m1-i{nn}",
        splits,
    )
    add(
        "B2",
        "b(m2)",
        "uv run cora bench -c .cora/bench/m19/deadline.toml --live --suite e2e --models "
        + QWEN_MODEL
        + " --protocols react --verify-attempts 3 --tasks {tasks} --repeats 3 "
        "--max-cost {cost} --out .cora/bench/m19/runs/b-m2-i{nn}",
        splits,
    )
    add(
        "G2",
        "g(m2)",
        "uv run cora bench -c .cora/bench/m19/deadline-keys-on.toml --live --suite e2e --models "
        + QWEN_MODEL
        + " --protocols react --tasks {tasks} --repeats 3 --max-cost {cost} "
        "--out .cora/bench/m19/runs/g-m2-i{nn}",
        splits[:4],
    )
    return tuple(calls)


PREREG_TEXT = PREREG.read_text(encoding="utf-8")
STATIC_CALLS: tuple[Call, ...] = tuple(load_calls(PREREG_TEXT))
EFFECTIVE_STATIC: tuple[Call, ...] = tuple(apply_amendments(STATIC_CALLS, PREREG_TEXT))
CONDITIONAL_CALLS: tuple[Call, ...] = _conditional_calls()
ALL_CALLS: tuple[Call, ...] = EFFECTIVE_STATIC + CONDITIONAL_CALLS
RERUNS: tuple[Call, ...] = tuple(
    load_reruns(
        PREREG_TEXT,
        {c.id: c for c in STATIC_CALLS},
        {c.id: c for c in EFFECTIVE_STATIC},
    )
)
BY_ID: dict[str, Call] = {c.id: c for c in (*ALL_CALLS, *RERUNS)}


def get_call(call_id: str) -> Call:
    if call_id not in BY_ID:
        raise LedgerError(f"unknown call {call_id}")
    return BY_ID[call_id]


def calls_of(cell: str) -> list[Call]:
    return [c for c in ALL_CALLS if c.cell == cell]


def plan_command(call: Call) -> str:
    tokens = call.command.replace(" bench ", " bench plan ", 1).split()
    kept: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in ("--live", "--sensor"):
            index += 1
        elif token in ("--sensor-source", "--verify-attempts", "--out"):
            index += 2
        else:
            kept.append(token)
            index += 1
    return " ".join(kept)


def parse_iso(text: str) -> datetime:
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


@dataclass
class State:
    start: dict[str, Any] | None
    m19_total: float
    e_total: float
    last_usage: float | None
    paid_total: float | None
    cells: list[dict[str, Any]]
    status: dict[str, str]
    cell_of: dict[str, str]
    unresolved: list[str]
    events: list[dict[str, Any]]


def _set_flag(items: list[str], item: str, flag: bool) -> None:
    if flag and item not in items:
        items.append(item)
    if not flag and item in items:
        items.remove(item)


def fold(records: Sequence[dict[str, Any]]) -> State:
    start: dict[str, Any] | None = None
    last_usage: float | None = None
    cells: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    status: dict[str, str] = {}
    cell_of: dict[str, str] = {}
    spend: dict[str, float] = {}
    unresolved: list[str] = []
    for record in records:
        kind = record["type"]
        if kind == "start":
            start = record
            last_usage = float(record["usage"])
        elif kind == "cell":
            cells.append(record)
        elif kind == "event":
            events.append(record)
        elif kind == "call":
            call_id = record["call"]
            status[call_id] = record["status"]
            cell_of[call_id] = record["cell"]
            spend[call_id] = float(record.get("spend") or 0.0)
            if record.get("usage_after") is not None:
                last_usage = float(record["usage_after"])
            _set_flag(
                unresolved,
                call_id,
                record["status"] == "failed" or bool(record.get("mismatch")),
            )
        elif kind == "settle":
            call_id = record["call"]
            spend[call_id] = float(record["spend"])
            last_usage = float(record["usage"])
            _set_flag(unresolved, call_id, bool(record["mismatch"]))
        elif kind == "resolve":
            _set_flag(unresolved, record["call"], False)
    counted = [c for c, s in status.items() if s in ("executed", "failed")]
    m19_total = sum(spend[c] for c in counted)
    e_total = sum(spend[c] for c in counted if cell_of[c] == "e")
    paid_total: float | None = None
    if start is not None and last_usage is not None:
        paid_total = float(start["paid_total"]) + (last_usage - float(start["usage"]))
    return State(
        start=start,
        m19_total=m19_total,
        e_total=e_total,
        last_usage=last_usage,
        paid_total=paid_total,
        cells=cells,
        status=status,
        cell_of=cell_of,
        unresolved=unresolved,
        events=events,
    )


def _with_totals(record: dict[str, Any], records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    state = fold([*records, record])
    record["m19_total"] = state.m19_total
    record["paid_total"] = state.paid_total
    record["e_total"] = state.e_total
    return record


def _report_cost(path: Path) -> float:
    data = json.loads(path.read_text(encoding="utf-8"))
    return sum(float(result["cost_usd"]) for result in data["results"])


def _latest_for(records: Sequence[dict[str, Any]], call_id: str) -> dict[str, Any] | None:
    found = [r for r in records if r.get("call") == call_id]
    return found[-1] if found else None


def _latest_call_record(records: Sequence[dict[str, Any]], call_id: str) -> dict[str, Any] | None:
    found = [r for r in records if r["type"] == "call" and r.get("call") == call_id]
    return found[-1] if found else None


def _start_required(state: State) -> dict[str, Any]:
    if state.start is None:
        raise LedgerError("ledger has no start record; run init first")
    return state.start


def _status_record(
    call: Call, status: str, note: str, now: datetime, records: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "call",
        "utc": iso_utc(now),
        "call": call.id,
        "cell": call.cell,
        "status": status,
        "usage_before": None,
        "usage_after": None,
        "report": None,
        "report_cost": 0.0,
        "delta": 0.0,
        "mismatch": False,
        "spend": 0.0,
        "note": note,
    }
    return _with_totals(record, records)


def cmd_init(args: argparse.Namespace, now: datetime) -> int:
    records = read_records(args.ledger)
    if records:
        raise LedgerError(f"ledger {args.ledger} is not empty; refusing to init")
    record = {
        "type": "start",
        "utc": iso_utc(now),
        "paid_total": args.paid_total,
        "usage": args.usage,
        "key_remaining": args.key_remaining,
        "balance": args.balance,
        "head": args.head,
        "confirmed": args.confirmed,
    }
    append_record(args.ledger, record)
    print(f"init: paid_total {args.paid_total:.6f}, usage {args.usage:.6f}")
    return 0


def cmd_cell(args: argparse.Namespace, now: datetime) -> int:
    records = read_records(args.ledger)
    state = fold(records)
    _start_required(state)
    if args.cell not in CELL_EXPECTED:
        raise LedgerError(f"unknown cell {args.cell}")
    done = [str(c["cell"]) for c in state.cells]
    if len(done) >= len(CELL_NAMES):
        raise LedgerError("every cell is already evaluated")
    next_cell = CELL_NAMES[len(done)]
    if args.cell != next_cell:
        print(f"FAIL cell order: next unevaluated cell is {next_cell}, not {args.cell}")
        return 1
    if done:
        problems: list[str] = []
        for call in calls_of(done[-1]):
            status = state.status.get(call.id)
            if status is None:
                problems.append(f"{call.id} has no record")
            elif status == "failed":
                problems.append(f"{call.id} failed")
            elif status == "executed" and call.id in state.unresolved:
                problems.append(f"{call.id} unresolved")
        if problems:
            print(f"FAIL previous cell {done[-1]} not final: " + "; ".join(problems))
            return 1
    expected = CELL_EXPECTED[args.cell]
    remaining = ALLOCATION_USD - state.m19_total
    needed = SKIP_FACTOR * expected
    run = remaining + 1e-9 >= needed
    decision = "RUN" if run else "SKIP"
    hours = (KEY_EXPIRY - now).total_seconds() / 3600
    print(
        f"CELL {args.cell}: remaining {remaining:.6f} vs 1.5 x {expected} "
        f"= {needed:.6f} -> {decision}"
    )
    print(f"hours to key expiry: {hours:.1f}")
    cell_record = {
        "type": "cell",
        "utc": iso_utc(now),
        "cell": args.cell,
        "expected": expected,
        "remaining": remaining,
        "needed": needed,
        "decision": decision,
        "hours_to_expiry": hours,
    }
    append_record(args.ledger, cell_record)
    if run and args.cell in CONDITIONAL_CELLS:
        print(
            "conditional: dated amendment + user confirmation of the derived calls required "
            "before its first call"
        )
    if not run:
        note = f"budget: cell skipped, remaining {remaining:.6f} < needed {needed:.6f}"
        for call in calls_of(args.cell):
            record = _status_record(call, "not_measured", note, now, read_records(args.ledger))
            append_record(args.ledger, record)
        print(f"skipped {len(calls_of(args.cell))} calls as not_measured")
    return 0


def _check_results(
    args: argparse.Namespace,
    now: datetime,
    records: Sequence[dict[str, Any]],
    state: State,
) -> tuple[list[tuple[str, bool, str]], float]:
    call = get_call(args.call)
    plan = float(args.plan_total)
    usage = float(args.usage)
    key_remaining = float(args.key_remaining)
    balance = float(args.balance)
    start = _start_required(state)
    results: list[tuple[str, bool, str]] = []

    last_cell = state.cells[-1] if state.cells else None
    recorded = {r["call"] for r in records if r["type"] == "call"}
    next_call = next((c for c in calls_of(call.cell) if c.id not in recorded), None)
    c1 = (
        last_cell is not None
        and last_cell["cell"] == call.cell
        and last_cell["decision"] == "RUN"
        and next_call is not None
        and next_call.id == call.id
    )
    results.append(
        ("C1", c1, f"{call.id} is the next call of run cell {call.cell}")
        if c1
        else (
            "C1",
            False,
            f"{call.id} is not the next call of a run cell (last cell: "
            f"{last_cell['cell'] if last_cell else 'none'})",
        )
    )

    if call.plan_total is None:
        results.append(("C2", True, "conditional: TOTAL read from bench plan at run time"))
    else:
        c2 = abs(plan - call.plan_total) <= 1e-6
        results.append(("C2", c2, f"plan TOTAL {plan:.6f} vs registered {call.plan_total:.6f}"))

    c3 = plan <= call.max_cost + 1e-9
    results.append(("C3", c3, f"plan TOTAL {plan:.6f} vs --max-cost {call.max_cost:.6f}"))

    c4 = call.max_cost <= MAX_COST_CAP_USD + 1e-9
    results.append(("C4", c4, f"--max-cost {call.max_cost:.6f} vs cap {MAX_COST_CAP_USD:.2f}"))

    last_usage = state.last_usage if state.last_usage is not None else float(start["usage"])
    c5 = abs(usage - last_usage) <= MATCH_TOL_USD
    results.append(
        (
            "C5",
            c5,
            f"/credits {usage:.6f} vs last recorded {last_usage:.6f}"
            + ("" if c5 else " (unexplained spend)"),
        )
    )

    paid_now = float(start["paid_total"]) + (usage - float(start["usage"]))
    limit = min(PAID_CAP_USD - paid_now, key_remaining, balance)
    c6 = plan <= limit + 1e-9
    results.append(
        ("C6", c6, f"plan TOTAL {plan:.6f} vs limit {limit:.6f} (min of paid cap, key, balance)")
    )

    c7 = state.m19_total < ALLOCATION_USD
    results.append(("C7", c7, f"M19 total {state.m19_total:.6f} < {ALLOCATION_USD:.2f}"))

    if call.cell == "e":
        c8 = state.e_total <= E_STOP_USD + 1e-9
        results.append(
            (
                "C8",
                c8,
                f"e_total {state.e_total:.6f} <= {E_STOP_USD:.2f}"
                + ("" if c8 else " e stop: mark the remaining e calls not_measured"),
            )
        )
    else:
        results.append(("C8", True, "n/a (not cell e)"))

    c9 = not state.unresolved
    results.append(
        ("C9", c9, "no unresolved calls" if c9 else "unresolved: " + ", ".join(state.unresolved))
    )

    c10 = now < KEY_EXPIRY
    results.append(("C10", c10, f"now {iso_utc(now)} < key expiry {iso_utc(KEY_EXPIRY)}"))

    amend_cells = {e.get("cell") for e in state.events if e["kind"] == "amend"}
    if call.cell in CONDITIONAL_CELLS:
        c11 = call.cell in amend_cells
        results.append(("C11", c11, f"amendment for conditional cell {call.cell}: {c11}"))
    else:
        results.append(("C11", True, "n/a (not conditional)"))

    after_e = CELL_NAMES.index(call.cell) > CELL_NAMES.index("e")
    if after_e:
        has_checkpoint = any(e["kind"] == "checkpoint" for e in state.events)
        results.append(
            (
                "C12",
                has_checkpoint,
                "checkpoint event exists"
                if has_checkpoint
                else "no checkpoint event before a call after cell e",
            )
        )
    else:
        results.append(("C12", True, "n/a (cell before or at e)"))
    return results, limit


def _original_error_run(records: Sequence[dict[str, Any]], state: State, call: Call) -> bool:
    orig = BY_ID[call.of or ""]
    record = _latest_call_record(records, orig.id)
    if state.status.get(orig.id) != "executed" or orig.id in state.unresolved:
        return False
    if record is None or not record.get("report") or not Path(record["report"]).exists():
        return False
    data = json.loads(Path(record["report"]).read_text(encoding="utf-8"))
    markers = RERUN_MARKERS[call.cause]
    return any(
        result.get("task") == call.tasks[0]
        and result.get("repeat_index") == call.repeat_index
        and result.get("status") == "error"
        and all(marker in str(result.get("detail") or "") for marker in markers)
        for result in data["results"]
    )


def _original_task_cap(records: Sequence[dict[str, Any]], call: Call) -> float | None:
    record = _latest_call_record(records, call.of or "")
    if record is None or not record.get("report") or not Path(record["report"]).exists():
        return None
    data = json.loads(Path(record["report"]).read_text(encoding="utf-8"))
    settings = data.get("settings") or {}
    mtc = settings.get("max_task_cost_usd")
    if mtc is None:
        return None
    entry = next(
        (
            task
            for task in (settings.get("e2e") or {}).get("tasks", [])
            if task.get("id") == call.tasks[0]
        ),
        None,
    )
    if entry is not None and "cost_usd" in entry:
        return min(float(mtc), float(entry["cost_usd"]))
    return float(mtc)


def _rerun_check_results(
    args: argparse.Namespace,
    now: datetime,
    records: Sequence[dict[str, Any]],
    state: State,
    call: Call,
) -> tuple[list[tuple[str, bool, str]], float]:
    assert call.of is not None
    orig = BY_ID[call.of]
    plan = float(args.plan_total)
    usage = float(args.usage)
    key_remaining = float(args.key_remaining)
    balance = float(args.balance)
    start = _start_required(state)
    results: list[tuple[str, bool, str]] = []

    e_index = CELL_NAMES.index("e")
    limit_index = max(CELL_NAMES.index(orig.cell), e_index)
    evaluated = [CELL_NAMES.index(str(c["cell"])) for c in state.cells]
    later_cells = [n for n in evaluated if n > limit_index]
    orig_evaluated = any(str(c["cell"]) == orig.cell for c in state.cells)
    has_checkpoint = any(e["kind"] == "checkpoint" for e in state.events)
    recorded = {r["call"] for r in records if r["type"] == "call"}
    next_rerun = next((r for r in RERUNS if r.id not in recorded), None)
    checkpoint_blocks = limit_index == e_index and has_checkpoint
    c1 = (
        orig_evaluated
        and not later_cells
        and not checkpoint_blocks
        and next_rerun is not None
        and next_rerun.id == call.id
    )
    results.append(
        ("C1", c1, f"{call.id} is the next rerun of {orig.id} (cell {orig.cell} evaluated)")
        if c1
        else (
            "C1",
            False,
            f"{call.id} is not the next rerun, or a later cell or checkpoint blocks it",
        )
    )

    assert call.plan_total is not None
    c2 = abs(plan - call.plan_total) <= 1e-6
    results.append(("C2", c2, f"plan TOTAL {plan:.6f} vs registered {call.plan_total:.6f}"))

    c3 = plan <= call.max_cost + 1e-9
    results.append(("C3", c3, f"plan TOTAL {plan:.6f} vs --max-cost {call.max_cost:.6f}"))

    c4 = call.max_cost <= MAX_COST_CAP_USD + 1e-9
    results.append(("C4", c4, f"--max-cost {call.max_cost:.6f} vs cap {MAX_COST_CAP_USD:.2f}"))

    last_usage = state.last_usage if state.last_usage is not None else float(start["usage"])
    c5 = abs(usage - last_usage) <= MATCH_TOL_USD
    results.append(
        (
            "C5",
            c5,
            f"/credits {usage:.6f} vs last recorded {last_usage:.6f}"
            + ("" if c5 else " (unexplained spend)"),
        )
    )

    paid_now = float(start["paid_total"]) + (usage - float(start["usage"]))
    limit = min(PAID_CAP_USD - paid_now, key_remaining, balance)
    c6 = plan <= limit + 1e-9
    results.append(
        ("C6", c6, f"plan TOTAL {plan:.6f} vs limit {limit:.6f} (min of paid cap, key, balance)")
    )

    c7 = state.m19_total + plan <= ALLOCATION_USD + 1e-9
    results.append(
        ("C7", c7, f"M19 total {state.m19_total:.6f} + plan {plan:.6f} <= {ALLOCATION_USD:.2f}")
    )

    if orig.cell == "e":
        c8 = state.e_total <= E_STOP_USD + 1e-9
        results.append(("C8", c8, f"e_total {state.e_total:.6f} <= {E_STOP_USD:.2f}"))
    else:
        results.append(("C8", True, "n/a (not cell e)"))

    c9 = not state.unresolved
    results.append(
        ("C9", c9, "no unresolved calls" if c9 else "unresolved: " + ", ".join(state.unresolved))
    )

    c10 = now < KEY_EXPIRY
    results.append(("C10", c10, f"now {iso_utc(now)} < key expiry {iso_utc(KEY_EXPIRY)}"))

    orig_indices = [
        i for i, r in enumerate(records) if r["type"] == "call" and r.get("call") == orig.id
    ]
    orig_index = orig_indices[-1] if orig_indices else None
    c11 = orig_index is not None and any(
        r["type"] == "event" and r.get("kind") == "amend" and r.get("cell") == "rerun"
        for r in records[orig_index + 1 :]
    )
    results.append(("C11", c11, f"amendment for reruns recorded after {orig.id}: {c11}"))

    markers = " + ".join(RERUN_MARKERS[call.cause])
    c12 = _original_error_run(records, state, call)
    results.append(
        (
            "C12",
            c12,
            f"{orig.id} {call.tasks[0]} r{call.repeat_index} is a {markers} error run"
            if c12
            else f"{orig.id} {call.tasks[0]} r{call.repeat_index} is not an executed "
            f"{markers} error run",
        )
    )

    c13 = call.id not in recorded
    results.append(("C13", c13, f"no call record yet for {call.id}: {c13}"))

    if call.cause in TASK_CAP_CAUSES:
        cap = _original_task_cap(records, call)
        c14 = cap is not None and abs(call.max_cost - cap) <= 1e-9
        text = (
            f"--max-cost {call.max_cost:.6f} vs original task cap {cap:.6f}"
            if cap is not None
            else "original task cap unknown"
        )
        results.append(("C14", c14, text))
    else:
        results.append(("C14", True, "n/a (정정 10 ceiling rule)"))
    return results, limit


def cmd_check(args: argparse.Namespace, now: datetime) -> int:
    records = read_records(args.ledger)
    state = fold(records)
    call = get_call(args.call)
    if call.of is not None:
        results, limit = _rerun_check_results(args, now, records, state, call)
    else:
        results, limit = _check_results(args, now, records, state)
    ok = all(passed for _, passed, _ in results)
    record = {
        "type": "check",
        "utc": iso_utc(now),
        "call": args.call,
        "plan_total": float(args.plan_total),
        "key_remaining": float(args.key_remaining),
        "balance": float(args.balance),
        "usage": float(args.usage),
        "limit": limit,
        "results": [[check_id, passed, text] for check_id, passed, text in results],
        "ok": ok,
    }
    append_record(args.ledger, record)
    for check_id, passed, text in results:
        print(f"{'PASS' if passed else 'FAIL'} {check_id} {text}")
    return 0 if ok else 1


def cmd_record(args: argparse.Namespace, now: datetime) -> int:
    records = read_records(args.ledger)
    call = get_call(args.call)
    state = fold(records)
    _start_required(state)
    last = _latest_for(records, call.id)
    if last is None or last["type"] != "check" or not last["ok"]:
        print(f"FAIL {call.id}: latest record is not a passing check; run check first")
        return 1
    report_path = Path(args.report)
    outcome: str | None = None
    if report_path.exists():
        report_cost = _report_cost(report_path)
        if call.of is not None:
            data = json.loads(report_path.read_text(encoding="utf-8"))
            matching = [r for r in data["results"] if r.get("task") == call.tasks[0]]
            if len(matching) != 1:
                raise LedgerError(
                    f"{call.id}: report must hold exactly one result for {call.tasks[0]}, "
                    f"found {len(matching)}"
                )
            outcome = str(matching[0]["status"])
    elif args.status == "failed" and args.note:
        report_cost = 0.0
    else:
        raise LedgerError(f"report missing: {args.report}")
    before = float(args.usage_before)
    after = float(args.usage_after)
    delta = after - before
    mismatch = abs(delta - report_cost) > MATCH_TOL_USD
    spend = max(delta, report_cost)
    record: dict[str, Any] = {
        "type": "call",
        "utc": iso_utc(now),
        "call": call.id,
        "cell": call.cell,
        "status": args.status,
        "usage_before": before,
        "usage_after": after,
        "report": args.report,
        "report_cost": report_cost,
        "delta": delta,
        "mismatch": mismatch,
        "spend": spend,
        "note": args.note,
    }
    if call.of is not None:
        record.update(
            {
                "of": call.of,
                "task": call.tasks[0],
                "repeat_index": call.repeat_index,
                "outcome": outcome,
            }
        )
    _with_totals(record, records)
    append_record(args.ledger, record)
    state = fold([*records, record])
    print(
        f"M19 total {state.m19_total:.6f} / {ALLOCATION_USD:.2f}; "
        f"paid total {state.paid_total:.6f} / {PAID_CAP_USD:.2f}; e total {state.e_total:.6f}"
    )
    failed = args.status == "failed"
    if mismatch:
        print(
            f"MISMATCH {call.id}: delta {delta:.6f} vs report cost {report_cost:.6f}; "
            "re-read /credits after >= 60 s and run settle"
        )
    if failed:
        print(f"FAILED {call.id}: root-cause, then resolve")
    return 1 if (mismatch or failed) else 0


def cmd_settle(args: argparse.Namespace, now: datetime) -> int:
    records = read_records(args.ledger)
    call = get_call(args.call)
    last = _latest_call_record(records, call.id)
    if last is None:
        raise LedgerError(f"no call record for {call.id}")
    delta = float(args.usage) - float(last["usage_before"])
    report_cost = float(last["report_cost"])
    mismatch = abs(delta - report_cost) > MATCH_TOL_USD
    record: dict[str, Any] = {
        "type": "settle",
        "utc": iso_utc(now),
        "call": call.id,
        "cell": call.cell,
        "usage": float(args.usage),
        "delta": delta,
        "mismatch": mismatch,
        "spend": max(delta, report_cost),
    }
    _with_totals(record, records)
    append_record(args.ledger, record)
    state = fold([*records, record])
    print(
        f"SETTLE {call.id}: delta {delta:.6f} vs report cost {report_cost:.6f}; "
        f"M19 total {state.m19_total:.6f}"
    )
    if mismatch:
        print(f"MISMATCH {call.id} still present")
    return 1 if mismatch else 0


def cmd_resolve(args: argparse.Namespace, now: datetime) -> int:
    records = read_records(args.ledger)
    call = get_call(args.call)
    if _latest_call_record(records, call.id) is None:
        raise LedgerError(f"no call record for {call.id}")
    record = {"type": "resolve", "utc": iso_utc(now), "call": call.id, "note": args.note}
    append_record(args.ledger, record)
    print(f"resolved {call.id}")
    return 0


def cmd_mark(args: argparse.Namespace, now: datetime) -> int:
    records = read_records(args.ledger)
    call = get_call(args.call)
    if _latest_call_record(records, call.id) is not None:
        raise LedgerError(f"{call.id} already has a call record")
    record = _status_record(call, args.status, args.reason, now, records)
    append_record(args.ledger, record)
    print(f"marked {call.id} {args.status}")
    return 0


def cmd_event(args: argparse.Namespace, now: datetime) -> int:
    record = {
        "type": "event",
        "utc": iso_utc(now),
        "kind": args.kind,
        "cell": args.cell,
        "note": args.note,
    }
    append_record(args.ledger, record)
    print(f"event {args.kind} recorded")
    return 0


def _fmt(value: Any, spec: str = ".6f") -> str:
    if value is None:
        return "—"
    return format(value, spec)


def _row_cells(call: Call, records: Sequence[dict[str, Any]]) -> list[str]:
    history = [r for r in records if r.get("call") == call.id]
    checks = [r for r in history if r["type"] == "check"]
    last_check = checks[-1] if checks else None
    call_recs = [r for r in history if r["type"] == "call"]
    call_rec = call_recs[-1] if call_recs else None
    row = next((r for r in reversed(history) if r["type"] in ("call", "settle")), None)
    plan = call.plan_total
    if plan is None and last_check is not None:
        plan = last_check["plan_total"]
    key = last_check["key_remaining"] if last_check else None
    balance = last_check["balance"] if last_check else None
    before = call_rec.get("usage_before") if call_rec else None
    after = None
    if row is not None:
        after = row.get("usage_after", row.get("usage"))
    report = call_rec.get("report") if call_rec else None
    report_cost = call_rec.get("report_cost") if call_rec else None
    delta = row.get("delta") if row else None
    m19 = row.get("m19_total") if row else None
    paid = row.get("paid_total") if row else None
    notes = [AMEND_NOTE[call.amended]] if call.amended else []
    if call_rec and call_rec.get("note"):
        notes.append(str(call_rec["note"]))
    return [
        _fmt(plan),
        _fmt(call.max_cost),
        _fmt(key),
        _fmt(balance),
        _fmt(before),
        _fmt(after),
        report or "—",
        _fmt(report_cost),
        _fmt(delta),
        _fmt(m19),
        _fmt(paid),
        "; ".join(notes),
    ]


def render_table(records: Sequence[dict[str, Any]]) -> str:
    state = fold(records)
    lines = [
        "### 호출",
        "",
        "| 호출 | 셀 | 상태 | 명령 | plan TOTAL | --max-cost | 키 잔액 | 계정 잔액 "
        "| /credits 전 | /credits 후 | 보고서 | 보고서 비용 | /credits 차이 | M19 누적 "
        "| 유료 누적 | 비고 |",
        "|" + "---|" * 16,
    ]
    for call in ALL_CALLS:
        status = state.status.get(call.id, "대기")
        cells = _row_cells(call, records)
        lines.append(
            f"| {call.id} | {call.cell} | {status} | `{call.command}` | " + " | ".join(cells) + " |"
        )
    lines += [
        "",
        "### 셀",
        "",
        "| 셀 | 예상 $ | 남은 배정 | 1.5× 필요 | 판정 |",
        "|---|---|---|---|---|",
    ]
    for cell in state.cells:
        lines.append(
            f"| {cell['cell']} | {_fmt(cell['expected'])} | {_fmt(cell['remaining'])} "
            f"| {_fmt(cell['needed'])} | {cell['decision']} |"
        )
    lines += ["", "### 이벤트", "", "| UTC | 종류 | 셀 | 내용 |", "|---|---|---|---|"]
    for event in state.events:
        lines.append(
            f"| {event['utc']} | {event['kind']} | {event.get('cell') or '—'} | {event['note']} |"
        )
    if RERUNS:
        lines += [
            "",
            "### 재실행",
            "",
            "| 재실행 | 원 호출 | 셀 | 과제 | 원 반복 | 상태 | 결과 | 명령 | plan TOTAL "
            "| --max-cost | 키 잔액 | 계정 잔액 | /credits 전 | /credits 후 | 보고서 "
            "| 보고서 비용 | /credits 차이 | M19 누적 | 유료 누적 | 비고 |",
            "|" + "---|" * 20,
        ]
        for rerun in RERUNS:
            status = state.status.get(rerun.id, "대기")
            call_rec = _latest_call_record(records, rerun.id)
            outcome = call_rec.get("outcome") if call_rec else None
            lines.append(
                f"| {rerun.id} | {rerun.of} | {rerun.cell} | {rerun.tasks[0]} "
                f"| {rerun.repeat_index} | {status} | {outcome or '—'} | `{rerun.command}` | "
                + " | ".join(_row_cells(rerun, records))
                + " |"
            )
    return "\n".join(lines)


def cmd_table(args: argparse.Namespace, now: datetime) -> int:
    print(render_table(read_records(args.ledger)))
    return 0


def cmd_plan_cmd(args: argparse.Namespace, now: datetime) -> int:
    print(plan_command(get_call(args.call)))
    return 0


def _report_path(out: str, root: str | None) -> str:
    base = Path(out).name
    if root:
        return str(Path(root) / f"{base}.json")
    return str(Path(out) / "report.json")


def cmd_panel_args(args: argparse.Namespace, now: datetime) -> int:
    records = read_records(args.ledger)
    state = fold(records)
    order: list[str] = []
    for record in records:
        if record["type"] == "call" and record["call"] not in order:
            order.append(record["call"])
    lines: list[str] = []
    for call_id in order:
        if state.status.get(call_id) != "executed":
            continue
        call = BY_ID[call_id]
        if call.of is not None:
            continue
        label = Path(call.out).name.split("-")[0]
        lines.append(f"{label}={_report_path(call.out, args.root)}")
    if args.d2:
        for model in args.d2.split(","):
            for index in ("04", "05"):
                out = f".cora/bench/m19/runs/a-{model}-i{index}"
                lines.append(f"d2@e2e_hx1,e2e_hx2={_report_path(out, args.root)}")
    print("\n".join(lines))
    return 0


def cmd_live_cmd(args: argparse.Namespace, now: datetime) -> int:
    print(get_call(args.call).command)
    return 0


def cmd_panel_extras(args: argparse.Namespace, now: datetime) -> int:
    records = read_records(args.ledger)
    state = fold(records)
    reruns = [
        {
            "id": rerun.id,
            "of": rerun.of,
            "task": rerun.tasks[0],
            "repeat_index": rerun.repeat_index,
            "orig_report": _report_path(BY_ID[str(rerun.of)].out, args.root),
            "rerun_report": _report_path(rerun.out, args.root),
            "status": state.status.get(rerun.id),
        }
        for rerun in RERUNS
    ]
    order: list[str] = []
    for record in records:
        if record["type"] == "call" and record["call"] not in order:
            order.append(record["call"])
    billed: list[dict[str, Any]] = []
    for call_id in order:
        if state.status.get(call_id) != "executed":
            continue
        call = BY_ID[call_id]
        call_rec = _latest_call_record(records, call_id)
        if call_rec is None:
            raise LedgerError(f"no call record for {call_id}")
        latest = [
            r for r in records if r.get("call") == call_id and r["type"] in ("call", "settle")
        ]
        report_cost = float(call_rec["report_cost"])
        billed.append(
            {
                "id": call_id,
                "report": _report_path(call.out, args.root),
                "report_cost": report_cost,
                "billed": max(float(latest[-1]["delta"]), report_cost),
            }
        )
    print(
        json.dumps(
            {"reruns": reruns, "billed": billed}, indent=2, sort_keys=True, ensure_ascii=False
        )
    )
    return 0


def _settings(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data["settings"])


def _render(value: Any) -> str:
    if value is ABSENT:
        return "absent"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _diff(key: str, a_value: Any, d1_value: Any, out: list[str]) -> None:
    if a_value != d1_value:
        out.append(f"DIFF {key}: a={_render(a_value)} d1={_render(d1_value)}")


def _task_entry(settings: dict[str, Any], task_id: str) -> Any:
    e2e = settings.get("e2e")
    if not isinstance(e2e, dict):
        return ABSENT
    for task in e2e.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return ABSENT


def _model_entry(settings: dict[str, Any], model_id: str | None) -> Any:
    for model in settings.get("models", []):
        if model.get("id") == model_id:
            return model
    return ABSENT


def d2_diffs(a: dict[str, Any], d1: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in D2_SETTINGS_KEYS:
        _diff(key, a.get(key, ABSENT), d1.get(key, ABSENT), out)
    a_e2e = a.get("e2e", ABSENT)
    d1_e2e = d1.get("e2e", ABSENT)
    _diff(
        "e2e",
        ABSENT if a_e2e is ABSENT else {k: v for k, v in a_e2e.items() if k != "tasks"},
        ABSENT if d1_e2e is ABSENT else {k: v for k, v in d1_e2e.items() if k != "tasks"},
        out,
    )
    for task_id in HARD_X:
        a_task = _task_entry(a, task_id)
        d1_task = _task_entry(d1, task_id)
        if a_task is not ABSENT and d1_task is not ABSENT:
            _diff(f"e2e.tasks[{task_id}]", a_task, d1_task, out)
    model_id = d1.get("ab", {}).get("model")
    _diff(f"models[{model_id}]", _model_entry(a, model_id), _model_entry(d1, model_id), out)
    return out


def cmd_d2check(args: argparse.Namespace, now: datetime) -> int:
    d1 = _settings(Path(args.d1))
    diffs: list[str] = []
    for path in args.a:
        diffs.extend(d2_diffs(_settings(Path(path)), d1))
    if diffs:
        print("\n".join(diffs))
        return 1
    print("MATCH")
    return 0


def cmd_earliest(args: argparse.Namespace, now: datetime) -> int:
    reports = sorted(Path(args.dir).glob("*/report.json"))
    if not reports:
        print(f"no reports under {args.dir}")
        return 1
    stamped: list[tuple[datetime, str, Path]] = []
    for path in reports:
        generated = json.loads(path.read_text(encoding="utf-8"))["generated_at"]
        stamped.append((parse_iso(generated), generated, path))
    _, generated, path = min(stamped, key=lambda item: item[0])
    print(f"{generated} {path}")
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--now", default=None)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="m19_ledger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add(name: str) -> argparse.ArgumentParser:
        child = sub.add_parser(name)
        _add_common(child)
        return child

    init = add("init")
    init.add_argument("--paid-total", type=float, required=True)
    init.add_argument("--usage", type=float, required=True)
    init.add_argument("--key-remaining", type=float, required=True)
    init.add_argument("--balance", type=float, required=True)
    init.add_argument("--head", required=True)
    init.add_argument("--confirmed", required=True)

    cell = add("cell")
    cell.add_argument("cell")

    check = add("check")
    check.add_argument("call")
    check.add_argument("--plan-total", type=float, required=True)
    check.add_argument("--key-remaining", type=float, required=True)
    check.add_argument("--balance", type=float, required=True)
    check.add_argument("--usage", type=float, required=True)

    record = add("record")
    record.add_argument("call")
    record.add_argument("--status", choices=("executed", "failed"), required=True)
    record.add_argument("--usage-before", type=float, required=True)
    record.add_argument("--usage-after", type=float, required=True)
    record.add_argument("--report", required=True)
    record.add_argument("--note", default=None)

    settle = add("settle")
    settle.add_argument("call")
    settle.add_argument("--usage", type=float, required=True)

    resolve = add("resolve")
    resolve.add_argument("call")
    resolve.add_argument("--note", required=True)

    mark = add("mark")
    mark.add_argument("call")
    mark.add_argument("--status", choices=("blocked", "not_measured"), required=True)
    mark.add_argument("--reason", required=True)

    event = add("event")
    event.add_argument("kind", choices=("amend", "checkpoint", "user", "deviation", "stop"))
    event.add_argument("--cell", default=None)
    event.add_argument("--note", required=True)

    add("table")

    plan_cmd = add("plan-cmd")
    plan_cmd.add_argument("call")

    panel = add("panel-args")
    panel.add_argument("--d2", default=None)
    panel.add_argument("--root", default=None)

    extras = add("panel-extras")
    extras.add_argument("--root", default=None)

    live = add("live-cmd")
    live.add_argument("call")

    d2 = add("d2check")
    d2.add_argument("--a", nargs="+", required=True)
    d2.add_argument("--d1", required=True)

    earliest = add("earliest")
    earliest.add_argument("dir")
    return parser


HANDLERS: dict[str, Callable[[argparse.Namespace, datetime], int]] = {
    "init": cmd_init,
    "cell": cmd_cell,
    "check": cmd_check,
    "record": cmd_record,
    "settle": cmd_settle,
    "resolve": cmd_resolve,
    "mark": cmd_mark,
    "event": cmd_event,
    "table": cmd_table,
    "plan-cmd": cmd_plan_cmd,
    "panel-args": cmd_panel_args,
    "panel-extras": cmd_panel_extras,
    "live-cmd": cmd_live_cmd,
    "d2check": cmd_d2check,
    "earliest": cmd_earliest,
}


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    now = parse_iso(args.now) if args.now else datetime.now(UTC)
    try:
        return HANDLERS[args.cmd](args, now)
    except LedgerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
