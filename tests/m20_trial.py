from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import statistics
import sys
import tempfile
import tomllib
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from cora.bench import e2e
from cora.bench.stats import wilson_interval
from cora.core.agent import Agent
from cora.core.config import find_model, load_config
from cora.core.milestones import DONE_STATUS, Condition, load_plan, run_condition
from cora.core.planner import plan_from_text
from cora.core.policy import approval_mode_of
from cora.core.router import HeuristicRouter
from cora.core.shellguard import home_protected, package_data_dirs
from cora.core.tools import ApprovalPolicy
from e2e_trial_util import grade, leakcheck, prepare  # noqa: E402
from m20a_artifacts import KEY_RES as M20A_KEY_RES  # noqa: E402
from m20a_artifacts import _sanitize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / ".cora" / "m20"
PLAN_MAX_MILESTONES = 8
PLAN_ERROR_RE = re.compile(r"503|UNAVAILABLE|overloaded", re.IGNORECASE)
TIMEOUT_MARKER = "timeout after"
SKIP_DIRS = frozenset({".git", ".venv", "__pycache__", "node_modules"})
PRE_REGISTERED_TASKS = ("e2e_h01", "e2e_h03", "e2e_n08")
DEADLINE_TOML = ROOT / "tests/fixtures/m19/arms/deadline.toml"
M20_BASE = ROOT / "tests/fixtures/m20/cora-m20-base.toml"
VARIANTS = ("base", "deadline")
DEADLINE_LINES = ("timeout_s = 300", "request_deadline_s = 300", "call_timeout_s = 960")
PRE_FIX_LABELS = ("gemini-rehearsal", "deepseek")
FIX_ROUNDS = {"-fix1": "R11 round 1", "-fix2": "R11 round 2"}
MAIN_RUN_LABEL = "deepseek-v2"
RUN_LABEL_NOTES = {
    "deepseek": (
        "30/2400 attempt, pre-fix planner prompt, base config "
        "(r2 rerun under deadline config)"
    ),
    "deepseek-v2": (
        "main series: deadline config, project caps, post-fix planner prompt "
        "(R11 rounds 1-2)"
    ),
}
M20D_LABEL = "m20d-deepseek-v2"
PRE_REGISTERED_LABELS = (MAIN_RUN_LABEL, M20D_LABEL)
M20D_RUNS = ("e2e_n08-r0", "e2e_n08-r1", "e2e_n08-r2", "e2e_h03-r0", "e2e_h03-r1")
M20D_REHEARSALS = ("e2e_n08", "e2e_h03")
UNMETERED_RE = re.compile(r"RequestDeadlineExceeded|provider_timeout|ReadTimeout")
# M20d registered cap_bound threshold, kept only for `cap_bound_m20d` (dated correction)
M20D_CAP_COST = 0.29
KEY_SCAN_RES = (
    *M20A_KEY_RES,
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)authorization\W{0,4}(?:bearer\s+)?[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
)
KEY_ENV_VARS = ("OPENROUTER_API_KEY", "GEMINI_API_KEY")
PLACEHOLDER_M20D = "<M20D>"


def _task(task_id: str) -> e2e.E2ETask:
    return e2e.select_e2e_tasks([task_id])[0]


def _under_root(p: Path) -> bool:
    try:
        p.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    return True


M20B_POLICY_BLOCK = (
    "\n[policy]                 "
    "# cora.toml-only switch; policy rules live in .cora/policy.toml (USAGE.md, 자율 승인 정책)\n"
    "prompt_rules = false     "
    "# true: with an active policy gate, append the rendered shell-policy rules to the agent "
    "system prompt (OFF until a paid A/B shows a gain)\n"
)


def m20_base_text() -> str:
    return M20_BASE.read_text(encoding="utf-8")


def _variant_lines(variant: str) -> list[str]:
    if variant == "base":
        return (ROOT / "cora.toml").read_text(encoding="utf-8").splitlines(keepends=True)
    base = m20_base_text().splitlines(keepends=True)
    dl = DEADLINE_TOML.read_text(encoding="utf-8").splitlines(keepends=True)
    if len(dl) != len(base):
        raise SystemExit(2)
    diff = [i for i, (a, b) in enumerate(zip(base, dl, strict=True)) if a != b]
    if len(diff) != len(DEADLINE_LINES):
        raise SystemExit(2)
    for i, prefix in zip(diff, DEADLINE_LINES, strict=True):
        if not dl[i].strip().startswith(prefix):
            raise SystemExit(2)
    return dl + M20B_POLICY_BLOCK.splitlines(keepends=True)


def make_config(model: str, out: Path, variant: str = "base", prompt_rules: bool = False) -> str:
    if variant not in VARIANTS:
        raise SystemExit(2)
    if _under_root(out):
        raise SystemExit(2)
    lines = _variant_lines(variant)
    idx = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == "[router]"]
    if len(idx) != 1:
        raise SystemExit(2)
    lines.insert(idx[0] + 1, f'pin = "{model}"   # M20: single pinned model\n')
    if prompt_rules:
        flips = [i for i, line in enumerate(lines) if line.startswith("prompt_rules = false")]
        if len(flips) != 1:
            raise SystemExit(2)
        lines[flips[0]] = lines[flips[0]].replace("prompt_rules = false", "prompt_rules = true", 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(lines), encoding="utf-8")
    cfg = load_config(out)
    if cfg.policy.prompt_rules is not prompt_rules:
        out.unlink(missing_ok=True)
        raise SystemExit(2)
    if find_model(cfg.models, model) is None or (
        HeuristicRouter(cfg).model_for(cfg.router.default).id != model
    ):
        out.unlink(missing_ok=True)
        raise SystemExit(2)
    if variant == "deadline":
        prov = cfg.providers["openrouter"]
        if (
            prov.get("timeout_s") != 300
            or prov.get("request_deadline_s") != 300
            or cfg.agent.call_timeout_s != 960
        ):
            out.unlink(missing_ok=True)
            raise SystemExit(2)
    return hashlib.sha256(out.read_bytes()).hexdigest()


def goal_text(task_id: str) -> str:
    task = _task(task_id)
    requirements = task.requirements_path.read_text(encoding="utf-8")
    return (
        "Build the project described in REQUIREMENTS.md in the current directory "
        "(its full text is below). Required files: "
        f"{', '.join(task.required_files)}. Work only inside this directory.\n\n"
        "--- REQUIREMENTS.md ---\n" + requirements
    )


def prepare_ws(task_id: str, d: Path) -> Path:
    if not d.is_absolute() or _under_root(d):
        raise SystemExit(2)
    d.mkdir(parents=True, exist_ok=True)
    return prepare(task_id, d)


def planner_calls(records: Path) -> list[dict]:
    entries: list[dict] = []
    for p in sorted(records.rglob("*.json")):
        if p.name.startswith("."):
            continue
        entries.append(json.loads(p.read_text(encoding="utf-8")))
    entries.sort(key=lambda e: len(e["request"]["messages"]))
    return entries


def _command_verdict(c: Condition, agent: Agent) -> tuple[bool, bool, bool]:
    gate = agent.ctx.gate
    verdict = (
        gate.check("run_shell", {"command": c.cmd}, approval_mode_of(agent.ctx.approval))
        if gate is not None
        else None
    )
    blocked = verdict is not None and verdict.blocked
    if blocked:
        return True, False, False
    ok, out = asyncio.run(run_condition(c, agent.ctx, timeout_s=60, max_chars=2000))
    executable = (
        not out.startswith(("denied:", "invalid command:", "error:"))
        and "command not found" not in out
        and TIMEOUT_MARKER not in out
    )
    return blocked, ok, executable


def check_conditions(task_id: str, plan_path: Path, config_path: Path) -> dict:
    tmp = Path(tempfile.mkdtemp())
    try:
        task = _task(task_id)
        ws = e2e.prepare_workspace(task, tmp)
        e2e.apply_reference(task, ws)
        cfg = load_config(config_path)
        agent = Agent(cfg, ws, ApprovalPolicy("policy"))
        details: list[dict] = []
        check_details: list[dict] = []
        for m in load_plan(plan_path).milestones:
            for c in m.conditions:
                if c.kind == "command":
                    blocked, ok, executable = _command_verdict(c, agent)
                else:
                    blocked = False
                    executable = True
                    ok, _ = asyncio.run(run_condition(c, agent.ctx, timeout_s=60, max_chars=2000))
                details.append(
                    {
                        "milestone": m.id,
                        "condition": c.describe(),
                        "blocked": blocked,
                        "executable": executable,
                        "pass_ref": ok,
                    }
                )
            if m.check is not None:
                blocked, ok, executable = _command_verdict(
                    Condition(kind="command", cmd=m.check), agent
                )
                check_details.append(
                    {
                        "milestone": m.id,
                        "check": m.check,
                        "blocked": blocked,
                        "runnable": executable,
                        "pass_ref": ok,
                    }
                )
        total = len(details)
        n_exec = sum(d["executable"] for d in details)
        n_pass = sum(d["pass_ref"] for d in details)
        checks_total = len(check_details)
        check_runnable = sum(d["runnable"] for d in check_details)
        return {
            "conditions_total": total,
            "conditions_executable": n_exec,
            "conditions_pass_ref": n_pass,
            "all_executable": n_exec == total,
            "all_pass_ref": n_pass == total,
            "conditions_blocked": sum(d["blocked"] for d in details),
            "details": details,
            "checks_total": checks_total,
            "check_runnable": check_runnable,
            "checks_blocked": sum(d["blocked"] for d in check_details),
            "checks_pass_ref": sum(d["pass_ref"] for d in check_details),
            "all_checks_runnable": check_runnable == checks_total,
            "check_details": check_details,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def checkq_row(task_id: str, plan_path: Path, config_path: Path, label: str) -> dict:
    checked = check_conditions(task_id, plan_path, config_path)
    return {
        "task": task_id,
        "label": label,
        "checks_total": checked["checks_total"],
        "check_runnable": checked["check_runnable"],
        "checks_blocked": checked["checks_blocked"],
        "checks_pass_ref": checked["checks_pass_ref"],
        "all_checks_runnable": checked["all_checks_runnable"],
    }


def _error_text(outcome: dict) -> str:
    errs = list(outcome.get("errors") or [])
    if outcome.get("error"):
        errs.append(str(outcome["error"]))
    return "; ".join(errs)


def planq_row(
    task_id: str,
    outcome: dict,
    plan_path: Path,
    records: Path,
    label: str,
    config_path: Path,
) -> dict:
    entries = planner_calls(records)
    calls = len(entries)
    pp = outcome.get("plan_policy")
    rounds = pp["rounds"] if pp else 0
    schema_calls = calls - rounds
    ok = bool(outcome["ok"])
    err = _error_text(outcome)
    if ok and schema_calls == 1:
        quality: str | None = "first_try"
    elif ok and schema_calls == 2:
        quality = "after_repair"
    elif not ok and PLAN_ERROR_RE.search(err):
        quality = "blocked"
    elif not ok:
        quality = "invalid"
    else:
        quality = None
    strict: bool | None = None
    if entries:
        try:
            plan_from_text(
                entries[0]["response"]["text"], max_milestones=PLAN_MAX_MILESTONES, lenient=False
            )
            strict = True
        except Exception:
            strict = False
    cond: dict[str, Any] = {
        "conditions_total": None,
        "conditions_executable": None,
        "conditions_pass_ref": None,
        "all_executable": None,
        "all_pass_ref": None,
        "conditions_blocked": None,
        "checks_total": None,
        "check_runnable": None,
        "checks_blocked": None,
        "checks_pass_ref": None,
        "all_checks_runnable": None,
    }
    if ok:
        checked = check_conditions(task_id, plan_path, config_path)
        cond = {k: checked[k] for k in cond}
    return {
        "task": task_id,
        "label": label,
        "model": (outcome.get("models") or [None])[0],
        "ok": ok,
        "exit_code": outcome.get("exit_code"),
        "stop_reason": outcome.get("stop_reason"),
        "cost_usd": outcome.get("cost_usd"),
        "planner_calls": calls,
        "plan_quality": quality,
        "first_reply_strict": strict,
        "milestones": outcome.get("milestone_count") if ok else None,
        **cond,
        "policy_issues": pp["issues"] if pp else None,
        "policy_repaired": pp["repaired"] if pp else None,
        "policy_dropped": pp["dropped"] if pp else None,
        "policy_rounds": pp["rounds"] if pp else None,
        "policy_first_try": pp["issues"] == 0 if pp else None,
        "ungated": list(pp["ungated"]) if pp else None,
        "error": err or None,
    }


def milestones_done(milestones: list[dict]) -> int:
    return sum(1 for m in milestones if m.get("status") == DONE_STATUS)


def event_hits(ws: Path) -> list[str]:
    needles = [str(p) for p in home_protected() + package_data_dirs()]
    hits: list[str] = []
    for f in sorted(ws.glob(".cora/projects/*/events.jsonl")):
        for lineno, line in enumerate(
            f.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if any(n in line for n in needles):
                hits.append(f"{f.parent.name}/events.jsonl:{lineno}")
    return hits


def cora_dir(run_dir: Path) -> Path:
    cdir = run_dir / "ws" / ".cora"
    return cdir if cdir.is_dir() else run_dir


def read_jsonl_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def project_events(cdir: Path, run_id: str | None) -> list[dict]:
    if not run_id:
        return []
    return read_jsonl_lines(cdir / "projects" / run_id / "events.jsonl")


def plan_quality_of(planning: dict, errors: list[str]) -> str | None:
    if any("planner reply invalid" in e for e in errors):
        return "failed"
    calls = planning.get("calls")
    if calls is None:
        return None
    rounds = (planning.get("policy") or {}).get("rounds") or 0
    return {1: "first_try", 2: "after_repair"}.get(calls - rounds)


def policy_columns(outcome: dict, planning: dict) -> dict:
    pol = planning.get("policy") or {}
    return {
        "policy_dropped": pol.get("dropped") if "dropped" in pol else None,
        "policy_rounds": pol.get("rounds"),
        "ungated": outcome.get("ungated_milestones", pol.get("ungated")),
    }


def cap_columns(outcome: dict) -> dict:
    tripped = (outcome.get("budget") or {}).get("tripped")
    return {
        "cap_tripped": tripped,
        "cap_bound": outcome.get("stop_reason") == "budget_exceeded" and tripped is not None,
    }


def gate_columns(milestones: list[dict], events: list[dict]) -> dict:
    gates = [m.get("gate") for m in milestones]
    return {
        "gate_failed": any(
            m.get("gate") is not None and m["gate"].get("passed") is False for m in milestones
        ),
        "gate_failed_any": any(
            e.get("type") == "gate" and e.get("passed") is False for e in events
        ),
        "gate_failed_final": any(
            g is not None and (g.get("attempts") or 0) >= 1 and g.get("passed") is False
            for g in gates
        ),
        "gate_unrun": [
            m["id"]
            for m in milestones
            if m.get("gate") is not None
            and (m["gate"].get("attempts") or 0) == 0
            and m["gate"].get("passed") is False
        ],
    }


def extract_row(row: dict, run_dir: Path) -> dict:
    out = json.loads((run_dir / "outcome.json").read_text("utf-8"))
    cdir = cora_dir(run_dir)
    run_id = out.get("run_id")
    cp = cdir / "projects" / str(run_id) / "checkpoint.json"
    planning = (json.loads(cp.read_text("utf-8")).get("planning") or {}) if cp.exists() else {}
    pol = planning.get("policy") or {}
    errors = list(out.get("errors") or [])
    planner_invalid = any("planner reply invalid" in e for e in errors)
    unmetered = sum(
        1
        for f in sorted(cdir.glob("**/events.jsonl"))
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines()
        if UNMETERED_RE.search(line)
    )
    milestones = out.get("milestones") or []
    events = project_events(cdir, run_id)
    cap = cap_columns(out)
    return {
        "task": row["task"],
        "run": row["run"],
        "stop_reason": out.get("stop_reason"),
        "policy_blocked": out.get("stop_reason") == "policy_blocked",
        "policy_deny": row.get("policy_deny"),
        "policy_ask_resolved_deny": row.get("policy_ask_resolved_deny"),
        **policy_columns(out, planning),
        "planner_invalid": planner_invalid,
        "plan": (
            None
            if ("rounds" not in pol and not planner_invalid)
            else plan_quality_of(planning, errors)
        ),
        "milestones_done": row.get("milestones_done"),
        "completed": row.get("completed"),
        "cost_usd": out.get("cost_usd"),
        "wall_s": out.get("wall_s"),
        "iterations": out.get("iterations"),
        "cap_bound": cap["cap_bound"],
        "unmetered": unmetered,
        "cap_bound_m20d": out.get("stop_reason") == "budget_exceeded"
        and (out.get("cost_usd") or 0) >= M20D_CAP_COST,
        "cap_tripped": cap["cap_tripped"],
        **gate_columns(milestones, events),
    }


def session_logs(run_dir: Path) -> list[tuple[str, list[dict]]]:
    found = [
        (f.parent.name, read_jsonl_lines(f))
        for f in (cora_dir(run_dir) / "sessions").glob("*/events.jsonl")
    ]
    return sorted(found, key=lambda s: (s[1][0]["ts"] if s[1] else "", s[0]))


def deny_table(run_dir: Path) -> list[dict]:
    plans = sorted(cora_dir(run_dir).glob("projects/*/plan.toml"))
    plan_text = plans[0].read_text(encoding="utf-8") if plans else ""
    seen: Counter[str] = Counter()
    rows: list[dict] = []
    for sid, events in session_logs(run_dir):
        for line, e in enumerate(events, 1):
            if e.get("type") != "policy_decision" or e.get("decision") == "allow":
                continue
            rule = e.get("rule")
            seen[rule] += 1
            args = e.get("args")
            cmd = args.get("command") if isinstance(args, dict) else args
            rows.append(
                {
                    "cite": f"{run_dir.name}/sessions/{sid}/events.jsonl:{line}",
                    "ts": e.get("ts"),
                    "tool": e.get("tool"),
                    "rule": rule,
                    "decision": e.get("decision"),
                    "resolved": e.get("resolved"),
                    "args": " ".join(str(args).split())[:100],
                    "in_plan": isinstance(cmd, str) and cmd in plan_text,
                    "nth": seen[rule],
                }
            )
    return rows


def stop_rows(run_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for sid, events in session_logs(run_dir):
        for line, e in enumerate(events, 1):
            if e.get("type") not in ("tripwire", "stop"):
                continue
            rows.append(
                {
                    "cite": f"{run_dir.name}/sessions/{sid}/events.jsonl:{line}",
                    "type": e.get("type"),
                    "reason": e.get("reason"),
                    "action": e.get("action"),
                    "kind": e.get("kind"),
                    "tool": e.get("tool"),
                    "count": e.get("count"),
                    "error_head": " ".join(str(e.get("error_head") or "").split())[:120],
                }
            )
    return rows


def _ts(e: dict) -> datetime:
    return datetime.fromisoformat(e["ts"])


def wall_breakdown(run_dir: Path, outcome: dict) -> dict:
    sessions = [evs for _, evs in session_logs(run_dir) if evs]
    everything = [e for evs in sessions for e in evs]
    llm = [e for e in everything if e.get("type") == "llm_call"]
    lat = [float(e["latency_s"]) for e in llm]
    llm_s = sum(lat)
    tool_s = sum(
        (_ts(evs[i]) - _ts(evs[i - 1])).total_seconds()
        for evs in sessions
        for i in range(1, len(evs))
        if evs[i].get("type") == "tool_call"
    )
    span_s = sum((_ts(evs[-1]) - _ts(evs[0])).total_seconds() for evs in sessions)
    gaps_s = sum(
        (_ts(nxt[0]) - _ts(cur[-1])).total_seconds()
        for cur, nxt in zip(sessions, sessions[1:], strict=False)
    )
    pe = project_events(cora_dir(run_dir), outcome.get("run_id"))
    head_s = tail_s = 0.0
    if pe and sessions:
        head_s = (_ts(sessions[0][0]) - _ts(pe[0])).total_seconds()
        tail_s = (_ts(pe[-1]) - _ts(sessions[-1][-1])).total_seconds()
    attributed_s = llm_s + tool_s + gaps_s + head_s + tail_s
    result = {
        "wall_s": outcome["wall_s"],
        "llm_s": llm_s,
        "llm_n": len(llm),
        "llm_median_s": statistics.median(lat) if lat else 0.0,
        "llm_max_s": max(lat, default=0.0),
        "out_tokens": sum(e.get("output_tokens") or 0 for e in llm),
        "parse_errors": sum(1 for e in everything if e.get("type") == "parse_error"),
        "retry_events": sum(1 for e in everything if "retry" in str(e.get("type"))),
        "tool_s": tool_s,
        "span_s": span_s,
        "gaps_s": gaps_s,
        "head_s": head_s,
        "tail_s": tail_s,
        "attributed_s": attributed_s,
        "unattributed_s": outcome["wall_s"] - attributed_s,
        "in_session_other_s": span_s - llm_s - tool_s,
    }
    return {k: round(v, 3) for k, v in result.items()}


def cost_check(run_dir: Path, outcome: dict, prices: dict) -> dict:
    cp = cora_dir(run_dir) / "projects" / str(outcome.get("run_id")) / "checkpoint.json"
    planning = (json.loads(cp.read_text("utf-8")).get("planning") or {}) if cp.exists() else {}
    calls = [e for _, evs in session_logs(run_dir) for e in evs if e.get("type") == "llm_call"]
    metered_s = sum(e.get("cost_usd") or 0.0 for e in calls)
    planner_usd = planning.get("cost_usd") or 0.0
    metered_total = metered_s + planner_usd
    outcome_usd = outcome["cost_usd"]
    priced = (
        sum(
            ((e.get("input_tokens") or 0) - (e.get("cached_tokens") or 0))
            * prices["input_usd_per_mtok"]
            + (e.get("cached_tokens") or 0) * prices["cache_read_usd_per_mtok"]
            + (e.get("output_tokens") or 0) * prices["output_usd_per_mtok"]
            for e in calls
        )
        / 1e6
    )
    result = {
        "metered_s": metered_s,
        "planner_usd": planner_usd,
        "metered_total": metered_total,
        "outcome_usd": outcome_usd,
        "outcome_minus_metered": outcome_usd - metered_total,
        "cost_sources": dict(Counter(e.get("cost_source") for e in calls)),
        "input_tokens": sum(e.get("input_tokens") or 0 for e in calls),
        "cached_tokens": sum(e.get("cached_tokens") or 0 for e in calls),
        "output_tokens": sum(e.get("output_tokens") or 0 for e in calls),
        "priced": priced,
        "metered_minus_priced": metered_s - priced,
    }
    return {k: round(v, 9) if isinstance(v, float) else v for k, v in result.items()}


def model_prices(config_path: Path, model_id: str) -> dict:
    with config_path.open("rb") as f:
        models = tomllib.load(f).get("models", [])
    for m in models:
        if m.get("id") == model_id:
            return {
                k: m.get(k, 0.0)
                for k in ("input_usd_per_mtok", "output_usd_per_mtok", "cache_read_usd_per_mtok")
            }
    raise SystemExit(2)


def _variants(p: str) -> set[str]:
    return {p, os.path.normpath(p), os.path.realpath(p)}


def _rescue_pairs(src: Path) -> list[tuple[str, str]]:
    tmp = tempfile.gettempdir()
    pairs: dict[str, str] = {}
    for s in _variants(str(src)) | _variants(str(Path(tmp) / "cora-m20d")):
        pairs[s] = PLACEHOLDER_M20D
    for t in _variants(tmp):
        pairs[t] = "<TMP>"
    pairs[os.path.expanduser("~")] = "<HOME>"
    return sorted(pairs.items(), key=lambda kv: len(kv[0]), reverse=True)


def _rescue_sources(src: Path) -> dict[str, tuple[Path, list[str] | None]]:
    plan: dict[str, tuple[Path, list[str] | None]] = {}
    top = {
        "runs.jsonl": ["R3"],
        "extract.jsonl": ["R5"],
        "rehearsal.jsonl": ["R3"],
        "ledger.md": ["R13"],
        "readiness.txt": ["R3"],
        "m17diff.txt": ["R3"],
    }
    for name, items in top.items():
        plan[name] = (src / name, items)
    plan["m20d_extract.py.txt"] = (src / "m20d_extract.py", ["R5"])
    plan["artifacts/cora-m20d-deepseek-deadline.toml"] = (
        src / "cfg" / "cora-m20d-deepseek-deadline.toml",
        ["R3"],
    )
    for run in M20D_RUNS:
        base = f"artifacts/m20d-deepseek-v2/{run}"
        plan[f"{base}/outcome.json"] = (src / base / "outcome.json", ["R3"])
        projects = src / base / "projects"
        pfiles = sorted(p for p in projects.rglob("*") if p.is_file()) if projects.is_dir() else []
        for p in pfiles:
            plan[f"{base}/projects/{p.relative_to(projects).as_posix()}"] = (
                p,
                ["R6", "R7", "R10"],
            )
        if not pfiles:
            plan[f"{base}/projects"] = (projects, ["R6", "R7", "R10"])
        runs_dir = src / "runs"
        sessions = sorted((runs_dir / run / "ws" / ".cora" / "sessions").glob("*/events.jsonl"))
        for s in sessions:
            plan[f"{base}/sessions/{s.parent.name}/events.jsonl"] = (
                s,
                ["R12", "R14", "R13"],
            )
        if not sessions:
            plan[f"{base}/sessions"] = (
                runs_dir / run / "ws" / ".cora" / "sessions",
                ["R12", "R14", "R13"],
            )
        for name in ("start.txt", "time.txt", "runrow.out"):
            plan[f"{base}/meta/{name}"] = (runs_dir / run / name, ["R3"])
        plan[f"{base}/meta/launch.txt"] = (runs_dir / f"{run}.launch.txt", None)
        plan[f"{base}/meta/guard.txt"] = (runs_dir / f"{run}.guard.txt", None)
    for t in M20D_REHEARSALS:
        rbase = f"artifacts/m20d-rehearsal/{t}-r0"
        plan[f"{rbase}/outcome.json"] = (src / rbase / "outcome.json", ["R3"])
        for name in ("runrow.out", "stderr.txt"):
            plan[f"{rbase}/meta/{name}"] = (src / "rehearsal" / t / name, None)
    fallback = src / "rehearsal" / "runrow.out"
    if not (src / "rehearsal" / "e2e_n08" / "runrow.out").is_file() and fallback.is_file():
        plan["artifacts/m20d-rehearsal/e2e_n08-r0/meta/runrow.out"] = (fallback, None)
    return plan


def rescue(src: Path, dst: Path) -> dict:
    src = src.absolute()
    dst = dst.absolute()
    pairs = _rescue_pairs(src)
    env_vals = [(name, os.environ.get(name, "")) for name in KEY_ENV_VARS]
    redacted = "<REDACTED>"
    copies: dict[str, str] = {}
    blocked: list[dict] = []
    redactions: list[dict] = []
    partial_tmp: list[dict] = []
    for rel, (path, items) in _rescue_sources(src).items():
        if not path.is_file():
            if items is not None:
                blocked.append({"file": rel, "items": items})
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            text, partial = _sanitize(fh.read(), pairs)
        partial_tmp.extend({"file": rel, "line": n} for n in partial)
        lines: list[str] = []
        for n, line in enumerate(text.split("\n"), 1):
            for rx in KEY_SCAN_RES:
                redactions.extend(
                    {"file": rel, "line": n, "pattern": rx.pattern} for _ in rx.finditer(line)
                )
                line = rx.sub(redacted, line)
            for name, val in env_vals:
                if len(val) >= 8:
                    redactions.extend(
                        {"file": rel, "line": n, "pattern": name} for _ in range(line.count(val))
                    )
                    line = line.replace(val, redacted)
            lines.append(line)
        copies[rel] = "\n".join(lines)
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)
    for rel, text in copies.items():
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    manifest = {
        "source": "$TMPDIR/cora-m20d (via backup if used)",
        "files": sorted(copies),
        "blocked": blocked,
        "redactions": redactions,
        "partial_tmp": partial_tmp,
        "not_copied": [
            {
                "path": "runs/*/ws (task files, .cora/memory, .cora/home)",
                "reason": "task workspace; rebuilt by prepare; memory not evidence for M20e",
            },
            {
                "path": "runs/*/ws/.cora/sessions/*/session.json",
                "reason": "session state snapshot; events.jsonl kept",
            },
            {
                "path": "rehearsal/*/ws, rehearsal/*/records, rehearsal/*.ws",
                "reason": "task workspace / empty record dir (records 0) / path note",
            },
            {
                "path": "scratch-*.sh, results-*.md, amend.md, *.txt logs",
                "reason": "operator scratch; results already in .docs/bench-results.md",
            },
        ],
        "placeholders": {
            "<M20D>": "M20d working dir",
            "<TMP>": "system temp directory",
            "<HOME>": "home directory",
            "<TMP-PARTIAL>": "truncated temp-path fragment",
        },
    }
    (dst / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8"
    )
    return manifest


def run_row(
    task_id: str,
    ws: Path,
    outcome: dict,
    label: str,
    run: int,
    interventions: int,
    rerun_of: str | None = None,
) -> dict:
    leaks = leakcheck(task_id, ws, pre_grade=True)
    hits = event_hits(ws)
    g = grade(task_id, ws, tempfile.mkdtemp())
    planning: dict[str, Any] = {}
    run_id = outcome.get("run_id")
    if run_id:
        cp = ws / ".cora" / "projects" / run_id / "checkpoint.json"
        if cp.exists():
            data = json.loads(cp.read_text(encoding="utf-8"))
            planning = data.get("planning") or {}
    dest = OUT_ROOT / label / (f"{task_id}-r{run}" + ("-rerun" if rerun_of else ""))
    dest.mkdir(parents=True, exist_ok=True)
    src = ws / ".cora" / "projects"
    if src.exists():
        shutil.copytree(src, dest / "projects", dirs_exist_ok=True)
    (dest / "outcome.json").write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    errors = list(outcome.get("errors") or [])
    planner_invalid = any("planner reply invalid" in e for e in errors)
    calls = planning.get("calls")
    quality = plan_quality_of(planning, errors)
    milestones = outcome.get("milestones") or []
    done = milestones_done(milestones)
    events = project_events(ws / ".cora", run_id)
    gates = gate_columns(milestones, events)
    policy = outcome.get("policy")
    error_run = not planner_invalid and (
        outcome.get("stop_reason") == "error" or outcome.get("exit_code") == 1
    )
    return {
        "task": task_id,
        "label": label,
        "run": run,
        "models": outcome.get("models"),
        "exit_code": outcome.get("exit_code"),
        "stop_reason": outcome.get("stop_reason"),
        "completed": bool(g["full_pass"]),
        "score": g["score"],
        "iterations": outcome.get("iterations"),
        "cost_usd": outcome.get("cost_usd"),
        "wall_s": outcome.get("wall_s"),
        **cap_columns(outcome),
        "interventions": interventions,
        "policy_deny": int(policy.get("deny", 0)) if policy else 0,
        "policy_ask_resolved_deny": int(policy.get("ask_resolved_deny", 0)) if policy else 0,
        "planner_calls": calls,
        "plan_quality": quality,
        **policy_columns(outcome, planning),
        "milestones_total": len(milestones),
        "milestones_done": done,
        **gates,
        "leaks": leaks,
        "protected_hits": hits,
        "error": "; ".join(errors) or None,
        "error_run": error_run,
        "rerun_of": rerun_of,
    }


def keygrep(paths: list[Path]) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key or len(key) < 8:
        raise SystemExit(2)
    needle = key.encode()
    scanned = 0
    matches: list[str] = []
    for path in paths:
        if path.is_file():
            files = [path]
        else:
            files = []
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                files.extend(Path(dirpath) / f for f in filenames)
        for f in files:
            try:
                data = f.read_bytes()
            except OSError:
                continue
            scanned += 1
            if needle in data:
                matches.append(str(f))
    return {"files_scanned": scanned, "matches": matches}


def _fmt_wilson(k: int, n: int) -> str:
    w = wilson_interval(k, n)
    if w is None:
        return "-"
    return f"[{w[0]:.3f}, {w[1]:.3f}]"


def _load_baseline(path: Path | None) -> dict:
    if path is None:
        return {}
    with path.open("rb") as f:
        return tomllib.load(f).get("tasks", {})


def _label_heading(label: str) -> str:
    heading = f"#### label: {label}"
    if label.startswith("gemini"):
        heading += " (free-tier, non-G1)"
    if label in PRE_FIX_LABELS:
        heading += " (pre-fix planner prompt)"
    for sfx, rnd in FIX_ROUNDS.items():
        if label.endswith(sfx):
            heading += f" (post-fix planner prompt, {rnd})"
    return heading


def _superseded_flags(run_rows: list[dict]) -> list[bool]:
    flags: list[bool] = []
    for i, s in enumerate(run_rows):
        key = f"{s['task']}-r{s['run']}"
        flags.append(
            any(
                j != i
                and o["label"] == s["label"]
                and o["task"] == s["task"]
                and o["run"] == s["run"]
                and o.get("rerun_of") == key
                for j, o in enumerate(run_rows)
            )
        )
    return flags


def summary(
    planq_rows: list[dict],
    run_rows: list[dict],
    baseline: Path | None,
    checks_rows: list[dict] | None = None,
    run_labels: list[str] | None = None,
) -> str:
    out: list[str] = []
    out.append("### (1) Plan quality, per label")
    labels: list[str] = []
    for r in planq_rows:
        if r["label"] not in labels:
            labels.append(r["label"])
    checks_by_key: dict[tuple[str, str], dict] = {}
    for c in checks_rows or []:
        checks_by_key[(c["task"], c["label"])] = c
    for label in labels:
        out.append(_label_heading(label))
        pol = any(r.get("policy_issues") is not None for r in planq_rows if r["label"] == label)
        head = (
            "| task | quality | first reply strict | milestones | conditions executable "
            "| pass on reference | check runnable | planner $ |"
        )
        sep = "|---|---|---|---|---|---|---|---|"
        if pol:
            head += " policy issues/repaired/dropped | ungated milestones |"
            sep += "---|---|"
        out.append(head)
        out.append(sep)
        for r in planq_rows:
            if r["label"] != label:
                continue
            strict = (
                "-"
                if r["first_reply_strict"] is None
                else ("yes" if r["first_reply_strict"] else "no")
            )
            ms = "-" if r["milestones"] is None else str(r["milestones"])
            ex = (
                "-"
                if r["conditions_total"] is None
                else f"{r['conditions_executable']}/{r['conditions_total']}"
            )
            ps = (
                "-"
                if r["conditions_total"] is None
                else f"{r['conditions_pass_ref']}/{r['conditions_total']}"
            )
            if r.get("checks_total") is not None:
                chk = f"{r['check_runnable']}/{r['checks_total']}"
            elif (r["task"], r["label"]) in checks_by_key:
                c = checks_by_key[(r["task"], r["label"])]
                chk = f"{c['check_runnable']}/{c['checks_total']}"
            else:
                chk = "-"
            cost = "-" if r["cost_usd"] is None else f"{r['cost_usd']:.4f}"
            line = (
                f"| {r['task']} | {r['plan_quality'] or '-'} | {strict} | {ms} | {ex} | {ps} "
                f"| {chk} | {cost} |"
            )
            if pol:
                issues = r.get("policy_issues")
                pcell = (
                    "-"
                    if issues is None
                    else f"{issues}/{r['policy_repaired']}/{r['policy_dropped']}"
                )
                ucell = "-" if r.get("ungated") is None else (", ".join(r["ungated"]) or "none")
                line = line[:-1] + f"| {pcell} | {ucell} |"
            out.append(line)
    out.append("")
    base = _load_baseline(baseline)
    flags = _superseded_flags(run_rows)
    all_labels = list(dict.fromkeys(r["label"] for r in run_rows))
    labels = run_labels if run_labels is not None else all_labels
    for label in labels:
        label_rows = [
            (r, sup) for r, sup in zip(run_rows, flags, strict=True) if r["label"] == label
        ]
        counted = [r for r, sup in label_rows if not sup]
        note = RUN_LABEL_NOTES.get(label)

        out.append(f"### (2) Per-run ({label})")
        if note is not None:
            out.append(note)
        out.append(
            "| task | run | completed | stop_reason | interventions | iterations | $ | wall_s "
            "| plan | gate_failed | leaks |"
        )
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r, sup in label_rows:
            leaks = f"{len(r['leaks'])}+{len(r['protected_hits'])}"
            stop = r["stop_reason"]
            if sup:
                stop = f"{stop} (superseded)"
            elif r.get("rerun_of"):
                stop = f"{stop} (rerun {r['rerun_of']})"
            out.append(
                f"| {r['task']} | {r['run']} | {'yes' if r['completed'] else 'no'} "
                f"| {stop} | "
                f"{r['interventions']} | {r['iterations']} | {r['cost_usd']:.4f} | {r['wall_s']} | "
                f"{r['plan_quality'] or '-'} | {'yes' if r['gate_failed'] else 'no'} | {leaks} |"
            )
        out.append("")

        out.append(f"### (3) Per task ({label})")
        if note is not None:
            out.append(note)
        out.append("| task | k/n | wilson | $ total | $ per run | CC k/n | CC $ per run |")
        out.append("|---|---|---|---|---|---|---|")
        tasks: list[str] = list(PRE_REGISTERED_TASKS) if label in PRE_REGISTERED_LABELS else []
        for r in counted:
            if r["task"] not in tasks:
                tasks.append(r["task"])
        for t in tasks:
            rows = [r for r in counted if r["task"] == t]
            n = len(rows)
            if n == 0:
                out.append(f"| {t} | 0/0 | not measured (budget) | - | - | - | - |")
                continue
            k = sum(1 for r in rows if r["completed"])
            total = sum(r["cost_usd"] for r in rows)
            wil = "no claim (n<3)" if n < 3 else _fmt_wilson(k, n)
            if t in base:
                cc_n = round(float(base[t]["solved"]) * int(base[t]["n"]))
                cc_kn = f"{cc_n}/{int(base[t]['n'])}"
                cc_cost = f"{float(base[t]['cost_usd']):.4f}"
            else:
                cc_kn = "no baseline (not measured)"
                cc_cost = "-"
            out.append(
                f"| {t} | {k}/{n} | {wil} | {total:.4f} | {total / n:.4f} | {cc_kn} | {cc_cost} |"
            )
        out.append("")

        out.append(f"### (4) Overall ({label})")
        if note is not None:
            out.append(note)
        out.append(
            "| completed | n | rate | wilson | $ total | solved per $ | $ per completed "
            "| interventions |"
        )
        out.append("|---|---|---|---|---|---|---|---|")
        n_all = len(counted)
        k_all = sum(1 for r in counted if r["completed"])
        total_all = sum(r["cost_usd"] for r in counted)
        interventions = sum(r["interventions"] for r in counted)
        rate = f"{k_all / n_all:.3f}" if n_all else "-"
        spd = f"{k_all / total_all:.3f}" if total_all > 0 else "n/a"
        per_completed = f"{total_all / k_all:.4f}" if k_all else "n/a"
        out.append(
            f"| {k_all} | {n_all} | {rate} | {_fmt_wilson(k_all, n_all)} | {total_all:.4f} | "
            f"{spd} | {per_completed} | {interventions} |"
        )
        out.append("")
    if out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="m20_trial")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("config")
    c.add_argument("model")
    c.add_argument("out", type=Path)
    c.add_argument("--variant", choices=VARIANTS, default="base")
    c.add_argument("--prompt-rules", action="store_true")
    g = sub.add_parser("goal")
    g.add_argument("task")
    pr = sub.add_parser("prepare")
    pr.add_argument("task")
    pr.add_argument("dir", type=Path)
    q = sub.add_parser("planq")
    q.add_argument("task")
    q.add_argument("--outcome", type=Path, required=True)
    q.add_argument("--plan", type=Path, required=True)
    q.add_argument("--records", type=Path, required=True)
    q.add_argument("--label", required=True)
    q.add_argument("--config", type=Path, required=True)
    cq = sub.add_parser("checkq")
    cq.add_argument("task")
    cq.add_argument("--plan", type=Path, required=True)
    cq.add_argument("--config", type=Path, required=True)
    cq.add_argument("--label", required=True)
    r = sub.add_parser("runrow")
    r.add_argument("task")
    r.add_argument("--ws", type=Path, required=True)
    r.add_argument("--outcome", type=Path, required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--run", type=int, required=True)
    r.add_argument("--interventions", type=int, required=True)
    r.add_argument("--rerun-of", default=None)
    k = sub.add_parser("keygrep")
    k.add_argument("paths", nargs="+", type=Path)
    s = sub.add_parser("summary")
    s.add_argument("--planq", type=Path, required=True)
    s.add_argument("--runs", type=Path, required=True)
    s.add_argument("--baseline", type=Path, default=None)
    s.add_argument("--checks", type=Path, default=None)
    s.add_argument("--run-label", action="append", dest="run_labels", default=None)
    x = sub.add_parser("extract")
    x.add_argument("--rows", type=Path, required=True)
    x.add_argument("--runs-root", type=Path, required=True)
    rs = sub.add_parser("rescue")
    rs.add_argument("--src", type=Path, required=True)
    rs.add_argument("--dst", type=Path, required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "config":
        print(make_config(args.model, args.out, args.variant, prompt_rules=args.prompt_rules))
        return 0
    if args.cmd == "goal":
        sys.stdout.write(goal_text(args.task))
        return 0
    if args.cmd == "prepare":
        print(prepare_ws(args.task, args.dir))
        return 0
    if args.cmd == "planq":
        outcome = json.loads(args.outcome.read_text(encoding="utf-8"))
        row = planq_row(args.task, outcome, args.plan, args.records, args.label, args.config)
        print(json.dumps(row))
        return 0
    if args.cmd == "checkq":
        row = checkq_row(args.task, args.plan, args.config, args.label)
        print(json.dumps(row))
        return 0
    if args.cmd == "runrow":
        outcome = json.loads(args.outcome.read_text(encoding="utf-8"))
        row = run_row(
            args.task,
            args.ws,
            outcome,
            args.label,
            args.run,
            args.interventions,
            rerun_of=args.rerun_of,
        )
        print(json.dumps(row))
        if row["error_run"]:
            return 3
        if row["leaks"] or row["protected_hits"]:
            return 1
        return 0
    if args.cmd == "keygrep":
        result = keygrep(args.paths)
        print(json.dumps(result))
        return 1 if result["matches"] else 0
    if args.cmd == "summary":
        planq_rows = _read_jsonl(args.planq)
        run_rows = _read_jsonl(args.runs)
        checks_rows = _read_jsonl(args.checks) if args.checks is not None else None
        sys.stdout.write(
            summary(
                planq_rows,
                run_rows,
                args.baseline,
                checks_rows,
                run_labels=args.run_labels,
            )
        )
        return 0
    if args.cmd == "extract":
        for row in _read_jsonl(args.rows):
            run_dir = args.runs_root / f"{row['task']}-r{row['run']}"
            print(json.dumps(extract_row(row, run_dir)))
        return 0
    if args.cmd == "rescue":
        m = rescue(args.src, args.dst)
        print(
            json.dumps(
                {
                    "files": len(m["files"]),
                    "blocked": m["blocked"],
                    "redactions": len(m["redactions"]),
                }
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
