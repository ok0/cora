"""M25 live planning helper. Editor-run; not part of the product.

Free mode uses the gemini free tier. Paid mode is guarded (one segment, capped, no retry).
Only the orchestrator or the user runs the live modes. Every subcommand except `run`
and `account` makes no network call.

Usage (repo root):
    uv run python tests/m25_planq.py config OUT [--model M] [--paid] [--deadline]
        [--on goal_paths,plan_repair_hint]
    uv run python tests/m25_planq.py estimate --config CFG --tasks T1,T2 [--out JSONL]
    uv run python tests/m25_planq.py account --config CFG --segment S \
        --when before|after --out JSONL
    uv run python tests/m25_planq.py run TASK --label L --config CFG --root DIR \
        --planq-out JSONL --fixtures DIR [--attempts 5] [--repeat 1] [--paid --max-cost USD]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))

import m20_trial  # noqa: E402
import m25_diag  # noqa: E402
from cora.core.config import CoraConfig, load_config  # noqa: E402
from cora.core.planner import plan_messages, workspace_listing  # noqa: E402
from cora.core.policy import planning_policy  # noqa: E402
from cora.core.providers.openrouter import OpenRouterProvider  # noqa: E402
from cora.core.router import HeuristicRouter  # noqa: E402

ROOT = m20_trial.ROOT
FREE_MODEL = "gemini-3.5-flash-lite"
PAID_MODELS = ("deepseek/deepseek-v3.2",)
PAID_TASKS = ("e2e_h01", "e2e_h05")
PAID_CAP_SEGMENT_USD = 0.05
PAID_CAP_TOTAL_USD = 0.10
PAID_LABELS = ("deepseek-fix4-off", "deepseek-fix4-on")
PLANNING_ARGV = ("uv", "run", "cora", "project", "plan")
PAY_ERROR_RE = re.compile(r"\b402\b|Payment Required|insufficient credits", re.IGNORECASE)
OUT_TOK_BOUND = 12000
BACKOFF_S = (60, 120, 240, 480)
CHARS_PER_TOKEN = 3
REPLY_OVERHEAD_TOK = 1500
DEADLINE_OLD = ("timeout_s = 120", "request_deadline_s = 90", "call_timeout_s = 300")
DEADLINE_TIMEOUTS = (300, 300, 960)
ON_SECTIONS = {
    "goal_paths": "project",
    "plan_repair_hint": "project",
    "tripwire_per_response": "agent",
}
ENV_KEY = "OPENROUTER_API_KEY"

Runner = Callable[[list[str], dict[str, str]], dict[str, Any]]


def _line_match(line: str, prefix: str) -> bool:
    return re.match(rf"{re.escape(prefix)}(?=\s|#|$)", line) is not None


def _patch(lines: list[str], old: str, new: str) -> list[str]:
    idx = [i for i, line in enumerate(lines) if _line_match(line, old)]
    if len(idx) != 1:
        raise SystemExit(2)
    i = idx[0]
    lines[i] = new + lines[i][len(old) :]
    return lines


def _on_keys(on: str) -> list[str]:
    keys = [k for k in on.split(",") if k]
    if any(k not in ON_SECTIONS for k in keys):
        raise SystemExit(2)
    return keys


def _pinned(cfg: CoraConfig) -> Any:
    return HeuristicRouter(cfg).model_for(cfg.router.default)


def _verify_config(
    cfg: CoraConfig, model: str, *, paid: bool, deadline: bool, keys: Sequence[str]
) -> None:
    spec = _pinned(cfg)
    if spec.id != model:
        raise SystemExit(2)
    if paid:
        if spec.id not in PAID_MODELS or spec.provider != "openrouter":
            raise SystemExit(2)
    elif spec.provider != "gemini" or not spec.free_tier:
        raise SystemExit(2)
    if deadline:
        prov = cfg.providers["openrouter"]
        got = (
            prov.get("timeout_s"),
            prov.get("request_deadline_s"),
            cfg.agent.call_timeout_s,
        )
        if got != DEADLINE_TIMEOUTS:
            raise SystemExit(2)
    for key in ON_SECTIONS:
        value = getattr(getattr(cfg, ON_SECTIONS[key]), key)
        if value != (key in keys):
            raise SystemExit(2)


def config_cmd(out: Path, model: str, *, paid: bool, deadline: bool, on: str) -> str:
    keys = _on_keys(on)
    if paid and model not in PAID_MODELS:
        raise SystemExit(2)
    m20_trial.make_config(model, out)
    try:
        lines = out.read_text(encoding="utf-8").splitlines(keepends=True)
        if deadline:
            for old, new in zip(DEADLINE_OLD, m20_trial.DEADLINE_LINES, strict=True):
                lines = _patch(lines, old, new)
        for key in keys:
            lines = _patch(lines, f"{key} = false", f"{key} = true")
        out.write_text("".join(lines), encoding="utf-8")
        cfg = load_config(out)
        _verify_config(cfg, model, paid=paid, deadline=deadline, keys=keys)
    except SystemExit:
        out.unlink(missing_ok=True)
        raise
    return hashlib.sha256(out.read_bytes()).hexdigest()


def _plan_input_tokens(cfg: CoraConfig, task: str) -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        ws = m20_trial.prepare_ws(task, tmp / "ws")
        policy = planning_policy(cfg.policy, ws, "policy")
        rules = policy.rules_text() if policy is not None else None
        files = workspace_listing(ws) if cfg.project.goal_paths else None
        msgs = plan_messages(
            m20_trial.goal_text(task),
            m20_trial.PLAN_MAX_MILESTONES,
            policy_rules=rules,
            workspace_files=files,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    chars = sum(len(m.content) for m in msgs)
    return math.ceil(chars / CHARS_PER_TOKEN) + REPLY_OVERHEAD_TOK


def estimate_doc(cfg: CoraConfig, tasks: Sequence[str]) -> dict[str, Any]:
    spec = _pinned(cfg)
    in_price = spec.input_usd_per_mtok or 0.0
    out_price = spec.output_usd_per_mtok or 0.0
    calls = 2 + cfg.project.policy_repairs
    per_task: dict[str, dict[str, Any]] = {}
    for task in tasks:
        in_tok = _plan_input_tokens(cfg, task)
        worst = calls * (in_tok * in_price + OUT_TOK_BOUND * out_price) / 1e6
        per_task[task] = {
            "calls": calls,
            "in_tok": in_tok,
            "out_tok": OUT_TOK_BOUND,
            "worst_usd": worst,
        }
    segment = sum(v["worst_usd"] for v in per_task.values())
    return {"model": spec.id, "per_task": per_task, "segment_worst_usd": segment}


def estimate_cmd(cfg_path: Path, tasks: Sequence[str], out: Path | None) -> int:
    doc = estimate_doc(load_config(cfg_path), tasks)
    line = json.dumps(doc, sort_keys=True)
    print(line)
    if out is not None:
        _append(out, doc)
    return 2 if doc["segment_worst_usd"] > PAID_CAP_SEGMENT_USD else 0


def _data(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return {}


def account_cmd(
    cfg_path: Path,
    segment: str,
    when: str,
    out: Path,
    *,
    transport: Any = None,
) -> int:
    cfg = load_config(cfg_path)
    settings = cfg.providers["openrouter"]
    env_name = settings.get("api_key_env", ENV_KEY)
    if not os.environ.get(env_name):
        print(f"{env_name} is not set", file=sys.stderr)
        return 2
    provider = OpenRouterProvider(settings, transport=transport)

    async def fetch() -> list[tuple[str, int, Any]]:
        got: list[tuple[str, int, Any]] = []
        for path in ("/auth/key", "/credits"):
            status, body = await provider.account_get(path)
            got.append((path, status, body))
        return got

    results = asyncio.run(fetch())
    for path, status, _ in results:
        if status != 200:
            print(f"HTTP {status} from {path}", file=sys.stderr)
            return 3
    key = _data(results[0][2])
    credits = _data(results[1][2])
    row = {
        "ts": datetime.now(UTC).isoformat(),
        "segment": segment,
        "when": when,
        "key_usage": key.get("usage"),
        "key_limit": key.get("limit"),
        "key_limit_remaining": key.get("limit_remaining"),
        "key_expires_at": key.get("expires_at"),
        "total_credits": credits.get("total_credits"),
        "total_usage": credits.get("total_usage"),
    }
    _append(out, row)
    return 0


def plan_argv(goal: str, out: Path, cfg: Path, ws: Path) -> list[str]:
    return [
        *PLANNING_ARGV,
        goal,
        "-o",
        str(out),
        "--approval",
        "policy",
        "--json",
        "--config",
        str(cfg),
        "--workdir",
        str(ws),
    ]


def _default_runner(argv: list[str], env: dict[str, str]) -> dict[str, Any]:
    proc = subprocess.run(argv, env=env, capture_output=True, text=True, cwd=ROOT, check=False)
    try:
        outcome = json.loads(proc.stdout)
    except json.JSONDecodeError:
        outcome = {"ok": False, "errors": [f"no JSON outcome (exit {proc.returncode})"]}
    outcome.setdefault("exit_code", proc.returncode)
    return outcome


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _cost(row: dict[str, Any], max_cost: float) -> float:
    cost = row.get("cost_usd")
    return max_cost if cost is None else float(cost)


def _copy_text(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(
        m25_diag.clean(src.read_text(encoding="utf-8", errors="replace")), encoding="utf-8"
    )


def _key_hits(dest: Path) -> list[Path]:
    values = [os.environ[v] for v in m20_trial.KEY_ENV_VARS if len(os.environ.get(v, "")) >= 6]
    hits: list[Path] = []
    for p in sorted(dest.rglob("*")):
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if any(rx.search(text) for rx in m20_trial.KEY_SCAN_RES) or any(v in text for v in values):
            hits.append(p)
    return hits


def _collect(
    dest: Path,
    plan_out: Path,
    records: Path,
    ws: Path,
    attempt_rows: list[dict[str, Any]],
    refcheck_rows: list[dict[str, Any]] | None,
) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if refcheck_rows is not None:
        m25_diag._write_jsonl(dest / "refcheck.jsonl", refcheck_rows)
    if plan_out.is_file():
        _copy_text(plan_out, dest / "plan.toml")
    if records.is_dir():
        for p in sorted(records.rglob("*")):
            if p.is_file():
                _copy_text(p, dest / "records" / p.relative_to(records))
    events = ws / ".cora" / "planner" / "events.jsonl"
    if events.is_file():
        _copy_text(events, dest / "events.jsonl")
    m25_diag._write_jsonl(dest / "attempts.jsonl", attempt_rows)


def _budget_ok(rows: list[dict[str, Any]], label: str, worst: float, max_cost: float) -> bool:
    spent = sum(_cost(r, max_cost) for r in rows if r.get("label") == label)
    if spent + worst > max_cost:
        return False
    spent_all = sum(_cost(r, max_cost) for r in rows if r.get("label") in PAID_LABELS)
    return spent_all + worst <= PAID_CAP_TOTAL_USD


def run_cmd(
    task: str,
    label: str,
    cfg_path: Path,
    root: Path,
    planq_out: Path,
    fixtures: Path,
    *,
    attempts: int,
    repeat: int,
    paid: bool,
    max_cost: float | None,
    runner: Runner | None = None,
    sleep: Callable[[float], None] | None = None,
) -> int:
    run = runner or _default_runner
    wait = sleep or time.sleep
    cfg = load_config(cfg_path)
    spec = _pinned(cfg)
    if paid:
        if spec.id not in PAID_MODELS or spec.provider != "openrouter":
            return 2
        if task not in PAID_TASKS or label not in PAID_LABELS:
            return 2
        if max_cost is None or not 0 < max_cost <= PAID_CAP_SEGMENT_USD:
            return 2
        if repeat != 1 or attempts != 1:
            return 2
        if not os.environ.get(ENV_KEY):
            return 2
        env = dict(os.environ)
        worst = estimate_doc(cfg, [task])["per_task"][task]["worst_usd"]
        if not _budget_ok(_read_rows(planq_out), label, worst, max_cost):
            return 3
    else:
        if spec.provider != "gemini" or not spec.free_tier:
            return 2
        env = {k: v for k, v in os.environ.items() if k != ENV_KEY}
    cfg_abs = cfg_path.resolve()
    goal = m20_trial.goal_text(task)
    for k in range(repeat):
        base = root / f"{task}-{k}"
        ws = m20_trial.prepare_ws(task, base / "ws")
        records = base / "records"
        plan_out = base / "plan.toml"
        argv = plan_argv(goal, plan_out, cfg_abs, ws)
        run_env = {**env, "CORA_RECORD_MODE": "record", "CORA_RECORD_DIR": str(records)}
        task_attempts: list[dict[str, Any]] = []
        outcome: dict[str, Any] = {}
        used = 0
        blocked = False
        for attempt in range(1, attempts + 1):
            assert tuple(argv[:5]) == PLANNING_ARGV
            outcome = run(argv, run_env)
            used = attempt
            err = m20_trial._error_text(outcome)
            blocked = not outcome.get("ok") and bool(m20_trial.PLAN_ERROR_RE.search(err))
            entry = {
                "task": task,
                "k": k,
                "attempt": attempt,
                "ts": datetime.now(UTC).isoformat(),
                "exit_code": outcome.get("exit_code"),
                "blocked": blocked,
                "error_head": err[:200],
            }
            task_attempts.append(entry)
            _append(root / "attempts.jsonl", entry)
            if not blocked or paid or attempt == attempts:
                break
            wait(BACKOFF_S[attempt - 1])
        err = m20_trial._error_text(outcome)
        row = m20_trial.planq_row(task, outcome, plan_out, records, label, cfg_abs)
        if not outcome.get("ok") and blocked and used == attempts and not paid:
            row["plan_quality"] = "blocked"
            row["attempts"] = used
        stop = bool(paid and not outcome.get("ok") and not err.startswith("planner reply invalid"))
        if stop:
            row["plan_quality"] = "blocked"
        _append(planq_out, row)
        refcheck_rows = (
            m25_diag.refcheck_details(task, plan_out, cfg_abs) if outcome.get("ok") else None
        )
        dest = fixtures / f"{task}-{k}"
        _collect(dest, plan_out, records, ws, task_attempts, refcheck_rows)
        hits = _key_hits(dest)
        if hits:
            for p in hits:
                p.unlink()
                print(str(p))
            return 6
        if stop:
            return 5 if PAY_ERROR_RE.search(err) else 4
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M25 live planning helper.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("config")
    s.add_argument("out", type=Path)
    s.add_argument("--model", default=FREE_MODEL)
    s.add_argument("--paid", action="store_true")
    s.add_argument("--deadline", action="store_true")
    s.add_argument("--on", default="")
    s = sub.add_parser("estimate")
    s.add_argument("--config", type=Path, required=True)
    s.add_argument("--tasks", required=True)
    s.add_argument("--out", type=Path, default=None)
    s = sub.add_parser("account")
    s.add_argument("--config", type=Path, required=True)
    s.add_argument("--segment", required=True)
    s.add_argument("--when", choices=("before", "after"), required=True)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("run")
    s.add_argument("task")
    s.add_argument("--label", required=True)
    s.add_argument("--config", type=Path, required=True)
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--planq-out", type=Path, required=True)
    s.add_argument("--fixtures", type=Path, required=True)
    s.add_argument("--attempts", type=int, default=5)
    s.add_argument("--repeat", type=int, default=1)
    s.add_argument("--paid", action="store_true")
    s.add_argument("--max-cost", type=float, default=None)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runner: Runner | None = None,
    sleep: Callable[[float], None] | None = None,
    transport: Any = None,
) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.cmd == "config":
            print(
                config_cmd(
                    args.out,
                    args.model,
                    paid=args.paid,
                    deadline=args.deadline,
                    on=args.on,
                )
            )
            return 0
        if args.cmd == "estimate":
            tasks = [t for t in args.tasks.split(",") if t]
            return estimate_cmd(args.config, tasks, args.out)
        if args.cmd == "account":
            return account_cmd(args.config, args.segment, args.when, args.out, transport=transport)
        if args.cmd == "run":
            return run_cmd(
                args.task,
                args.label,
                args.config,
                args.root.resolve(),
                args.planq_out,
                args.fixtures,
                attempts=args.attempts,
                repeat=args.repeat,
                paid=args.paid,
                max_cost=args.max_cost,
                runner=runner,
                sleep=sleep,
            )
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
