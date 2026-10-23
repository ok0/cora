"""Live bench reports and optional baseline comparison.

Baseline file schema (TOML, optional, used with `cora bench --live --baseline`):

    [meta]
    source = "free text"   # optional

    [tasks.<task_id>]
    cost_usd = 0.04
    success = true
"""

from __future__ import annotations

import json
import math
import os
import statistics
import tomllib
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

import cora
from cora.bench.aggregate import Run, aggregate, aggregation_lines
from cora.bench.stats import fmt_sig
from cora.core.errors import ConfigError

ATTEMPTED_STATUSES = ("solved", "failed", "stopped_budget", "error")
UNRUN_STATUSES = ("skipped_budget", "not_run")
DEFAULT_STALL_THRESHOLD_S = 60.0
AB_ARMS = ("deleg-off", "deleg-on-par-off", "deleg-on-par-on", "strong-only", "auto-routed")
ARM_ALIASES = {"deleg-off": "cheap-only"}
DIFFICULTY_BINS = ("easy", "medium", "hard", "unlabeled")
DIFF_HEADING = (
    "### By difficulty (easy <= 2 min, medium <= 10 min, hard > 10 min; author estimates)"
)
AVOIDED_NOTE = (
    "avoided_tokens_est is an estimate (sub-agent tool-result tokens minus the summary tokens "
    "returned to the main agent), not a counterfactual measurement. Each cell is one attempt: "
    "directional only."
)


@dataclass
class LiveTaskResult:
    task: str
    kind: str
    model: str
    protocol: str
    status: str  # solved | failed | stopped_budget | skipped_budget | error | not_run
    budget_reason: str | None
    stop_reason: str | None
    iterations: int
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    provider_cost_calls: int
    latency_s: float
    detail: str
    check_runs: int = 0
    sensor_retries: int = 0
    sensor_calls: int = 0
    sensor_cost_usd: float = 0.0
    escalated: bool = False
    arm: str | None = None
    difficulty: str | None = None
    estimated_minutes: float | None = None
    routes: list[dict] = field(default_factory=list)
    deleg_invocations: int = 0
    deleg_attempts: int = 0
    deleg_attempts_unparsed: int = 0
    deleg_explore: int = 0
    deleg_general: int = 0
    deleg_ok: int = 0
    deleg_failed: int = 0
    deleg_refused: int = 0
    deleg_input_tokens: int = 0
    deleg_output_tokens: int = 0
    deleg_cost_usd: float = 0.0
    deleg_wall_s: float = 0.0
    deleg_max_fanout: int = 0
    deleg_avoided_tokens_est: int = 0
    call_latencies_s: list[float] = field(default_factory=list)
    run_id: str = ""
    repeat_index: int = 0
    seed: int = 0
    aborted_run: bool = False
    score: float | None = None
    full_pass: bool | None = None
    end_reason: str | None = None
    human_interventions: int | None = None
    grader: dict | None = None
    policy_denies: int | None = None
    policy_asks: int | None = None
    policy: dict | None = None


@dataclass
class RowSummary:
    model: str
    protocol: str
    attempted: int
    solved: int
    failed: int
    skipped: int
    solve_rate: float | None
    total_cost_usd: float
    cost_per_solved_usd: float | None
    input_tokens: int
    output_tokens: int
    avg_calls: float | None
    avg_latency_s: float | None


@dataclass
class LiveReport:
    generated_at: str
    settings: dict
    results: list[LiveTaskResult]
    budget_exhausted: bool
    aborted: str | None = None
    wall_s: float | None = None
    abort_guidance: str | None = None
    runs_planned: int | None = None
    in_progress: bool = False
    extras: dict = field(default_factory=dict)

    @property
    def total_cost_usd(self) -> float:
        return sum((r.cost_usd for r in self.results), 0.0)

    @property
    def total_calls(self) -> int:
        return sum(r.calls for r in self.results)

    @property
    def provider_cost_calls(self) -> int:
        return sum(r.provider_cost_calls for r in self.results)

    @property
    def runs_completed(self) -> int:
        return sum(1 for r in self.results if is_completed(r))

    @property
    def partial_reason(self) -> str | None:
        if self.in_progress:
            return "in progress: the run stopped before it finished"
        if self.aborted:
            return f"aborted: {self.aborted}"
        if self.budget_exhausted and self.runs_completed < (self.runs_planned or len(self.results)):
            return "budget cap reached (--max-cost)"
        return None

    @property
    def partial(self) -> bool:
        return self.partial_reason is not None


@dataclass
class ArmRow:
    arm: str
    alias: str | None
    model: str
    attempted: int
    solved: int
    skipped: int
    solve_rate: float | None
    total_cost_usd: float
    cost_per_solved_usd: float | None
    resolved_per_dollar: float | None
    wall_s: float
    avg_latency_s: float | None
    deleg_invocations: int
    deleg_attempts: int
    deleg_attempts_unparsed: int
    deleg_explore: int
    deleg_general: int
    deleg_ok: int
    deleg_failed: int
    deleg_refused: int
    deleg_input_tokens: int
    deleg_output_tokens: int
    deleg_cost_usd: float
    deleg_wall_s: float
    deleg_max_fanout: int
    deleg_avoided_tokens_est: int


@dataclass(frozen=True)
class BaselineEntry:
    cost_usd: float
    success: bool


@dataclass(frozen=True)
class LiveBaseline:
    file: str  # basename only
    source: str | None
    tasks: dict[str, BaselineEntry]


def make_run_id(
    arm: str | None, model: str, protocol: str, task: str, repeat_index: int
) -> str:
    return f"{arm or '-'}|{model}|{protocol}|{task}|r{repeat_index}"


def completed_status(status: str, budget_reason: str | None, aborted_run: bool) -> bool:
    return (
        status in ATTEMPTED_STATUSES
        and not aborted_run
        and not (status == "stopped_budget" and budget_reason == "total")
    )


def is_completed(r: LiveTaskResult) -> bool:
    return completed_status(r.status, r.budget_reason, r.aborted_run)


def to_run(r: LiveTaskResult) -> Run:
    return Run(
        arm=r.arm,
        model=r.model,
        protocol=r.protocol,
        task=r.task,
        solved=r.status == "solved",
        cost_usd=r.cost_usd,
        tokens=r.input_tokens + r.output_tokens,
        wall_s=r.latency_s,
        score=getattr(r, "score", None),
    )


def atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_resume(out_dir: Path) -> tuple[dict, dict[str, LiveTaskResult]]:
    try:
        obj = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ConfigError(f"--resume: cannot read report.json in {out_dir.name}") from None
    raw = obj.get("results") if isinstance(obj, dict) else None
    if not isinstance(raw, list):
        raise ConfigError(f"--resume: invalid report.json in {out_dir.name}")
    names = {f.name for f in fields(LiveTaskResult)}
    results: list[LiveTaskResult] = []
    for d in raw:
        try:
            r = LiveTaskResult(**{k: v for k, v in d.items() if k in names})
        except (TypeError, AttributeError):
            raise ConfigError(f"--resume: invalid report.json in {out_dir.name}") from None
        if not r.run_id:
            r = replace(
                r, run_id=make_run_id(r.arm, r.model, r.protocol, r.task, r.repeat_index)
            )
        results.append(r)
    return obj, {r.run_id: r for r in results if is_completed(r)}


def e2e_section(report: LiveReport) -> dict | None:
    runs = [r for r in report.results if r.kind == "e2e"]
    if not runs:
        return None
    done = [r for r in runs if is_completed(r)]
    scores = [r.score for r in done if r.score is not None]
    return {
        "runs": len(done),
        "full_pass": sum(1 for r in done if r.full_pass),
        "mean_score": statistics.fmean(scores) if scores else None,
        "human_interventions_total": sum(r.human_interventions or 0 for r in runs),
        "policy_deny_total": sum(r.policy_denies or 0 for r in runs),
        "policy_ask_total": sum(r.policy_asks or 0 for r in runs),
        "grader_errors": sum(
            1 for r in runs if r.grader is not None and r.grader.get("status") == "grader_error"
        ),
    }


def _grader_cell(r: LiveTaskResult) -> str:
    if r.grader is None:
        return "-"
    if r.grader.get("status") == "ok":
        return "ok"
    return f"grader_error: {r.grader.get('reason')}"


def _e2e_lines(report: LiveReport) -> list[str]:
    runs = [r for r in report.results if r.kind == "e2e"]
    if not runs:
        return []
    lines = [
        "### E2E tasks (solved = full_pass)",
        "",
        "| task | config | repeat | score | full_pass | end_reason | iterations | cost_usd | "
        "tokens | wall_s | human_interventions | grader |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        score = "n/a" if r.score is None else fmt_sig(r.score, 2)
        lines.append(
            f"| {r.task} | {_result_label(r)} | {r.repeat_index} | {score} | "
            f"{_yes_no(r.full_pass)} | {r.end_reason or '-'} | {r.iterations} | "
            f"{r.cost_usd:.6f} | {r.input_tokens + r.output_tokens} | {r.latency_s:.2f} | "
            f"{r.human_interventions if r.human_interventions is not None else 'n/a'} | "
            f"{_grader_cell(r)} |"
        )
    if any(r.policy_denies is not None for r in runs):
        lines += ["", "policy (strict e2e profile, separate from human_interventions): "
                  f"deny={sum(r.policy_denies or 0 for r in runs)} "
                  f"ask={sum(r.policy_asks or 0 for r in runs)}"]
    for r in runs:
        if r.grader is None:
            continue
        lines += ["", f"#### checks: {r.task} {_result_label(r)} r{r.repeat_index}"]
        for c in r.grader.get("checks", []):
            if c["passed"]:
                lines.append(f"- [x] {c['name']}")
            else:
                lines.append(f"- [ ] {c['name']}: {c['detail']}")
    intervened = sum(1 for r in runs if (r.human_interventions or 0) > 0)
    if intervened:
        lines += [
            "",
            f"WARNING: human_interventions > 0 in {intervened} run(s): approval requests "
            "were answered automatically by the harness",
        ]
    return lines


def _aggregation(report: LiveReport) -> dict:
    return aggregate([to_run(r) for r in report.results if is_completed(r)])


def summarize(report: LiveReport) -> list[RowSummary]:
    rows: list[RowSummary] = []
    for model in report.settings["models"]:
        for protocol in report.settings["protocols"]:
            rs = [r for r in report.results if r.model == model["id"] and r.protocol == protocol]
            attempted = sum(1 for r in rs if r.status in ATTEMPTED_STATUSES)
            solved = sum(1 for r in rs if r.status == "solved")
            skipped = sum(1 for r in rs if r.status in UNRUN_STATUSES)
            total_cost = sum((r.cost_usd for r in rs), 0.0)
            calls = sum(r.calls for r in rs)
            latency = sum(r.latency_s for r in rs)
            rows.append(
                RowSummary(
                    model=model["id"],
                    protocol=protocol,
                    attempted=attempted,
                    solved=solved,
                    failed=attempted - solved,
                    skipped=skipped,
                    solve_rate=solved / attempted if attempted else None,
                    total_cost_usd=total_cost,
                    cost_per_solved_usd=total_cost / solved if solved else None,
                    input_tokens=sum(r.input_tokens for r in rs),
                    output_tokens=sum(r.output_tokens for r in rs),
                    avg_calls=calls / attempted if attempted else None,
                    avg_latency_s=latency / attempted if attempted else None,
                )
            )
    return rows


def summarize_arms(report: LiveReport) -> list[ArmRow]:
    ab = report.settings["ab"]
    rows: list[ArmRow] = []
    for arm in ab["arms"]:
        rs = [r for r in report.results if r.arm == arm]
        attempted = sum(1 for r in rs if r.status in ATTEMPTED_STATUSES)
        solved = sum(1 for r in rs if r.status == "solved")
        skipped = sum(1 for r in rs if r.status in UNRUN_STATUSES)
        total_cost = sum((r.cost_usd for r in rs), 0.0)
        wall = sum(r.latency_s for r in rs)
        if arm == "strong-only":
            model = ab["strong_model"]
        elif arm == "auto-routed":
            model = "auto"
        else:
            model = ab["model"]
        rows.append(
            ArmRow(
                arm=arm,
                alias=ARM_ALIASES.get(arm),
                model=model,
                attempted=attempted,
                solved=solved,
                skipped=skipped,
                solve_rate=solved / attempted if attempted else None,
                total_cost_usd=total_cost,
                cost_per_solved_usd=total_cost / solved if solved else None,
                resolved_per_dollar=solved / total_cost if total_cost > 0 else None,
                wall_s=wall,
                avg_latency_s=wall / attempted if attempted else None,
                deleg_invocations=sum(r.deleg_invocations for r in rs),
                deleg_attempts=sum(r.deleg_attempts for r in rs),
                deleg_attempts_unparsed=sum(r.deleg_attempts_unparsed for r in rs),
                deleg_explore=sum(r.deleg_explore for r in rs),
                deleg_general=sum(r.deleg_general for r in rs),
                deleg_ok=sum(r.deleg_ok for r in rs),
                deleg_failed=sum(r.deleg_failed for r in rs),
                deleg_refused=sum(r.deleg_refused for r in rs),
                deleg_input_tokens=sum(r.deleg_input_tokens for r in rs),
                deleg_output_tokens=sum(r.deleg_output_tokens for r in rs),
                deleg_cost_usd=sum((r.deleg_cost_usd for r in rs), 0.0),
                deleg_wall_s=sum((r.deleg_wall_s for r in rs), 0.0),
                deleg_max_fanout=max((r.deleg_max_fanout for r in rs), default=0),
                deleg_avoided_tokens_est=sum(r.deleg_avoided_tokens_est for r in rs),
            )
        )
    return rows


def _result_label(r: LiveTaskResult) -> str:
    return r.arm or f"{r.model} {r.protocol}"


def _configs(report: LiveReport) -> list[str]:
    ab = report.settings.get("ab")
    if ab is not None:
        return list(ab["arms"])
    return [
        f"{m['id']} {p}" for m in report.settings["models"] for p in report.settings["protocols"]
    ]


def stall_threshold(report: LiveReport) -> float:
    return float(report.settings.get("stall_threshold_s", DEFAULT_STALL_THRESHOLD_S))


def call_stats(values: Sequence[float], threshold: float) -> dict:
    stalled = sum(1 for v in values if v > threshold)
    return {
        "calls": len(values),
        "p50_s": statistics.median(values) if values else None,
        "max_s": max(values) if values else None,
        "stalled_calls": stalled,
        "stall": stalled > 0,
    }


def cell_counts(report: LiveReport) -> dict:
    return {
        "executed": sum(1 for r in report.results if r.status not in UNRUN_STATUSES),
        "not_run": sum(1 for r in report.results if r.status == "not_run"),
        "skipped_budget": sum(1 for r in report.results if r.status == "skipped_budget"),
    }


def latency_section(report: LiveReport) -> dict:
    thr = stall_threshold(report)
    ran = [r for r in report.results if r.status not in UNRUN_STATUSES]
    return {
        "stall_threshold_s": thr,
        "cell_wall_s_sum": sum(r.latency_s for r in report.results),
        "configs": [
            {"config": c, **call_stats(
                [v for r in ran if _result_label(r) == c for v in r.call_latencies_s], thr
            )}
            for c in _configs(report)
        ],
        "cells": [
            {"task": r.task, "config": _result_label(r), **call_stats(r.call_latencies_s, thr)}
            for r in ran
        ],
    }


def difficulty_rows(report: LiveReport) -> list[dict]:
    rows: list[dict] = []
    for config in _configs(report):
        for bin_name in DIFFICULTY_BINS:
            rs = [
                r
                for r in report.results
                if _result_label(r) == config
                and (r.difficulty or "unlabeled") == bin_name
                and r.status not in UNRUN_STATUSES
            ]
            if not rs:
                continue
            rows.append(
                {
                    "config": config,
                    "bin": bin_name,
                    "tasks": len(rs),
                    "solved": sum(1 for r in rs if r.status == "solved"),
                    "cost_usd": sum((r.cost_usd for r in rs), 0.0),
                    "wall_s": sum(r.latency_s for r in rs),
                }
            )
    return rows


def tier_rows(report: LiveReport) -> list[dict] | None:
    ab = report.settings.get("ab")
    if ab is None or not {"strong-only", "auto-routed"} & set(ab["arms"]):
        return None
    rows: list[dict] = []
    for task_id in report.settings["tasks"]:
        by_arm = {r.arm: r for r in report.results if r.task == task_id}
        cheap = by_arm.get("deleg-off")
        strong = by_arm.get("strong-only")
        auto = by_arm.get("auto-routed")
        cheap_status = cheap.status if cheap is not None else None
        strong_status = strong.status if strong is not None else None
        auto_status = auto.status if auto is not None else None
        auto_tiers = [rt["tier"] for rt in auto.routes] if auto is not None else []
        flags: list[str] = []
        if auto_tiers[:1] == ["cheap"] and cheap_status in ("failed", "error", "stopped_budget"):
            flags.append("routed_cheap_cheap_failed")
        if strong_status == "solved" and cheap_status != "solved":
            flags.append("only_strong_solved")
        difficulty = next(
            (r.difficulty for r in report.results if r.task == task_id and r.difficulty), None
        )
        rows.append(
            {
                "task": task_id,
                "difficulty": difficulty,
                "cheap_only": cheap_status,
                "strong_only": strong_status,
                "auto_routed": auto_status,
                "auto_tiers": auto_tiers,
                "flags": flags,
            }
        )
    return rows


def ab_section(report: LiveReport) -> dict | None:
    if report.settings.get("ab") is None:
        return None
    return {
        "arms": report.settings["ab"]["arms"],
        "rows": [asdict(r) for r in summarize_arms(report)],
        "per_task_tiers": tier_rows(report),
        "note": AVOIDED_NOTE,
    }


def load_live_baseline(path: Path, task_ids: Sequence[str]) -> LiveBaseline:
    name = path.name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(
            f"cannot read baseline file {name}: {e.strerror or type(e).__name__}"
        ) from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid baseline file {name}: {e}") from e
    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        raise ConfigError(f"baseline {name}: [meta] must be a table")
    source = meta.get("source")
    if source is not None and not isinstance(source, str):
        raise ConfigError(f"baseline {name}: meta.source must be a string")
    tasks_raw = data.get("tasks")
    if not isinstance(tasks_raw, dict) or not tasks_raw:
        raise ConfigError(f"baseline file {name}: missing [tasks.<task_id>] tables")
    tasks: dict[str, BaselineEntry] = {}
    for tid, entry in tasks_raw.items():
        if tid not in task_ids:
            raise ConfigError(
                f"baseline {name}: unknown task id '{tid}'; known: {list(task_ids)}"
            )
        cost_msg = f"baseline {name}: tasks.{tid}.cost_usd must be a number >= 0"
        if not isinstance(entry, dict):
            raise ConfigError(cost_msg)
        cost = entry.get("cost_usd")
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not math.isfinite(cost)
            or cost < 0
        ):
            raise ConfigError(cost_msg)
        success = entry.get("success")
        if not isinstance(success, bool):
            raise ConfigError(f"baseline {name}: tasks.{tid}.success must be true or false")
        tasks[tid] = BaselineEntry(float(cost), success)
    return LiveBaseline(file=name, source=source, tasks=tasks)


def baseline_comparison(report: LiveReport, baseline: LiveBaseline | None) -> dict | None:
    if baseline is None:
        return None
    rows: list[dict[str, Any]] = []
    for model in report.settings["models"]:
        for protocol in report.settings["protocols"]:
            rs = [
                r
                for r in report.results
                if r.model == model["id"]
                and r.protocol == protocol
                and r.task in baseline.tasks
                and r.status not in UNRUN_STATUSES
            ]
            entries = [baseline.tasks[r.task] for r in rs]
            cora_cost = sum((r.cost_usd for r in rs), 0.0)
            cora_solved = sum(1 for r in rs if r.status == "solved")
            base_cost = sum((e.cost_usd for e in entries), 0.0)
            base_success = sum(1 for e in entries if e.success)
            cora_cps = cora_cost / cora_solved if cora_solved else None
            base_cps = base_cost / base_success if base_success else None
            ratio = cora_cps / base_cps if cora_cps is not None and base_cps is not None else None
            rows.append(
                {
                    "model": model["id"],
                    "protocol": protocol,
                    "tasks_compared": len(rs),
                    "cora_cost_usd": cora_cost,
                    "cora_solved": cora_solved,
                    "cora_cost_per_solved_usd": cora_cps,
                    "baseline_cost_usd": base_cost,
                    "baseline_solved": base_success,
                    "baseline_cost_per_solved_usd": base_cps,
                    "ratio": ratio,
                }
            )
    per_task: list[dict[str, Any]] = []
    for r in report.results:
        entry = baseline.tasks.get(r.task)
        per_task.append(
            {
                "task": r.task,
                "model": r.model,
                "protocol": r.protocol,
                "cora_status": r.status,
                "cora_cost_usd": r.cost_usd,
                "baseline_cost_usd": entry.cost_usd if entry is not None else None,
                "baseline_success": entry.success if entry is not None else None,
            }
        )
    return {
        "file": baseline.file,
        "source": baseline.source,
        "tasks_provided": len(baseline.tasks),
        "rows": rows,
        "per_task": per_task,
    }


def scrub(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        if len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    return text


def sensor_totals(report: LiveReport) -> dict:
    results = report.results
    return {
        "check_runs": sum(r.check_runs for r in results),
        "sensor_retries": sum(r.sensor_retries for r in results),
        "extra_calls": sum(r.sensor_calls for r in results),
        "extra_cost_usd": sum(r.sensor_cost_usd for r in results),
        "escalations": sum(1 for r in results if r.escalated),
    }


def report_json(
    report: LiveReport,
    baseline: LiveBaseline | None,
    secrets: Sequence[str] = (),
    include_aggregation: bool = True,
) -> str:
    obj = {
        "schema_version": 1,
        "generated_at": report.generated_at,
        "cora_version": cora.__version__,
        "settings": report.settings,
        "total_cost_usd": report.total_cost_usd,
        "total_calls": report.total_calls,
        "provider_cost_calls": report.provider_cost_calls,
        "budget_exhausted": report.budget_exhausted,
        "rows": [asdict(r) for r in summarize(report)],
        "results": [asdict(r) for r in report.results],
        "sensor_totals": sensor_totals(report),
        "baseline": baseline_comparison(report, baseline),
        "baseline_note": (
            "baseline not provided"
            if baseline is None
            else f"baseline provided: {baseline.file}"
        ),
        "difficulty_bins": difficulty_rows(report),
        "ab": ab_section(report),
        "aborted": report.aborted,
        "cells": cell_counts(report),
        "wall_s": report.wall_s,
        "latency": latency_section(report),
        "partial": report.partial,
        "partial_reason": report.partial_reason,
        "runs_planned": (
            report.runs_planned if report.runs_planned is not None else len(report.results)
        ),
        "runs_completed": report.runs_completed,
        "aggregation": _aggregation(report) if include_aggregation else None,
        "budget_plan": report.extras.get("budget_plan"),
        "trimmed": report.extras.get("trimmed"),
        "resumed": report.extras.get("resumed"),
        "e2e": e2e_section(report),
    }
    return scrub(json.dumps(obj, indent=2, ensure_ascii=False), secrets)


def _num(value: float | None, spec: str) -> str:
    return "n/a" if value is None else format(value, spec)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _yes_no(value: bool | None) -> str:
    return "n/a" if value is None else ("yes" if value else "no")


def _summary_lines(report: LiveReport) -> list[str]:
    settings = report.settings
    if settings.get("sensor", {}).get("enabled"):
        st = sensor_totals(report)
        src = settings["sensor"].get("source")
        no_check = settings["sensor"].get("no_check_tasks")
        no_check_part = f" no_check_tasks={','.join(no_check)}" if no_check else ""
        sensor_line = (
            f"sensor: on ({'source=' + src + ' ' if src else ''}check_runs={st['check_runs']} "
            f"retries={st['sensor_retries']} "
            f"extra_calls={st['extra_calls']} extra_cost_usd={st['extra_cost_usd']:.6f} "
            f"escalations={st['escalations']}{no_check_part})"
        )
    else:
        sensor_line = "sensor: off"
    lines = [
        f"total_spend_usd: {report.total_cost_usd:.6f} "
        f"(provider-reported calls: {report.provider_cost_calls}/{report.total_calls}; "
        "cost_source: provider_usage when provider-reported, else catalog:<id>@<provider>; "
        "self_hosted excluded)",
        f"budget: max_cost_usd={settings['max_cost_usd']} "
        f"max_task_cost_usd={settings['max_task_cost_usd']} "
        f"budget_exhausted={'yes' if report.budget_exhausted else 'no'}",
        f"tools: {', '.join(settings.get('tools', [])) or 'n/a'} "
        f"(groups: {', '.join(settings.get('tool_groups', [])) or 'n/a'})",
        sensor_line,
        f"wall_s: {_num(report.wall_s, '.2f')} (sum of cell latencies "
        f"{sum(r.latency_s for r in report.results):.2f})",
    ]
    if report.aborted is not None:
        c = cell_counts(report)
        lines += [
            f"aborted: {report.aborted}",
            f"cells: executed={c['executed']} not_run={c['not_run']} "
            f"skipped_budget={c['skipped_budget']}",
        ]
    planned = report.runs_planned if report.runs_planned is not None else len(report.results)
    lines.append(
        f"runs: completed {report.runs_completed}/{planned} "
        f"(repeats={settings.get('repeats', 1)}, seed={settings.get('seed', 0)})"
    )
    if report.partial:
        lines.append(f"partial: yes ({report.partial_reason})")
    t = report.extras.get("trimmed")
    if t:
        lines.append(
            f"trimmed: --repeats {t['requested_repeats']} -> {t['used_repeats']} to fit "
            f"--max-cost {t['max_cost_usd']} (estimated max "
            f"${t['estimated_max_usd_before']:.6f} -> ${t['estimated_max_usd_after']:.6f})"
        )
    resumed = report.extras.get("resumed")
    if resumed:
        lines.append(
            f"resumed: {resumed['reused_runs']} completed run(s) reused without calls"
        )
    plan = report.extras.get("budget_plan")
    if plan:
        if plan["total_max_usd"] is None:
            lines.append("budget plan: unbounded/unknown")
        else:
            lines.append(
                f"budget plan: estimated max ${plan['total_max_usd']:.6f} for "
                f"{plan['runs']} runs (conservative upper bound)"
            )
    return lines


def _latency_lines(report: LiveReport) -> list[str]:
    sec = latency_section(report)
    lines = [
        f"### Call latency (per LLM call, wall clock; stall = call > "
        f"{sec['stall_threshold_s']:g}s)",
        "",
        "| config | calls | p50_s | max_s | stalled_calls |",
        "|---|---|---|---|---|",
    ]
    for row in sec["configs"]:
        lines.append(
            f"| {row['config']} | {row['calls']} | {_num(row['p50_s'], '.2f')} | "
            f"{_num(row['max_s'], '.2f')} | {row['stalled_calls']} |"
        )
    lines += [
        "",
        "| task | config | calls | p50_s | max_s | stalled_calls | stall |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in sec["cells"]:
        lines.append(
            f"| {row['task']} | {row['config']} | {row['calls']} | "
            f"{_num(row['p50_s'], '.2f')} | {_num(row['max_s'], '.2f')} | "
            f"{row['stalled_calls']} | {'STALL' if row['stall'] else '-'} |"
        )
    return lines


def _baseline_lines(report: LiveReport, baseline: LiveBaseline | None) -> list[str]:
    cmp = baseline_comparison(report, baseline)
    if cmp is None:
        return ["baseline: baseline not provided"]
    lines = [
        f"baseline: {cmp['file']}",
        "",
        "| model | protocol | tasks_compared | cora_cost_per_solved_usd | "
        "baseline_cost_per_solved_usd | ratio |",
        "|---|---|---|---|---|---|",
    ]
    for row in cmp["rows"]:
        lines.append(
            f"| {row['model']} | {row['protocol']} | {row['tasks_compared']} | "
            f"{_num(row['cora_cost_per_solved_usd'], '.6f')} | "
            f"{_num(row['baseline_cost_per_solved_usd'], '.6f')} | "
            f"{_num(row['ratio'], '.2f')} |"
        )
    lines += [
        "",
        "| task | model | protocol | cora_status | cora_cost_usd | baseline_cost_usd | "
        "baseline_success |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in cmp["per_task"]:
        lines.append(
            f"| {row['task']} | {row['model']} | {row['protocol']} | "
            f"{row['cora_status']} | {row['cora_cost_usd']:.6f} | "
            f"{_num(row['baseline_cost_usd'], '.6f')} | "
            f"{_yes_no(row['baseline_success'])} |"
        )
    return lines


def _difficulty_table(report: LiveReport) -> list[str]:
    return [
        "| config | bin | tasks | solved | cost_usd | wall_s |",
        "|---|---|---|---|---|---|",
        *(
            f"| {row['config']} | {row['bin']} | {row['tasks']} | {row['solved']} | "
            f"{row['cost_usd']:.6f} | {row['wall_s']:.2f} |"
            for row in difficulty_rows(report)
        ),
    ]


def _ab_markdown(report: LiveReport, baseline: LiveBaseline | None, secrets: Sequence[str]) -> str:
    ab = report.settings["ab"]
    lines = [
        f"## CORA live bench A/B ({report.generated_at})",
        "",
        f"arms: {', '.join(ab['arms'])} | model: {ab['model']} | "
        f"strong model: {ab.get('strong_model') or 'n/a'} | protocol: {ab['protocol']}",
        "",
        "| arm | model | attempted | solved | skipped | solve_rate | total_cost_usd | "
        "cost_per_solved_usd | resolved_per_dollar | wall_s | avg_latency_s | deleg_calls | "
        "deleg_attempts | deleg_explore | deleg_general | deleg_ok | deleg_failed | "
        "deleg_refused | deleg_in | deleg_out | deleg_cost_usd | deleg_wall_s | "
        "deleg_max_fanout | avoided_tokens_est |",
        "|" + "---|" * 24,
    ]
    for row in summarize_arms(report):
        name = f"{row.arm} ({row.alias})" if row.alias else row.arm
        lines.append(
            f"| {name} | {row.model} | {row.attempted} | {row.solved} | {row.skipped} | "
            f"{_pct(row.solve_rate)} | {row.total_cost_usd:.6f} | "
            f"{_num(row.cost_per_solved_usd, '.6f')} | "
            f"{_num(row.resolved_per_dollar, '.2f')} | {row.wall_s:.2f} | "
            f"{_num(row.avg_latency_s, '.2f')} | {row.deleg_invocations} | {row.deleg_attempts} | "
            f"{row.deleg_explore} | {row.deleg_general} | {row.deleg_ok} | {row.deleg_failed} | "
            f"{row.deleg_refused} | {row.deleg_input_tokens} | {row.deleg_output_tokens} | "
            f"{row.deleg_cost_usd:.6f} | {row.deleg_wall_s:.2f} | {row.deleg_max_fanout} | "
            f"{row.deleg_avoided_tokens_est} |"
        )
    lines += ["", AVOIDED_NOTE, "", DIFF_HEADING, "", *_difficulty_table(report)]
    tiers = tier_rows(report)
    if tiers is not None:
        lines += [
            "",
            "### Model tiers per task",
            "",
            "| task | difficulty | cheap-only | strong-only | auto-routed | auto tiers | flags |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in tiers:
            lines.append(
                f"| {row['task']} | {row['difficulty'] or 'n/a'} | "
                f"{row['cheap_only'] or 'n/a'} | {row['strong_only'] or 'n/a'} | "
                f"{row['auto_routed'] or 'n/a'} | {'>'.join(row['auto_tiers']) or 'n/a'} | "
                f"{', '.join(row['flags']) or '-'} |"
            )
    lines += [
        "",
        *_summary_lines(report),
        "",
        "| task | arm | model | status | calls | cost_usd | latency_s |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in report.results:
        lines.append(
            f"| {t.task} | {t.arm} | {t.model} | {t.status} | {t.calls} | "
            f"{t.cost_usd:.6f} | {t.latency_s:.2f} |"
        )
    lines += ["", *_baseline_lines(report, baseline)]
    e2e = _e2e_lines(report)
    if e2e:
        lines += ["", *e2e]
    lines += ["", *aggregation_lines(_aggregation(report))]
    lines += ["", *_latency_lines(report)]
    return scrub("\n".join(lines) + "\n", secrets)


def report_markdown(
    report: LiveReport, baseline: LiveBaseline | None, secrets: Sequence[str] = ()
) -> str:
    if report.settings.get("ab") is not None:
        return _ab_markdown(report, baseline, secrets)
    lines = [
        f"## CORA live bench ({report.generated_at})",
        "",
        "| model | protocol | attempted | solved | failed | skipped | solve_rate | "
        "total_cost_usd | cost_per_solved_usd | input_tokens | output_tokens | avg_calls | "
        "avg_latency_s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summarize(report):
        lines.append(
            f"| {r.model} | {r.protocol} | {r.attempted} | {r.solved} | {r.failed} | "
            f"{r.skipped} | {_pct(r.solve_rate)} | {r.total_cost_usd:.6f} | "
            f"{_num(r.cost_per_solved_usd, '.6f')} | {r.input_tokens} | {r.output_tokens} | "
            f"{_num(r.avg_calls, '.2f')} | {_num(r.avg_latency_s, '.2f')} |"
        )
    lines += [
        "",
        *_summary_lines(report),
        "",
        "| task | model | protocol | status | calls | cost_usd | latency_s |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in report.results:
        lines.append(
            f"| {t.task} | {t.model} | {t.protocol} | {t.status} | {t.calls} | "
            f"{t.cost_usd:.6f} | {t.latency_s:.2f} |"
        )
    lines.append("")
    lines += _baseline_lines(report, baseline)
    if any(r.difficulty is not None for r in report.results):
        lines += ["", DIFF_HEADING, "", *_difficulty_table(report)]
    e2e = _e2e_lines(report)
    if e2e:
        lines += ["", *e2e]
    lines += ["", *aggregation_lines(_aggregation(report))]
    lines += ["", *_latency_lines(report)]
    return scrub("\n".join(lines) + "\n", secrets)
