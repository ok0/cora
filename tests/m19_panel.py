from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from cora.bench.compare import CompareBaseline, load_compare_baseline
from cora.bench.report import completed_status
from cora.bench.stats import wilson_interval
from cora.core.errors import ConfigError

LABEL_RE = re.compile(r"[A-Za-z0-9_.-]+")
DEFAULT_THRESHOLDS = "0.70,0.40,2.0"
THRESHOLD_HELP = "--thresholds must be A,B,COST e.g. 0.70,0.40,2.0 (1 >= A > B > 0, COST > 0)"
EXCLUDED_CLASS_ARMS = ("e", "strong-only", "g")
MIN_N = 3
HARD_F = ("e2e_h01", "e2e_h02", "e2e_h03", "e2e_h04", "e2e_h05", "e2e_h06")
HARD_X = ("e2e_hx1", "e2e_hx2")
_B_TASKS = HARD_F + ("e2e_hx2",)
REGISTERED_TASKS: dict[str, tuple[str, ...]] = {
    "a": HARD_F + HARD_X,
    "e": HARD_F + HARD_X,
    "b": _B_TASKS,
    "c_s": _B_TASKS,
    "c_cc": _B_TASKS,
    "d1": HARD_X,
    "d2": HARD_X,
    "g": HARD_F,
}
MECHANISMS = ("b", "c_s", "c_cc", "d1")
NO_BASELINE = "none"
ERROR_POLICIES = ("unsolved", "exclude", "replace")
COST_BASES = ("report", "billed")
SLOW_CALL_S = 90.0


class PanelError(Exception):
    pass


@dataclass(frozen=True)
class Row:
    arm: str
    model: str
    task: str
    solved: bool
    cost_usd: float
    wall_s: float
    deleg_attempts: int
    deleg_attempts_unparsed: int
    deleg_started: int
    source: str = ""
    repeat_index: int | None = None
    status: str = ""
    call_latencies_s: tuple[float, ...] = ()


def parse_thresholds(text: str) -> tuple[float, float, float]:
    parts = text.split(",")
    if len(parts) != 3:
        raise PanelError(THRESHOLD_HELP)
    try:
        a, b, m = (float(part) for part in parts)
    except ValueError:
        raise PanelError(THRESHOLD_HELP) from None
    if not all(math.isfinite(x) for x in (a, b, m)):
        raise PanelError(THRESHOLD_HELP)
    if not (1 >= a > b > 0 and m > 0):
        raise PanelError(THRESHOLD_HELP)
    return a, b, m


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _malformed(path: str, detail: str) -> PanelError:
    return PanelError(f"malformed report {path}: {detail}")


def load_rows(spec: str) -> list[Row]:
    label: str | None = None
    tasks: set[str] | None = None
    path_text = spec
    left, sep, right = spec.partition("=")
    if sep and "@" in left:
        label_text, _, task_csv = left.partition("@")
        names = task_csv.split(",")
        if not (
            LABEL_RE.fullmatch(label_text)
            and all(LABEL_RE.fullmatch(name) for name in names)
        ):
            raise PanelError(
                f"bad label spec {left}: use LABEL or LABEL@TASK,TASK=path"
            )
        label, tasks, path_text = label_text, set(names), right
    elif sep and LABEL_RE.fullmatch(left):
        label, path_text = left, right
    try:
        text = Path(path_text).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise PanelError(f"cannot read report {path_text}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise _malformed(path_text, f"invalid JSON ({e.msg})") from None
    if not isinstance(data, dict):
        raise _malformed(path_text, "top level must be an object")
    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        raise _malformed(path_text, "settings must be an object")
    results = data.get("results")
    if not isinstance(results, list):
        raise _malformed(path_text, "no results list")
    rows: list[Row] = []
    for index, item in enumerate(results):
        where = f"results[{index}]"
        if not isinstance(item, dict):
            raise _malformed(path_text, f"{where} must be an object")
        for key in ("task", "model", "status"):
            if not isinstance(item.get(key), str):
                raise _malformed(path_text, f"{where}.{key} must be a string")
        if not _is_number(item.get("cost_usd")):
            raise _malformed(path_text, f"{where}.cost_usd must be a number")
        if not _is_number(item.get("latency_s", 0.0)):
            raise _malformed(path_text, f"{where}.latency_s must be a number")
        budget_reason = item.get("budget_reason")
        if budget_reason is not None and not isinstance(budget_reason, str):
            raise _malformed(path_text, f"{where}.budget_reason must be a string")
        aborted_run = item.get("aborted_run", False)
        if not isinstance(aborted_run, bool):
            raise _malformed(path_text, f"{where}.aborted_run must be a boolean")
        for key in ("deleg_attempts", "deleg_attempts_unparsed", "deleg_invocations"):
            if not _is_int(item.get(key, 0)):
                raise _malformed(path_text, f"{where}.{key} must be an integer")
        repeat_index = item.get("repeat_index")
        if repeat_index is not None and not _is_int(repeat_index):
            raise _malformed(path_text, f"{where}.repeat_index must be an integer")
        latencies = item.get("call_latencies_s", [])
        if not isinstance(latencies, list) or not all(
            _is_number(x) for x in latencies
        ):
            raise _malformed(path_text, f"{where}.call_latencies_s must be a list of numbers")
        if not completed_status(item["status"], budget_reason, aborted_run):
            continue
        model = item["model"]
        if model == "auto":
            ab = settings.get("ab")
            if isinstance(ab, dict) and "model" in ab:
                if not isinstance(ab["model"], str):
                    raise _malformed(path_text, "settings.ab.model must be a string")
                model = ab["model"]
        arm = label if label is not None else (item.get("arm") or "-")
        rows.append(
            Row(
                arm=arm,
                model=model,
                task=item["task"],
                solved=item["status"] == "solved",
                cost_usd=float(item["cost_usd"]),
                wall_s=float(item.get("latency_s", 0.0)),
                deleg_attempts=item.get("deleg_attempts", 0),
                deleg_attempts_unparsed=item.get("deleg_attempts_unparsed", 0),
                deleg_started=item.get("deleg_invocations", 0),
                source=path_text,
                repeat_index=repeat_index,
                status=item["status"],
                call_latencies_s=tuple(float(x) for x in latencies),
            )
        )
    if tasks is not None:
        rows = [row for row in rows if row.task in tasks]
    return rows


def _tally(members: list[Row]) -> tuple[int, int, float]:
    k = sum(1 for r in members if r.solved)
    return k, len(members), sum(r.cost_usd for r in members)


def _spd(k: int, cost: float) -> float | None:
    return None if cost == 0 else k / cost


def cells(rows: Iterable[Row]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[Row]] = {}
    for row in rows:
        groups.setdefault((row.arm, row.model, row.task), []).append(row)
    out: list[dict[str, Any]] = []
    for (arm, model, task), members in sorted(groups.items()):
        k, n, cost = _tally(members)
        out.append(
            {
                "arm": arm,
                "model": model,
                "task": task,
                "k": k,
                "n": n,
                "cost_usd": cost,
                "wilson": wilson_interval(k, n),
            }
        )
    return out


def pooled(rows: Iterable[Row], tasks: set[str] | None = None) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        if tasks is not None and row.task not in tasks:
            continue
        groups.setdefault((row.arm, row.model), []).append(row)
    out: list[dict[str, Any]] = []
    for (arm, model), members in sorted(groups.items()):
        k, n, cost = _tally(members)
        out.append(
            {
                "arm": arm,
                "model": model,
                "tasks": len({r.task for r in members}),
                "k": k,
                "n": n,
                "ratio": k / n,
                "wilson": wilson_interval(k, n),
                "cost_usd": cost,
                "spd": _spd(k, cost),
            }
        )
    return out


def completeness(rows: Iterable[Row]) -> tuple[list[Row], list[dict[str, Any]]]:
    rows = list(rows)
    counts: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        per = counts.setdefault((row.arm, row.model), {})
        per[row.task] = per.get(row.task, 0) + 1
    incomplete: list[dict[str, Any]] = []
    complete_keys: set[tuple[str, str]] = set()
    for (arm, model), per in sorted(counts.items()):
        present = set(per)
        if arm in REGISTERED_TASKS and all(t.startswith("e2e_h") for t in present):
            required = set(REGISTERED_TASKS[arm])
        else:
            required = present
        missing = sorted(required - present)
        short = sorted((t, n) for t, n in per.items() if n < MIN_N)
        if missing or short:
            incomplete.append(
                {"arm": arm, "model": model, "missing": missing, "short": short}
            )
        else:
            complete_keys.add((arm, model))
    kept = [row for row in rows if (row.arm, row.model) in complete_keys]
    return kept, incomplete


def baseline_pool(baseline: CompareBaseline, tasks: set[str]) -> dict[str, Any] | None:
    common = sorted(tasks & set(baseline.tasks))
    if not common:
        return None
    entries = [baseline.tasks[t] for t in common]
    k = sum(round(e.solve_rate * e.n) for e in entries)
    n = sum(e.n for e in entries)
    cost = sum(e.cost_usd * e.n for e in entries)
    return {
        "k": k,
        "n": n,
        "p": k / n,
        "wilson": wilson_interval(k, n),
        "cost_usd": cost,
        "spd": _spd(k, cost),
    }


def classify(lo: float, ratio: float, hi: float, a: float, b: float) -> str:
    if any(lo < t < hi for t in (a, b)):
        return "indeterminate"
    if ratio >= a:
        return "a"
    if ratio >= b:
        return "b"
    return "c"


def classes(
    rows: Iterable[Row],
    baseline: CompareBaseline,
    thresholds: tuple[float, float, float],
) -> list[dict[str, Any]]:
    a, b, m = thresholds
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        if row.arm in EXCLUDED_CLASS_ARMS:
            continue
        groups.setdefault((row.arm, row.model), []).append(row)
    candidates: list[dict[str, Any]] = []
    for arm, model in sorted(groups):
        members = groups[(arm, model)]
        role = "arm a" if arm == "a" else "candidate"
        common = {r.task for r in members} & set(baseline.tasks)
        base = baseline_pool(baseline, common)
        if base is None or base["p"] == 0:
            reason = (
                "no common baseline tasks" if base is None else "S_cc = 0 on the common tasks"
            )
            candidates.append(
                {
                    "role": role,
                    "arm": arm,
                    "model": model,
                    "cls": "blocked",
                    "reason": reason,
                    "k": None,
                    "n": None,
                    "ratio": None,
                    "ratio_vs_baseline": None,
                    "lo": None,
                    "hi": None,
                    "spd": None,
                    "base_spd": None,
                    "cost_advantage": None,
                    "s_cc": None,
                    "s_cc_wilson": None,
                }
            )
            continue
        cand = pooled(members, common)[0]
        ratio = cand["ratio"] / base["p"]
        lo, hi = cand["wilson"]
        lo_r, hi_r = lo / base["p"], hi / base["p"]
        if cand["spd"] is not None and base["spd"] is not None:
            advantage = "yes" if cand["spd"] >= m * base["spd"] else "no"
        else:
            advantage = "n/a"
        candidates.append(
            {
                "role": role,
                "arm": arm,
                "model": model,
                "k": cand["k"],
                "n": cand["n"],
                "ratio": cand["ratio"],
                "ratio_vs_baseline": ratio,
                "lo": lo_r,
                "hi": hi_r,
                "cls": classify(lo_r, ratio, hi_r, a, b),
                "reason": None,
                "spd": cand["spd"],
                "base_spd": base["spd"],
                "cost_advantage": advantage,
                "s_cc": base["p"],
                "s_cc_wilson": base["wilson"],
            }
        )
    out: list[dict[str, Any]] = [c for c in candidates if c["arm"] == "a"]
    viable = [c for c in candidates if c["cls"] != "blocked"]
    if viable:
        best = max(
            viable,
            key=lambda c: (c["ratio"], c["spd"] if c["spd"] is not None else -1),
        )
        out.append({**best, "role": "best"})
    return out


def _arm_a_by(rows: Iterable[Row]) -> dict[str, dict[str, tuple[int, int, float]]]:
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        if row.arm == "a":
            groups.setdefault((row.task, row.model), []).append(row)
    by: dict[str, dict[str, tuple[int, int, float]]] = {}
    for (task, model), members in groups.items():
        k, n, cost = _tally(members)
        by.setdefault(task, {})[model] = (k, n, cost / n)
    return by


def oracle_tasks(
    by: dict[str, dict[str, tuple[int, int, float]]], tasks: set[str]
) -> dict[str, Any]:
    per: list[tuple[str, float, float]] = []
    for task in sorted(t for t in tasks if t in by):
        models = by[task]
        top_k, top_n = max(
            ((k, n) for k, n, _ in models.values()), key=lambda kn: kn[0] / kn[1]
        )
        attaining = [
            model
            for model in sorted(models)
            if models[model][0] * top_n == top_k * models[model][1]
        ]
        cost = min(models[model][2] for model in attaining)
        per.append((task, top_k / top_n, cost))
    total_cost = sum(cost for _, _, cost in per)
    ratio_sum = sum(mx for _, mx, _ in per)
    return {
        "tasks": len(per),
        "oracle": ratio_sum / len(per) if per else 0.0,
        "oracle_per_task": per,
        "oracle_cost_usd": total_cost,
        "oracle_spd": None if total_cost == 0 else ratio_sum / total_cost,
    }


def complementarity(rows: Iterable[Row]) -> dict[str, Any]:
    by = _arm_a_by(rows)
    per_task = [
        (task, sorted(model for model, (k, _, _) in by[task].items() if k >= 1))
        for task in sorted(by)
    ]
    union = sum(1 for task in by if any(3 * k >= n for k, n, _ in by[task].values()))
    counts: dict[str, int] = {}
    for _, models in per_task:
        for model in models:
            counts[model] = counts.get(model, 0) + 1
    best: tuple[str | None, int] = (None, 0)
    if counts:
        best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return {
        "per_task": per_task,
        "union": union,
        **oracle_tasks(by, set(by)),
        "best_single": best,
    }


def oracle_beside(rows: Iterable[Row]) -> list[dict[str, Any]]:
    rows = list(rows)
    by = _arm_a_by(rows)
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        if row.arm in ("b", "c_s", "c_cc"):
            groups.setdefault((row.arm, row.model), []).append(row)
    out: list[dict[str, Any]] = []
    for (arm, model), members in sorted(groups.items()):
        tasks = {r.task for r in members}
        mine = pooled(members)[0]
        oracle = oracle_tasks(by, tasks)
        out.append(
            {
                "arm": arm,
                "model": model,
                "tasks": len(tasks),
                "ratio": mine["ratio"],
                "spd": mine["spd"],
                "oracle_ratio": oracle["oracle"],
                "oracle_spd": oracle["oracle_spd"],
            }
        )
    return out


def p1(rows: Iterable[Row]) -> dict[str, Any]:
    rows = list(rows)
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        groups.setdefault((row.arm, row.model), []).append(row)
    out: list[dict[str, Any]] = []
    for arm, model in sorted(groups):
        if arm not in MECHANISMS:
            continue
        members = groups[(arm, model)]
        tasks = {r.task for r in members}
        mech = pooled(members)[0]
        candidates = [
            c
            for c in pooled([r for r in rows if r.arm == "a"], tasks)
            if c["tasks"] == len(tasks)
        ]
        if candidates:
            best_a = max(
                candidates,
                key=lambda c: (c["ratio"], c["spd"] if c["spd"] is not None else -1),
            )
            on = (
                mech["spd"] is not None
                and best_a["spd"] is not None
                and mech["spd"] > best_a["spd"]
                and mech["ratio"] >= best_a["ratio"]
            )
            decision = "ON" if on else "OFF"
        else:
            best_a = None
            decision = "no arm a on these tasks"
        out.append(
            {
                "mechanism": arm,
                "model": model,
                "tasks": len(tasks),
                "ratio": mech["ratio"],
                "spd": mech["spd"],
                "best_a_model": best_a["model"] if best_a else None,
                "best_a_ratio": best_a["ratio"] if best_a else None,
                "best_a_spd": best_a["spd"] if best_a else None,
                "decision": decision,
            }
        )
    verdicts: dict[str, str] = {mech: "not measured" for mech in MECHANISMS}
    for mech in MECHANISMS:
        decisions = {r["decision"] for r in out if r["mechanism"] == mech}
        if not decisions:
            continue
        if decisions == {"ON"}:
            verdicts[mech] = "ON proposed"
        elif decisions == {"OFF"}:
            verdicts[mech] = "OFF"
        else:
            verdicts[mech] = "mixed (user decision)"
    return {"rows": out, "verdicts": verdicts}


def delegation(rows: Iterable[Row]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        if row.arm in ("d1", "d2") or row.arm.startswith("deleg-"):
            groups.setdefault((row.arm, row.model), []).append(row)
    out: list[dict[str, Any]] = []
    for (arm, model), members in sorted(groups.items()):
        out.append(
            {
                "arm": arm,
                "model": model,
                "runs": len(members),
                "attempts": sum(r.deleg_attempts for r in members),
                "attempts_unparsed": sum(r.deleg_attempts_unparsed for r in members),
                "started": sum(r.deleg_started for r in members),
                "solved": sum(1 for r in members if r.solved),
                "cost_usd": sum(r.cost_usd for r in members),
                "wall_s": sum(r.wall_s for r in members),
            }
        )
    return out


_RERUN_FIELDS = {
    "id": str,
    "of": str,
    "task": str,
    "repeat_index": int,
    "orig_report": str,
    "rerun_report": str,
    "status": str,
}
_BILLED_FIELDS = {"id": str, "report": str, "report_cost": float, "billed": float}


def _entry_ok(item: object, fields: dict[str, type]) -> bool:
    if not isinstance(item, dict):
        return False
    for key, kind in fields.items():
        value = item.get(key)
        if kind is str and not isinstance(value, str):
            return False
        if kind is int and not _is_int(value):
            return False
        if kind is float and not _is_number(value):
            return False
    return True


def _resolved(path: str) -> Path:
    return Path(path).resolve()


def load_extras(path: str) -> dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise PanelError(f"cannot read extras {path}") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise PanelError(f"malformed extras {path}: invalid JSON ({e.msg})") from None
    if not isinstance(data, dict) or set(data) != {"reruns", "billed"}:
        raise PanelError(f"malformed extras {path}: top level needs reruns and billed")
    if not isinstance(data["reruns"], list) or not isinstance(data["billed"], list):
        raise PanelError(f"malformed extras {path}: reruns and billed must be lists")
    for index, item in enumerate(data["reruns"]):
        if not _entry_ok(item, _RERUN_FIELDS):
            raise PanelError(f"malformed extras {path}: reruns[{index}]")
    for index, item in enumerate(data["billed"]):
        if not _entry_ok(item, _BILLED_FIELDS):
            raise PanelError(f"malformed extras {path}: billed[{index}]")
    return data


def _billed_extra(entry: dict[str, Any]) -> float:
    return entry["billed"] - entry["report_cost"]


def _resolve_reruns(
    rows: list[Row], extras: dict[str, Any]
) -> tuple[dict[int, Row], list[dict[str, Any]]]:
    sources = [_resolved(row.source) for row in rows]
    superseded: dict[int, Row] = {}
    info: list[dict[str, Any]] = []
    for entry in extras["reruns"]:
        orig_path = _resolved(entry["orig_report"])
        found = [
            i
            for i, row in enumerate(rows)
            if sources[i] == orig_path
            and row.task == entry["task"]
            and row.repeat_index == entry["repeat_index"]
        ]
        base = {
            "id": entry["id"],
            "of": entry["of"],
            "task": entry["task"],
            "repeat_index": entry["repeat_index"],
        }
        if not found:
            info.append({**base, "arm": "-", "model": "-", "outcome": "unmatched"})
            continue
        orig = rows[found[0]]
        if entry["status"] != "executed":
            info.append(
                {
                    **base,
                    "arm": orig.arm,
                    "model": orig.model,
                    "outcome": f"not run ({entry['status']})",
                }
            )
            continue
        for i in found:
            if rows[i].status != "error":
                raise PanelError(
                    f"rerun {entry['id']}: original {entry['task']} "
                    f"r{entry['repeat_index']} in {entry['orig_report']} "
                    "is not an error run"
                )
        reruns = load_rows(f"{orig.arm}={entry['rerun_report']}")
        if len(reruns) != 1 or reruns[0].task != entry["task"]:
            raise PanelError(
                f"rerun {entry['id']}: {entry['rerun_report']} must hold "
                f"exactly one {entry['task']} result"
            )
        for i in found:
            superseded[i] = reruns[0]
        info.append(
            {
                **base,
                "arm": orig.arm,
                "model": orig.model,
                "outcome": reruns[0].status,
            }
        )
    return superseded, info


def apply_error_policy(
    rows: list[Row], extras: dict[str, Any], policy: str
) -> tuple[list[Row], list[dict[str, Any]]]:
    if policy not in ERROR_POLICIES:
        raise PanelError(f"unknown error policy {policy}")
    rows = list(rows)
    superseded, info = _resolve_reruns(rows, extras)
    out: list[Row] = []
    for i, row in enumerate(rows):
        if i not in superseded or policy == "unsolved":
            out.append(row)
        elif policy == "replace":
            out.append(superseded[i])
    return out, info


def apply_cost_basis(
    rows: list[Row], extras: dict[str, Any], basis: str
) -> list[Row]:
    if basis not in COST_BASES:
        raise PanelError(f"unknown cost basis {basis}")
    rows = list(rows)
    if basis == "report":
        return rows
    extra_by: dict[Path, float] = {}
    for entry in extras["billed"]:
        extra = _billed_extra(entry)
        if extra > 1e-12:
            key = _resolved(entry["report"])
            extra_by[key] = extra_by.get(key, 0.0) + extra
    sources = [_resolved(row.source) for row in rows]
    out = list(rows)
    for key, extra in extra_by.items():
        idx = [i for i, source in enumerate(sources) if source == key]
        if not idx:
            continue
        total = sum(rows[i].cost_usd for i in idx)
        for i in idx:
            share = (
                extra * rows[i].cost_usd / total if total else extra / len(idx)
            )
            out[i] = replace(rows[i], cost_usd=rows[i].cost_usd + share)
    return out


def sensitivity(raw_rows: Iterable[Row], extras: dict[str, Any]) -> list[dict[str, Any]]:
    raw = list(raw_rows)
    superseded, _ = _resolve_reruns(raw, extras)
    groups = sorted({(raw[i].arm, raw[i].model) for i in superseded})
    out: list[dict[str, Any]] = []
    for arm, model in groups:
        for policy in ERROR_POLICIES:
            kept, _ = apply_error_policy(raw, extras, policy)
            for basis in COST_BASES:
                variant = apply_cost_basis(kept, extras, basis)
                members = [r for r in variant if (r.arm, r.model) == (arm, model)]
                k, n, cost = _tally(members)
                _, incomplete = completeness(members)
                out.append(
                    {
                        "arm": arm,
                        "model": model,
                        "variant": f"{policy}/{basis}",
                        "k": k,
                        "n": n,
                        "ratio": k / n if n else None,
                        "cost_usd": cost,
                        "spd": _spd(k, cost),
                        "complete": bool(members) and not incomplete,
                    }
                )
    return out


def slow_calls(raw_rows: Iterable[Row]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[Row]] = {}
    for row in raw_rows:
        groups.setdefault((row.arm, row.model, row.task), []).append(row)
    out: list[dict[str, Any]] = []
    for (arm, model, task), members in sorted(groups.items()):
        calls = [c for r in members for c in r.call_latencies_s]
        out.append(
            {
                "arm": arm,
                "model": model,
                "task": task,
                "runs": len(members),
                "error_runs": sum(1 for r in members if r.status == "error"),
                "slow_calls": sum(1 for c in calls if c > SLOW_CALL_S),
                "max_call_s": max(calls) if calls else None,
            }
        )
    return out


def _sensitivity_appendix(
    raw: list[Row], extras: dict[str, Any], info: list[dict[str, Any]]
) -> list[str]:
    variants = sensitivity(raw, extras)
    variant_data = [
        [
            v["arm"],
            v["model"],
            v["variant"],
            f"{v['k']}/{v['n']}",
            "-" if v["ratio"] is None else f"{v['ratio']:.3f}",
            f"{v['cost_usd']:.4f}",
            _fmt_spd(v["spd"]),
            "yes" if v["complete"] else "no",
        ]
        for v in variants
    ]
    rerun_lines = [
        f"rerun {e['id']} (of {e['of']}): {e['arm']} {e['model']} {e['task']} "
        f"r{e['repeat_index']} -> {e['outcome']}"
        for e in info
    ]
    billed = [
        (entry, _billed_extra(entry))
        for entry in extras["billed"]
        if _billed_extra(entry) > 1e-12
    ]
    billed_data = [
        [
            entry["report"],
            f"{entry['report_cost']:.4f}",
            f"{entry['billed']:.4f}",
            f"{extra:.4f}",
        ]
        for entry, extra in billed
    ]
    total = sum(extra for _, extra in billed)
    body = [
        *(
            _table(
                ["arm", "model", "variant", "k/n", "ratio", "cost_usd", "spd", "complete"],
                variant_data,
            )
            if variant_data
            else ["(none)"]
        ),
        "",
        *(rerun_lines or ["(no rerun entries)"]),
        "",
        *(_table(["report", "report_cost", "billed", "extra"], billed_data) if billed else []),
        f"billed extra total: {total:.6f}",
    ]
    slow_data = [
        [
            s["arm"],
            s["model"],
            s["task"],
            str(s["runs"]),
            str(s["error_runs"]),
            str(s["slow_calls"]),
            "n/a" if s["max_call_s"] is None else f"{s['max_call_s']:.1f}",
        ]
        for s in slow_calls(raw)
    ]
    slow_body = (
        _table(
            ["arm", "model", "task", "runs", "error runs", "calls > 90 s", "max call s"],
            slow_data,
        )
        if slow_data
        else ["(none)"]
    )
    return [
        *_section("(g) sensitivity: error runs and billed cost", body),
        *_section("(g2) error runs and slow calls (> 90 s)", slow_body),
    ]


def _fmt_spd(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def _fmt_interval(bounds: tuple[float, float]) -> str:
    lo, hi = bounds
    return f"[{lo:.3f}, {hi:.3f}]"


def _table(headers: list[str], data: list[list[str]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in data)
    return lines


def _section(title: str, body: list[str]) -> list[str]:
    return [f"## {title}", "", *body, ""]


def _class_row(c: dict[str, Any]) -> list[str]:
    if c["cls"] == "blocked":
        return [
            c["role"],
            c["arm"],
            c["model"],
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            f"blocked ({c['reason']})",
            "-",
            "-",
            "-",
        ]
    return [
        c["role"],
        c["arm"],
        c["model"],
        f"{c['k']}/{c['n']}",
        f"{c['ratio']:.3f}",
        f"{c['s_cc']:.3f}",
        _fmt_interval(c["s_cc_wilson"]),
        f"{c['ratio_vs_baseline']:.3f}",
        _fmt_interval((c["lo"], c["hi"])),
        c["cls"],
        _fmt_spd(c["spd"]),
        _fmt_spd(c["base_spd"]),
        c["cost_advantage"],
    ]


def render(
    specs: list[str],
    rows: list[Row],
    baseline: CompareBaseline | None,
    thresholds: tuple[float, float, float],
    extra_header: list[str] | None = None,
    appendix: list[str] | None = None,
) -> str:
    a, b, m = thresholds
    complete, incomplete = completeness(rows)
    baseline_text = (
        "none (blocked: no Claude Code baseline, arm f)"
        if baseline is None
        else f"{baseline.file} ({baseline.meta.tool}, {baseline.meta.model})"
    )
    lines = [
        "# M19 panel",
        "",
        f"reports: {' '.join(specs)}",
        f"baseline: {baseline_text}",
        f"thresholds: A={a} B={b} cost={m}x",
        *(extra_header or []),
        "",
    ]

    cell_data = [
        [
            c["arm"],
            c["model"],
            c["task"],
            f"{c['k']}/{c['n']}",
            _fmt_interval(c["wilson"]),
            f"{c['cost_usd']:.4f}",
        ]
        for c in cells(rows)
    ]
    lines += _section(
        "(a) cells",
        _table(["arm", "model", "task", "k/n", "wilson", "cost_usd"], cell_data)
        if cell_data
        else ["(none)"],
    )

    incomplete_data = [
        [
            e["arm"],
            e["model"],
            ", ".join(e["missing"]) or "-",
            ", ".join(f"{t}:{n}" for t, n in e["short"]) or "-",
        ]
        for e in incomplete
    ]
    lines += _section(
        "(a2) incomplete cells (no claim, n < 3 or missing tasks)",
        _table(["arm", "model", "missing", "short"], incomplete_data)
        if incomplete_data
        else ["(none)"],
    )

    pooled_data = [
        [
            p["arm"],
            p["model"],
            str(p["tasks"]),
            f"{p['k']}/{p['n']}",
            f"{p['ratio']:.3f}",
            _fmt_interval(p["wilson"]),
            f"{p['cost_usd']:.4f}",
            _fmt_spd(p["spd"]),
        ]
        for p in pooled(complete)
    ]
    lines += _section(
        "(b) pooled",
        _table(
            ["arm", "model", "tasks", "k/n", "ratio", "wilson", "cost_usd", "spd"],
            pooled_data,
        )
        if pooled_data
        else ["(none)"],
    )

    if baseline is None:
        class_body = [
            "blocked: no Claude Code baseline (arm f); "
            "classes and cost advantage not computed"
        ]
    else:
        class_rows = classes(complete, baseline, thresholds)
        class_body = (
            _table(
                [
                    "role",
                    "arm",
                    "model",
                    "k/n",
                    "S",
                    "S_cc",
                    "S_cc wilson",
                    "r",
                    "interval",
                    "class",
                    "spd",
                    "base_spd",
                    "cost_advantage",
                ],
                [_class_row(c) for c in class_rows],
            )
            + [
                "",
                "best configuration: chosen post hoc among a, b, c_s, c_cc, d1, d2 "
                "by pooled solved ratio (tie: spd); optimistic at n = 3 (A20); "
                "every arm's own ratio is in (b).",
                "indeterminate: the interval crosses a class boundary; "
                "the higher class is not claimed.",
            ]
            if class_rows
            else ["(none)"]
        )
    lines += _section("(c) R38 classes", class_body)

    comp = complementarity(complete)
    if comp["tasks"]:
        best_member, best_count = comp["best_single"]
        mx_by_task = {task: (mx, cost) for task, mx, cost in comp["oracle_per_task"]}
        comp_table = _table(
            ["task", "solved by (>=1 of n)", "max k/n", "oracle cost/run"],
            [
                [
                    task,
                    ", ".join(models) or "-",
                    f"{mx_by_task[task][0]:.3f}",
                    f"{mx_by_task[task][1]:.4f}",
                ]
                for task, models in comp["per_task"]
            ],
        )
        beside = oracle_beside(complete)
        beside_body = (
            _table(
                [
                    "arm",
                    "model",
                    "tasks",
                    "S",
                    "spd",
                    "oracle S (same tasks)",
                    "oracle spd (same tasks)",
                ],
                [
                    [
                        x["arm"],
                        x["model"],
                        str(x["tasks"]),
                        f"{x['ratio']:.3f}",
                        _fmt_spd(x["spd"]),
                        f"{x['oracle_ratio']:.3f}",
                        _fmt_spd(x["oracle_spd"]),
                    ]
                    for x in beside
                ],
            )
            if beside
            else ["(no b/c_s/c_cc cell)"]
        )
        comp_body = [
            *comp_table,
            "",
            f"union: {comp['union']} of {comp['tasks']} tasks",
            f"oracle_ratio: {comp['oracle']:.3f}",
            f"oracle_cost_usd: {comp['oracle_cost_usd']:.4f}",
            f"oracle_spd: {_fmt_spd(comp['oracle_spd'])}",
            f"best_single: {best_member or 'none'} ({best_count} tasks)",
            "",
            *beside_body,
        ]
    else:
        comp_body = ["(none)"]
    lines += _section("(d) complementarity (arm a)", comp_body)

    deleg_data = [
        [
            d["arm"],
            d["model"],
            str(d["runs"]),
            str(d["attempts"]),
            str(d["attempts_unparsed"]),
            str(d["started"]),
            str(d["solved"]),
            f"{d['cost_usd']:.4f}",
            f"{d['wall_s']:.1f}",
        ]
        for d in delegation(rows)
    ]
    lines += _section(
        "(e) delegation",
        _table(
            [
                "arm",
                "model",
                "runs",
                "attempts",
                "attempts_unparsed",
                "started",
                "solved",
                "cost_usd",
                "wall_s",
            ],
            deleg_data,
        )
        if deleg_data
        else ["(none)"],
    )

    p1_result = p1(complete)
    p1_data = [
        [
            r["mechanism"],
            r["model"],
            str(r["tasks"]),
            f"{r['ratio']:.3f}",
            _fmt_spd(r["spd"]),
            r["best_a_model"] or "-",
            "-" if r["best_a_ratio"] is None else f"{r['best_a_ratio']:.3f}",
            "-" if r["best_a_model"] is None else _fmt_spd(r["best_a_spd"]),
            r["decision"],
        ]
        for r in p1_result["rows"]
    ]
    p1_body = _table(
        [
            "mechanism",
            "model",
            "tasks",
            "S",
            "spd",
            "best a",
            "best a S",
            "best a spd",
            "decision",
        ],
        p1_data,
    ) if p1_data else ["(none)"]
    p1_body += [
        f"P1 {mech}: {p1_result['verdicts'][mech]}" for mech in MECHANISMS
    ]
    lines += _section("(f) P1", p1_body)
    lines += appendix or []
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="M19 panel analysis over bench reports (offline, no model call)."
    )
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--thresholds", default=DEFAULT_THRESHOLDS)
    parser.add_argument("--out")
    parser.add_argument("--extras")
    parser.add_argument("--error-policy", choices=ERROR_POLICIES, default="unsolved")
    parser.add_argument("--cost-basis", choices=COST_BASES, default="report")
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args(argv)
    try:
        thresholds = parse_thresholds(args.thresholds)
        raw = [row for spec in args.reports for row in load_rows(spec)]
        baseline = (
            None
            if args.baseline == NO_BASELINE
            else load_compare_baseline(Path(args.baseline))
        )
        if args.extras is None and (
            args.error_policy != "unsolved"
            or args.cost_basis != "report"
            or args.sensitivity
        ):
            raise PanelError(
                "--error-policy, --cost-basis and --sensitivity need --extras"
            )
        rows = raw
        extra_header = None
        appendix = None
        if args.extras is not None:
            extras = load_extras(args.extras)
            rows, info = apply_error_policy(raw, extras, args.error_policy)
            rows = apply_cost_basis(rows, extras, args.cost_basis)
            extra_header = [
                f"error policy: {args.error_policy}",
                f"cost basis: {args.cost_basis}",
                f"extras: {args.extras}",
            ]
            if args.sensitivity:
                appendix = _sensitivity_appendix(raw, extras, info)
        text = render(
            args.reports,
            rows,
            baseline,
            thresholds,
            extra_header=extra_header,
            appendix=appendix,
        )
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
    except (PanelError, ConfigError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
