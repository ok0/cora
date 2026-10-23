from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cora.bench import stats
from cora.bench.report import completed_status

ARM_LABELS = {
    "A": "A cheap",
    "B": "B cheap+auto-sensor",
    "C": "C strong",
    "D": "auto-routed (derived)",
}

M12_ROUTES: dict[str, str] = {
    "query_client_timeout": "cheap",
    "query_total_backoff": "cheap",
    "query_env_override": "cheap",
    "multi_edit_delay_cap": "cheap",
    "multi_edit_rename_cents": "cheap",
    "multi_edit_region": "cheap",
    "e2e_todo_cli": "cheap",
    "e2e_text_stats": "cheap",
    "e2e_rest_notes": "cheap",
    "e2e_md_to_html": "cheap",
    "e2e_refactor_inventory": "cheap",
}

SATURATION_RULE = (
    ".ensemble/remediation-plan.md weakness row 8: cheap lower bound overlaps strong upper bound "
    "and both >= 90% -> saturated"
)

_KEYS = ("A", "B", "C")


def load_report(dir: Path) -> dict:
    return json.loads((dir / "report.json").read_text(encoding="utf-8"))


def merge_reports(arms: Mapping[str, Sequence[Path]]) -> dict:
    bad = [k for k in arms if k not in _KEYS]
    if bad:
        raise ValueError(f"unknown arm key(s): {', '.join(sorted(bad))}")
    results: list[dict] = []
    reasons: list[str] = []
    partial = False
    sources: dict[str, list[str]] = {}
    for key, dirs in arms.items():
        label = ARM_LABELS[key]
        sources[label] = [str(p) for p in dirs]
        for d in dirs:
            rep = load_report(Path(d))
            if rep.get("partial"):
                partial = True
            reason = rep.get("partial_reason")
            if reason:
                reasons.append(str(reason))
            for row in rep.get("results", []):
                item = dict(row)
                item["arm"] = label
                results.append(item)
    return {
        "results": results,
        "partial": partial,
        "partial_reason": "; ".join(reasons) or None,
        "settings": {"m15_sources": sources},
    }


def derive_routed(merged: dict, routes: Mapping[str, str] = M12_ROUTES) -> dict:
    results = [dict(r) for r in merged.get("results", [])]
    missing: list[str] = []
    for task, route in routes.items():
        if route == "cheap":
            source_arm = ARM_LABELS["A"]
        elif route == "strong":
            source_arm = ARM_LABELS["C"]
        else:
            raise ValueError(f"unknown route for {task}: {route}")
        rows = [
            r
            for r in merged.get("results", [])
            if r.get("arm") == source_arm and r.get("task") == task
        ]
        if not rows:
            missing.append(task)
        for r in rows:
            item = dict(r)
            item["arm"] = ARM_LABELS["D"]
            item["derived"] = True
            results.append(item)
    settings = dict(merged.get("settings", {}))
    settings["derived_missing"] = missing
    settings["derived_rule"] = (
        "per-task route from M12 table; cheap→arm A runs, strong→arm C runs; zero extra spend"
    )
    out = dict(merged)
    out["results"] = results
    out["settings"] = settings
    return out


@dataclass(frozen=True)
class Cell:
    arm: str
    task: str
    k: int
    n: int
    wilson: tuple[float, float] | None
    total_cost: float
    mean_cost: float | None
    solved_per_dollar: float | None
    stop_reasons: dict[str, int]
    check_runs: tuple[int, ...]


def _stop_reason(row: dict) -> str:
    return str(row.get("end_reason") or row.get("stop_reason") or row.get("status"))


def cells(merged: dict) -> list[Cell]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in merged.get("results", []):
        groups.setdefault((row["arm"], row["task"]), []).append(row)
    out: list[Cell] = []
    for (arm, task), rows in sorted(groups.items()):
        done = [
            r
            for r in rows
            if completed_status(r["status"], r.get("budget_reason"), r.get("aborted_run", False))
        ]
        n = len(done)
        k = sum(1 for r in done if r["status"] == "solved")
        total_cost = float(sum(float(r.get("cost_usd") or 0.0) for r in rows))
        stop_reasons: dict[str, int] = {}
        for r in rows:
            reason = _stop_reason(r)
            if arm == ARM_LABELS["B"] and r.get("check_runs") == 0 and reason != "final_answer":
                reason = f"{reason}+gate not reached"
            stop_reasons[reason] = stop_reasons.get(reason, 0) + 1
        out.append(
            Cell(
                arm=arm,
                task=task,
                k=k,
                n=n,
                wilson=stats.wilson_interval(k, n),
                total_cost=total_cost,
                mean_cost=total_cost / len(rows) if rows else None,
                solved_per_dollar=k / total_cost if total_cost > 0 else None,
                stop_reasons=stop_reasons,
                check_runs=tuple(r.get("check_runs") for r in rows),
            )
        )
    return out


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def saturation(a: Cell | None, c: Cell | None) -> str:
    if a is None or c is None or a.n < 3 or c.n < 3:
        return "blocked"
    if a.wilson is None or c.wilson is None:
        return "blocked"
    if _overlap(a.wilson, c.wilson):
        if a.k / a.n >= 0.9 and c.k / c.n >= 0.9:
            return "saturated"
        return "inconclusive"
    return "gap"


def log_counts(report_dir: Path) -> dict[str, int]:
    counts = {"evicted": 0, "parse_repaired": 0, "parse_error": 0}
    for path in (report_dir / "state" / "memory").glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("kind") == "evicted":
                counts["evicted"] += 1
    for path in (report_dir / "state" / "sessions").glob("*/events.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            kind = json.loads(line).get("type")
            if kind == "parse_repaired":
                counts["parse_repaired"] += 1
            elif kind == "parse_error":
                counts["parse_error"] += 1
    return counts


def _cell_text(c: Cell | None) -> str:
    if c is None:
        return "n/a"
    return f"{c.k}/{c.n}"


def cells_markdown(cs: list[Cell], verdicts: Mapping[str, str]) -> str:
    lines = [
        "| arm | task | solved k/n | Wilson 95% | total $ | $/run | solved/$ "
        "| stop reasons | check_runs |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cs:
        mean = f"{c.mean_cost:.4f}" if c.mean_cost is not None else "n/a"
        spd = f"{c.solved_per_dollar:.2f}" if c.solved_per_dollar is not None else "n/a"
        reasons = "; ".join(f"{k}: {v}" for k, v in sorted(c.stop_reasons.items()))
        checks = ",".join(str(x) for x in c.check_runs)
        lines.append(
            f"| {c.arm} | {c.task} | {c.k}/{c.n} | {stats.fmt_interval_pct(c.wilson)} | "
            f"{c.total_cost:.4f} | {mean} | {spd} | {reasons} | {checks} |"
        )
    lines.append("")
    lines.append("| task | A | C | verdict |")
    lines.append("|---|---|---|---|")
    by_key = {(c.arm, c.task): c for c in cs}
    a_label = ARM_LABELS["A"]
    c_label = ARM_LABELS["C"]
    for task in sorted(verdicts):
        a = by_key.get((a_label, task))
        c = by_key.get((c_label, task))
        lines.append(f"| {task} | {_cell_text(a)} | {_cell_text(c)} | {verdicts[task]} |")
    non_blocked = [v for v in verdicts.values() if v != "blocked"]
    overall = "saturated" if all(v == "saturated" for v in non_blocked) else "not saturated"
    lines.append("")
    lines.append(f"| overall | | | {overall} |")
    lines.append("")
    lines.append(f"Saturation rule: {SATURATION_RULE}")
    return "\n".join(lines) + "\n"


def _parse_arm(value: str) -> tuple[str, list[Path]]:
    key, sep, dirs = value.partition("=")
    if not sep or not dirs:
        raise argparse.ArgumentTypeError(f"expected KEY=DIR[,DIR...], got {value!r}")
    return key, [Path(d) for d in dirs.split(",") if d]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m15_tables")
    parser.add_argument("--arm", action="append", type=_parse_arm, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    arms: dict[str, list[Path]] = {}
    for key, dirs in args.arm:
        arms.setdefault(key, []).extend(dirs)
    merged = merge_reports(arms)
    derived = derive_routed(merged)
    cs = cells(derived)
    by_key = {(c.arm, c.task): c for c in cs}
    tasks = sorted({c.task for c in cs})
    verdicts = {
        t: saturation(by_key.get((ARM_LABELS["A"], t)), by_key.get((ARM_LABELS["C"], t)))
        for t in tasks
    }
    counts: dict[str, dict[str, int]] = {}
    for key, dirs in arms.items():
        total = {"evicted": 0, "parse_repaired": 0, "parse_error": 0}
        for d in dirs:
            for name, value in log_counts(Path(d)).items():
                total[name] += value
        counts[ARM_LABELS[key]] = total
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / "report.json"
    cells_path = args.out / "cells.md"
    counts_path = args.out / "counts.json"
    report_path.write_text(json.dumps(derived, ensure_ascii=False, indent=2), encoding="utf-8")
    cells_path.write_text(cells_markdown(cs, verdicts), encoding="utf-8")
    counts_path.write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    for p in (report_path, cells_path, counts_path):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
