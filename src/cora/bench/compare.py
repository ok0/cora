from __future__ import annotations

import datetime
import json
import math
import tomllib
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from cora.bench.aggregate import Run, config_label
from cora.bench.e2e import load_e2e_tasks
from cora.bench.live_tasks import ALL_TASK_IDS
from cora.bench.report import completed_status
from cora.bench.stats import fmt_interval_pct, fmt_sig, solve_verdict, wilson_interval
from cora.core.errors import ConfigError

SYNTHETIC_BANNER = (
    "!! SYNTHETIC BASELINE: example numbers, not measurements "
    "(SYNTHETIC / EXAMPLE, 실제 측정값 아님) !!"
)
NO_BASELINE_NOTE = "baseline 없음: 비교 생략 (no baseline: comparison skipped)"
BASELINE_N1_NOTE = "baseline n=1, 비교 불확실 (comparison uncertain)"
META_FIELDS = ("tool", "model", "date", "source", "synthetic")
TASK_FIELDS = ("solved", "cost_usd", "wall_s", "n", "note")
SOLVE_ONLY_NOTE = (
    "note: the verdict compares solve rates only; the baseline carries a mean cost per run "
    "and no per-run values, so no cost verdict is given"
)
COST_SOURCE_NOTE = (
    "cost_source: CORA cost uses provider_usage when the provider reported it, else "
    "catalog:<id>@<provider> configured prices; self_hosted calls are excluded"
)


def example_baseline_path() -> Path:
    return Path(str(resources.files("cora") / "data" / "baseline.example.toml"))


@dataclass(frozen=True)
class BaselineMeta:
    tool: str
    model: str
    date: str
    source: str
    synthetic: bool


@dataclass(frozen=True)
class BaselineTask:
    task: str
    solve_rate: float
    n: int
    cost_usd: float
    wall_s: float
    note: str | None

    @property
    def solved_k(self) -> float:
        return self.solve_rate * self.n


@dataclass(frozen=True)
class CompareBaseline:
    file: str
    meta: BaselineMeta
    tasks: dict[str, BaselineTask]
    warnings: tuple[str, ...]


def known_task_ids() -> set[str]:
    try:
        e2e_ids = {t.id for t in load_e2e_tasks()}
    except ConfigError:
        e2e_ids = set()
    return set(ALL_TASK_IDS) | e2e_ids


def _non_negative(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def load_compare_baseline(
    path: Path, known_ids: Collection[str] | None = None
) -> CompareBaseline:
    name = path.name

    def fail(msg: str) -> ConfigError:
        return ConfigError(f"baseline {name}: {msg}")

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        reason = getattr(e, "strerror", None) or type(e).__name__
        raise fail(f"cannot read baseline file {name}: {reason}") from None
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise fail(f"invalid baseline file {name}: {e}") from None

    for key in data:
        if key not in ("meta", "tasks"):
            raise fail(f"unknown top-level key '{key}' (allowed: meta, tasks)")
    meta_raw = data.get("meta")
    if not isinstance(meta_raw, dict):
        raise fail(f"missing [meta] table (required: {', '.join(META_FIELDS)})")

    def meta_text(field: str) -> str:
        value = meta_raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise fail(f"meta.{field} is required (non-empty string)")
        return value

    tool = meta_text("tool")
    model = meta_text("model")
    date_raw = meta_raw.get("date")
    if isinstance(date_raw, (datetime.date, datetime.datetime)):
        date = str(date_raw)
    elif isinstance(date_raw, str):
        date = date_raw
    else:
        raise fail("meta.date is required (string or TOML date)")
    source = meta_text("source")
    synthetic = meta_raw.get("synthetic")
    if not isinstance(synthetic, bool):
        raise fail("meta.synthetic is required (true or false)")

    tasks_raw = data.get("tasks")
    if not isinstance(tasks_raw, dict) or not tasks_raw:
        raise fail("no [tasks.<task_id>] tables")
    tasks: dict[str, BaselineTask] = {}
    warnings: list[str] = []
    for tid, entry in tasks_raw.items():
        if not isinstance(entry, dict):
            raise fail(f"tasks.{tid} must be a table")
        for key in entry:
            if key not in TASK_FIELDS:
                raise fail(
                    f"tasks.{tid}.{key} is not a known field "
                    f"(allowed: {', '.join(TASK_FIELDS)})"
                )
        solved = entry.get("solved")
        if isinstance(solved, bool):
            rate = 1.0 if solved else 0.0
        elif isinstance(solved, (int, float)) and math.isfinite(solved) and 0 <= solved <= 1:
            rate = float(solved)
        else:
            raise fail(
                f"tasks.{tid}.solved is required (true/false or a number between 0 and 1)"
            )
        for field in ("cost_usd", "wall_s"):
            if not _non_negative(entry.get(field)):
                raise fail(f"tasks.{tid}.{field} is required (number >= 0)")
        n = entry.get("n", 1)
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise fail(f"tasks.{tid}.n must be an integer >= 1")
        note = entry.get("note")
        if note is not None and not isinstance(note, str):
            raise fail(f"tasks.{tid}.note must be a string")
        if known_ids is not None and tid not in known_ids:
            warnings.append(
                f"baseline {name}: task id '{tid}' is not a CORA bench task; "
                "it is listed as unmatched"
            )
        tasks[tid] = BaselineTask(
            task=tid,
            solve_rate=rate,
            n=n,
            cost_usd=float(entry["cost_usd"]),
            wall_s=float(entry["wall_s"]),
            note=note,
        )
    return CompareBaseline(
        file=name,
        meta=BaselineMeta(
            tool=tool,
            model=model,
            date=date,
            source=source,
            synthetic=synthetic,
        ),
        tasks=tasks,
        warnings=tuple(warnings),
    )


def load_report_runs(path: Path) -> tuple[dict, list[Run]]:
    name = path.name

    def fail(msg: str) -> ConfigError:
        return ConfigError(f"invalid report file {name}: {msg}")

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise fail(f"cannot read file ({e.strerror or type(e).__name__})") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise fail(f"not valid JSON ({e})") from None
    raw = obj.get("results") if isinstance(obj, dict) else None
    if not isinstance(raw, list):
        raise fail("results must be a list")
    runs: list[Run] = []
    try:
        for d in raw:
            if not completed_status(
                d["status"], d.get("budget_reason"), d.get("aborted_run", False)
            ):
                continue
            runs.append(
                Run(
                    arm=d.get("arm"),
                    model=d["model"],
                    protocol=d["protocol"],
                    task=d["task"],
                    solved=d["status"] == "solved",
                    cost_usd=float(d["cost_usd"]),
                    tokens=int(d.get("input_tokens", 0)) + int(d.get("output_tokens", 0)),
                    wall_s=float(d.get("latency_s", 0.0)),
                    score=d.get("score"),
                )
            )
    except (KeyError, TypeError, ValueError) as e:
        raise fail(f"malformed result entry ({type(e).__name__}: {e})") from None
    return obj, runs


def _iv(iv: tuple[float, float] | None) -> list[float] | None:
    return list(iv) if iv is not None else None


def _ratio(num: float | None, den: float | None) -> float | None:
    return num / den if num is not None and den is not None and den > 0 else None


def _plain_fields(k: int, n: int, total: float) -> dict[str, Any]:
    return {
        "cora_solved": k,
        "cora_n": n,
        "cora_solve_rate": k / n,
        "cora_wilson95": _iv(wilson_interval(k, n)),
        "cora_mean_cost_usd": total / n,
    }


def _plain_summary(parts: list[tuple[int, int, float]]) -> dict[str, Any]:
    k = sum(p[0] for p in parts)
    n = sum(p[1] for p in parts)
    total = sum(p[2] for p in parts)
    return {
        "task": "ALL",
        **_plain_fields(k, n, total),
        "cora_cost_per_solved_usd": total / k if k else None,
        "cora_solved_per_dollar": k / total if total > 0 else None,
    }


def _joined_summary(parts: list[tuple[int, int, float, float, int, float]]) -> dict[str, Any]:
    k = sum(p[0] for p in parts)
    n = sum(p[1] for p in parts)
    total = sum(p[2] for p in parts)
    bk = sum(p[3] for p in parts)
    bn = sum(p[4] for p in parts)
    base_total = sum(p[5] for p in parts)
    spd = k / total if total > 0 else None
    base_spd = bk / base_total if base_total > 0 else None
    summary: dict[str, Any] = {
        "task": "ALL",
        "cora_solved": k,
        "cora_n": n,
        "cora_solve_rate": k / n if n else None,
        "cora_wilson95": _iv(wilson_interval(k, n)) if n else None,
        "cora_mean_cost_usd": total / n if n else None,
        "cora_solved_per_dollar": spd,
        "baseline_solved": bk,
        "baseline_n": bn,
        "baseline_solve_rate": bk / bn if bn else None,
        "baseline_cost_usd": base_total / bn if bn else None,
        "baseline_solved_per_dollar": base_spd,
        "spd_ratio": _ratio(spd, base_spd),
        "verdict": None,
    }
    if n and bn:
        verdict = solve_verdict("CORA", k, n, "baseline", round(bk), bn)
        if any(p[4] == 1 for p in parts):
            verdict += "; " + BASELINE_N1_NOTE
        summary["verdict"] = verdict
    return summary


def compare(
    report_obj: dict,
    runs: list[Run],
    baseline: CompareBaseline | None,
    report_name: str,
    notes: Sequence[str] = (),
) -> dict:
    groups: dict[str, dict[str, list[Run]]] = {}
    for r in runs:
        label = config_label(r.arm, r.model, r.protocol)
        groups.setdefault(label, {}).setdefault(r.task, []).append(r)
    run_tasks = {r.task for r in runs}
    cora_only: list[str] = []
    configs: list[dict] = []
    for label, by_task in groups.items():
        rows: list[dict] = []
        plain_parts: list[tuple[int, int, float]] = []
        joined_parts: list[tuple[int, int, float, float, int, float]] = []
        for tid, group in by_task.items():
            k = sum(1 for r in group if r.solved)
            n = len(group)
            total = sum(r.cost_usd for r in group)
            spd = k / total if total > 0 else None
            if baseline is None:
                plain_parts.append((k, n, total))
                rows.append({
                    "task": tid,
                    **_plain_fields(k, n, total),
                    "cora_cost_per_solved_usd": total / k if k else None,
                    "cora_solved_per_dollar": spd,
                })
                continue
            bt = baseline.tasks.get(tid)
            if bt is None:
                if tid not in cora_only:
                    cora_only.append(tid)
                continue
            base_total = bt.cost_usd * bt.n
            base_spd = bt.solved_k / base_total if base_total > 0 else None
            verdict = solve_verdict("CORA", k, n, "baseline", round(bt.solved_k), bt.n)
            if bt.n == 1:
                verdict += "; " + BASELINE_N1_NOTE
            joined_parts.append((k, n, total, bt.solved_k, bt.n, base_total))
            rows.append({
                "task": tid,
                **_plain_fields(k, n, total),
                "cora_solved_per_dollar": spd,
                "baseline_solved": bt.solved_k,
                "baseline_n": bt.n,
                "baseline_solve_rate": bt.solve_rate,
                "baseline_cost_usd": bt.cost_usd,
                "baseline_wall_s": bt.wall_s,
                "baseline_solved_per_dollar": base_spd,
                "spd_ratio": _ratio(spd, base_spd),
                "verdict": verdict,
            })
        if baseline is None:
            summary = _plain_summary(plain_parts)
        else:
            summary = _joined_summary(joined_parts)
        configs.append({"config": label, "rows": rows, "summary": summary})
    baseline_only: list[str] = []
    if baseline is not None:
        baseline_only = [tid for tid in baseline.tasks if tid not in run_tasks]
    return {
        "banner": SYNTHETIC_BANNER if baseline is not None and baseline.meta.synthetic else None,
        "synthetic": baseline is not None and baseline.meta.synthetic,
        "report": report_name,
        "report_partial": bool(report_obj.get("partial")),
        "report_partial_reason": report_obj.get("partial_reason"),
        "baseline": None if baseline is None else {
            "file": baseline.file,
            "tool": baseline.meta.tool,
            "model": baseline.meta.model,
            "date": baseline.meta.date,
            "source": baseline.meta.source,
            "synthetic": baseline.meta.synthetic,
        },
        "notes": [*notes, *([NO_BASELINE_NOTE] if baseline is None else [])],
        "warnings": list(baseline.warnings) if baseline is not None else [],
        "configs": configs,
        "unmatched": {"cora_only": cora_only, "baseline_only": baseline_only},
    }


def _usd(v: float | None) -> str:
    return "n/a" if v is None else "$" + fmt_sig(v)


def _solve_text(k: float, n: int) -> str:
    if abs(k - round(k)) < 1e-9:
        return f"{round(k)}/{n}"
    return f"{fmt_sig(k)}/{n}"


def _plain_table(cfg: dict) -> list[str]:
    lines = [
        "| task | CORA solve | Wilson 95% | CORA cost | cost per solved | solved per dollar |",
        "|---|---|---|---|---|---|",
    ]
    for r in [*cfg["rows"], cfg["summary"]]:
        if r["cora_cost_per_solved_usd"] is None and r["cora_solved"] == 0:
            per_solved = "unsolved"
        else:
            per_solved = _usd(r["cora_cost_per_solved_usd"])
        lines.append(
            f"| {r['task']} | {r['cora_solved']}/{r['cora_n']} | "
            f"{fmt_interval_pct(r['cora_wilson95'])} | {_usd(r['cora_mean_cost_usd'])} | "
            f"{per_solved} | {fmt_sig(r['cora_solved_per_dollar'])} |"
        )
    return lines


def _joined_table(cfg: dict) -> list[str]:
    lines = [
        "| task | CORA solve | baseline solve | CORA cost | baseline cost | "
        "solved-per-dollar ratio | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in [*cfg["rows"], cfg["summary"]]:
        lines.append(
            f"| {r['task']} | {r['cora_solved']}/{r['cora_n']} | "
            f"{_solve_text(r['baseline_solved'], r['baseline_n'])} | "
            f"{_usd(r['cora_mean_cost_usd'])} | {_usd(r['baseline_cost_usd'])} | "
            f"{fmt_sig(r['spd_ratio'])} | {r['verdict'] or 'n/a'} |"
        )
    return lines


def compare_markdown(cmp: dict) -> str:
    base = cmp["baseline"]
    lines: list[str] = []
    if cmp["banner"]:
        lines.append(cmp["banner"])
    if base is None:
        lines.append("## CORA bench results (no baseline)")
    else:
        lines.append(f"## CORA vs baseline ({base['tool']} {base['model']}, {base['date']})")
        lines.append(f"source: {base['source']}")
    head = f"report: {cmp['report']}"
    if base is not None:
        head += f" | baseline: {base['file']}"
    lines.append(head)
    lines.append(COST_SOURCE_NOTE)
    if cmp["report_partial"]:
        lines.append(f"note: report is partial ({cmp['report_partial_reason']})")
    if base is not None:
        lines.append(SOLVE_ONLY_NOTE)
    lines.extend(cmp["notes"])
    lines.extend(cmp["warnings"])
    for cfg in cmp["configs"]:
        lines += ["", f"### {cfg['config']}", ""]
        lines += _plain_table(cfg) if base is None else _joined_table(cfg)
    unmatched = cmp["unmatched"]
    if unmatched["cora_only"] or unmatched["baseline_only"]:
        cora_only = ", ".join(unmatched["cora_only"]) or "-"
        baseline_only = ", ".join(unmatched["baseline_only"]) or "-"
        lines += ["", f"unmatched: CORA only: {cora_only} | baseline only: {baseline_only}"]
    return "\n".join(lines)
