from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cora.bench import e2e, live
from cora.bench.live_tasks import MULTI_TASKS, write_task_files

TASK_IDS: tuple[str, ...] = (
    "query_client_timeout",
    "query_total_backoff",
    "query_env_override",
    "multi_edit_delay_cap",
    "multi_edit_rename_cents",
    "multi_edit_region",
    "e2e_todo_cli",
    "e2e_text_stats",
    "e2e_rest_notes",
    "e2e_md_to_html",
    "e2e_refactor_inventory",
)

_MULTI_BY_ID = {t.id: t for t in MULTI_TASKS}

HIDDEN_ENV = frozenset({"OPENROUTER_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"})

ROOT_NAME = Path(__file__).resolve().parents[1].name

FORBIDDEN_DEFAULT: tuple[str, ...] = (
    ROOT_NAME,
    ".ensemble",
    ".docs/",
    "e2e_tasks",
    "exploration.json",
    "/reference/",
)

PRICE_SOURCE = "m15-readiness (4), pricing doc S3, fetched 2026-10-15"

PRICES: dict[str, dict[str, float]] = {
    "sonnet": {"in": 2, "cache_write": 2.50, "cache_read": 0.10, "out": 10},
    "opus": {"in": 4, "cache_write": 5, "cache_read": 0.20, "out": 20},
    "haiku": {"in": 0.10, "cache_write": 0.125, "cache_read": 0.01, "out": 0.50},
}

FAMILIES = ("opus", "sonnet", "haiku")

USAGE_FIELDS = (
    "inputTokens",
    "outputTokens",
    "cacheReadInputTokens",
    "cacheCreationInputTokens",
    "costUSD",
    "costBasis",
)


def _e2e_task(task_id: str) -> e2e.E2ETask:
    return e2e.select_e2e_tasks([task_id])[0]


def task_prompt(task_id: str) -> str:
    if task_id in _MULTI_BY_ID:
        return _MULTI_BY_ID[task_id].prompt
    return e2e.agent_prompt(_e2e_task(task_id))


def prepare(task_id: str, dest: Path) -> Path:
    if dest.exists():
        raise ValueError(f"destination already exists: {dest}")
    dest.mkdir(parents=True)
    if task_id in _MULTI_BY_ID:
        ws = dest / "ws"
        write_task_files(ws, _MULTI_BY_ID[task_id].files)
    else:
        ws = e2e.prepare_workspace(_e2e_task(task_id), dest)
    (dest / "prompt.txt").write_text(task_prompt(task_id), encoding="utf-8")
    return ws


def grade(task_id: str, ws: Path, answer: str | None, scratch: Path) -> dict:
    if task_id in _MULTI_BY_ID:
        ok, detail = asyncio.run(live.check_task(_MULTI_BY_ID[task_id], ws, answer, HIDDEN_ENV))
        return {"solved": ok, "score": 1.0 if ok else 0.0, "detail": detail[-300:]}
    g = e2e.run_grader(_e2e_task(task_id), ws, scratch)
    return {"solved": g.full_pass, "score": g.score, "detail": g.reason or ""}


def recompute_cost(model_usage: Mapping[str, Mapping[str, Any]]) -> tuple[float | None, list[str]]:
    total = 0.0
    notes: list[str] = []
    for model, u in model_usage.items():
        lowered = model.lower()
        family = next((f for f in FAMILIES if f in lowered), None)
        if family is None:
            return None, [f"no price for {model}"]
        p = PRICES[family]
        inp = u.get("inputTokens") or 0
        out = u.get("outputTokens") or 0
        cache_read = u.get("cacheReadInputTokens") or 0
        cache_write = u.get("cacheCreationInputTokens") or 0
        total += (
            inp * p["in"]
            + cache_write * p["cache_write"]
            + cache_read * p["cache_read"]
            + out * p["out"]
        ) / 1e6
        if family == "haiku" and inp + cache_read + cache_write > 100_000:
            notes.append("haiku >100k tier not applied (unverified rule)")
    return total, notes


def run_record(
    task_id: str,
    repeat: int,
    cc: dict,
    graded: dict,
    wall_s: float,
    *,
    dry_run: bool,
) -> dict:
    usage_raw: Mapping[str, Mapping[str, Any]] = cc.get("modelUsage") or {}
    model_usage = {m: {k: u[k] for k in USAGE_FIELDS if k in u} for m, u in usage_raw.items()}
    cost, notes = recompute_cost(usage_raw)
    return {
        "task": task_id,
        "repeat": repeat,
        "solved": bool(graded["solved"]),
        "score": graded["score"],
        "total_cost_usd": cc.get("total_cost_usd"),
        "cost_recomputed_usd": cost,
        "cost_notes": notes,
        "model_usage": model_usage,
        "model": "+".join(usage_raw),
        "wall_s": wall_s,
        "session_id": cc.get("session_id"),
        "num_turns": cc.get("num_turns"),
        "is_error": cc.get("is_error"),
        "subtype": cc.get("subtype"),
        "json_keys": sorted(cc),
        "dry_run": dry_run,
    }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def to_baseline_toml(
    records: Sequence[dict],
    *,
    model: str,
    date: str,
    source: str,
    dry_run: bool,
) -> str:
    selected = [r for r in records if r["dry_run"] == dry_run]
    full_source = f"DRY-RUN (not counted): {source}" if dry_run else source
    lines = [
        "[meta]",
        'tool = "claude-code"',
        f"model = {json.dumps(model)}",
        f"date = {json.dumps(date)}",
        f"source = {json.dumps(full_source)}",
        "synthetic = false",
        "",
    ]
    task_ids = [*TASK_IDS, *sorted({r["task"] for r in selected} - set(TASK_IDS))]
    for tid in task_ids:
        rs = [r for r in selected if r["task"] == tid]
        if not rs:
            continue
        n = len(rs)
        k = sum(1 for r in rs if r["solved"])
        fallback = False
        recomputed = [r["cost_recomputed_usd"] for r in rs]
        if all(c is not None for c in recomputed):
            cost = _mean(recomputed)
        else:
            totals = [r["total_cost_usd"] for r in rs]
            if any(t is None for t in totals):
                raise ValueError(f"no cost for task {tid}")
            cost = _mean(totals)
            fallback = True
        wall = _mean([r["wall_s"] for r in rs])
        if dry_run:
            note = "dry-run, not counted"
        else:
            reported = [r["total_cost_usd"] for r in rs if r["total_cost_usd"] is not None]
            reported_text = f"{_mean(reported):.4f}" if reported else "n/a"
            if fallback:
                note = (
                    f"reported total_cost_usd mean ${reported_text} used as cost_usd "
                    f"(recompute unavailable; {PRICE_SOURCE})"
                )
            else:
                note = (
                    f"recomputed from modelUsage ({PRICE_SOURCE}); reported mean ${reported_text}"
                )
        lines += [
            f"[tasks.{tid}]",
            f"solved = {json.dumps(k / n)}",
            f"cost_usd = {json.dumps(float(cost))}",
            f"wall_s = {json.dumps(float(wall))}",
            f"n = {n}",
            f"note = {json.dumps(note)}",
            "",
        ]
    return "\n".join(lines)


def audit(transcript: Path, forbidden: Sequence[str]) -> list[str]:
    hits: list[str] = []
    text = transcript.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        for sub in forbidden:
            idx = line.find(sub)
            if idx < 0:
                continue
            start = max(0, idx - 40)
            excerpt = line[start : start + 80].replace("\r", "\\r").replace("\n", "\\n")
            hits.append(f"line {i}: {sub}: {excerpt}")
    return hits


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m15_baseline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit")
    p_audit.add_argument("transcript", type=Path)
    p_audit.add_argument("--forbid", action="append", default=None)

    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("task")
    p_prepare.add_argument("dest", type=Path)

    p_grade = sub.add_parser("grade")
    p_grade.add_argument("task")
    p_grade.add_argument("ws", type=Path)
    p_grade.add_argument("--cc-json", type=Path, required=True)
    p_grade.add_argument("--repeat", type=int, required=True)
    p_grade.add_argument("--wall-s", type=float, required=True)
    p_grade.add_argument("--log", type=Path, required=True)
    p_grade.add_argument("--dry-run", action="store_true")

    p_toml = sub.add_parser("toml")
    p_toml.add_argument("runs", type=Path)
    p_toml.add_argument("--model", required=True)
    p_toml.add_argument("--date", required=True)
    p_toml.add_argument("--source", required=True)
    p_toml.add_argument("--out", type=Path, required=True)
    p_toml.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "audit":
        if not args.transcript.is_file():
            print(f"transcript not found: {args.transcript}", file=sys.stderr)
            return 2
        forbidden = tuple(args.forbid) if args.forbid else FORBIDDEN_DEFAULT
        hits = audit(args.transcript, forbidden)
        for hit in hits:
            print(hit)
        if not hits:
            print("clean")
            return 0
        return 1
    if args.cmd == "prepare":
        print(prepare(args.task, args.dest))
        return 0
    if args.cmd == "grade":
        cc = json.loads(args.cc_json.read_text(encoding="utf-8"))
        graded = grade(args.task, args.ws, cc.get("result"), args.ws.parent / "grade")
        rec = run_record(args.task, args.repeat, cc, graded, args.wall_s, dry_run=args.dry_run)
        with args.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(str(graded["solved"]).lower())
        return 0
    records = [
        json.loads(line)
        for line in args.runs.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    text = to_baseline_toml(
        records, model=args.model, date=args.date, source=args.source, dry_run=args.dry_run
    )
    args.out.write_text(text, encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
