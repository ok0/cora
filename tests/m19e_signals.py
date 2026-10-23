from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from pathlib import Path

from cora.core.prerouter import HistoryRow, knn_score, signal_score

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/m19e"
SEED = 20261022
EXACT_LIMIT = 100_000
MC_N = 100_000
WILSON_Z = 1.96
PASS_AUROC = 0.75
PASS_P = 0.025
RATIO_SLACK = 0.05
TASK_SIGNALS = ("S1a", "S1b", "S2", "S3")
ALL_SIGNALS = ("S1a", "S1b", "S2", "S3", "S4")
PREREG_PREFIX = "## M19e 1단계 사전 등록 ("
HARD_SET = "hard"
POS_MIN = Fraction(2, 3)
INF = math.inf
PASS_RULE = (
    "PASS iff at least one signal meets all of: (i) AUROC ≥ 0.75; (ii) permutation p ≤ 0.025 "
    "(0.10 Bonferroni over 4 signals); (iii) S1–S3: AUROC > the set-identity baseline's; "
    "(iv) its simulated policy has solved-per-dollar > always-strong's AND solved ratio ≥ "
    "always-strong's − 0.05."
)
FAIL_LINE = (
    "FAIL — M19e2 and M19e3 dropped; M19e closed with no paid spend; core/prerouter.py "
    "stays unwired; M20 may start."
)

Cell = tuple[int, int, float]


def auroc(scores: Sequence[float], positive: Sequence[bool]) -> float | None:
    pos = [s for s, p in zip(scores, positive, strict=True) if p]
    neg = [s for s, p in zip(scores, positive, strict=True) if not p]
    if not pos or not neg:
        return None
    total = 0.0
    for a in pos:
        for b in neg:
            if a > b:
                total += 1.0
            elif a == b:
                total += 0.5
    return total / (len(pos) * len(neg))


def perm_p(
    scores: Sequence[float],
    positive: Sequence[bool],
    *,
    exact_limit: int = EXACT_LIMIT,
    mc: int = MC_N,
    seed: int = SEED,
) -> tuple[float, str]:
    obs = auroc(scores, positive)
    if obs is None:
        raise ValueError("permutation test needs both classes")
    n = len(scores)
    n_pos = sum(1 for p in positive if p)
    if math.comb(n, n_pos) <= exact_limit:
        hits = 0
        total = 0
        for idx in itertools.combinations(range(n), n_pos):
            mask = [False] * n
            for i in idx:
                mask[i] = True
            total += 1
            a = auroc(scores, mask)
            if a is not None and a >= obs - 1e-12:
                hits += 1
        return hits / total, "exact"
    rng = random.Random(seed)
    labels = [bool(p) for p in positive]
    hits = 0
    for _ in range(mc):
        rng.shuffle(labels)
        a = auroc(scores, labels)
        if a is not None and a >= obs - 1e-12:
            hits += 1
    return (1 + hits) / (1 + mc), "monte_carlo"


def wilson(k: float, n: int, z: float = WILSON_Z) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    z2 = z * z
    d = 1 + z2 / n
    c = (p + z2 / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def labels(runs: Sequence[Mapping]) -> dict[str, bool]:
    counts: dict[tuple[str, str], tuple[int, int]] = {}
    for r in runs:
        if r["tier"] != "cheap":
            continue
        key = (r["task"], r["model"])
        k, n = counts.get(key, (0, 0))
        counts[key] = (k + int(bool(r["solved"])), n + 1)
    out: dict[str, bool] = {}
    for (task, _model), (k, n) in counts.items():
        ok = Fraction(k, n) >= POS_MIN
        out[task] = out.get(task, False) or ok
    return out


def set_baseline(task_set: Mapping[str, str], cheap_ok: Mapping[str, bool]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t, s in task_set.items():
        others = [u for u, su in task_set.items() if su == s and u != t and u in cheap_ok]
        if not others:
            out[t] = 0.5
        else:
            out[t] = sum(1 for u in others if not cheap_ok[u]) / len(others)
    return out


def s3_scores(
    feats: Mapping[str, Mapping[str, float]], cheap_ok: Mapping[str, bool]
) -> dict[str, float | None]:
    return {
        t: knn_score(
            feats[t],
            [HistoryRow(u, feats[u], cheap_ok[u]) for u in feats],
            k=3,
            exclude_task=t,
        )
        for t in feats
    }


def cells(runs: Sequence[Mapping]) -> tuple[dict[tuple[str, str], Cell], dict[str, Cell]]:
    cheap: dict[tuple[str, str], Cell] = {}
    strong: dict[str, Cell] = {}
    for r in runs:
        if r["tier"] == "cheap":
            acc, key = cheap, (r["task"], r["model"])
        elif r["tier"] == "strong":
            acc, key = strong, r["task"]
        else:
            continue
        k, n, c = acc.get(key, (0, 0, 0.0))
        acc[key] = (k + int(bool(r["solved"])), n + 1, c + float(r["cost_usd"]))
    return cheap, strong


def best_cheap_member(cheap: Mapping[tuple[str, str], Cell], tasks: Sequence[str]) -> str:
    members = sorted({m for (t, m) in cheap if t in tasks})
    if not members:
        raise ValueError("no cheap cells for set")

    def key(m: str) -> tuple[int, float, str]:
        cs = [cheap[(t, m)] for t in tasks if (t, m) in cheap]
        return (-sum(c[0] for c in cs), sum(c[2] for c in cs), m)

    return min(members, key=key)


def policy(
    decisions: Mapping[str, str], cheap: Mapping[str, Cell], strong: Mapping[str, Cell]
) -> dict:
    k = 0
    n = 0
    cost = 0.0
    for t, d in decisions.items():
        ck, cn, cc = strong[t] if d == "strong" else cheap[t]
        k += ck
        n += cn
        cost += cc
    return {
        "k": k,
        "n": n,
        "cost": cost,
        "ratio": k / n if n else None,
        "wilson": wilson(round(k), n),
        "spd": k / cost if cost > 0 else None,
    }


def loo_threshold(
    scores: Mapping[str, float],
    train_tasks: Sequence[str],
    cheap: Mapping[str, Cell],
    strong: Mapping[str, Cell],
) -> float:
    train = {t: scores[t] for t in train_tasks if scores.get(t) is not None}
    if not train:
        return INF
    always = policy({t: "strong" for t in train}, cheap, strong)
    floor = always["ratio"] - RATIO_SLACK
    best: tuple[tuple[float, float], float] | None = None
    for th in sorted(set(train.values())) + [INF]:
        dec = {t: ("strong" if s >= th else "cheap") for t, s in train.items()}
        p = policy(dec, cheap, strong)
        if p["ratio"] is None or p["ratio"] < floor:
            continue
        spd = p["spd"] if p["spd"] is not None else -INF
        key = (spd, th)
        if best is None or key > best[0]:
            best = (key, th)
    return INF if best is None else best[1]


def routed(
    scores: Mapping[str, float], cheap: Mapping[str, Cell], strong: Mapping[str, Cell]
) -> dict[str, tuple[float, str]]:
    tasks = [t for t, s in scores.items() if s is not None]
    out: dict[str, tuple[float, str]] = {}
    for t in tasks:
        th = loo_threshold(scores, [u for u in tasks if u != t], cheap, strong)
        out[t] = (th, "strong" if scores[t] >= th else "cheap")
    return out


def _strong_unit(strong: Mapping[str, Cell], task: str) -> tuple[float, float]:
    k, n, c = strong[task]
    return k / n, c / n


def s4_units(runs: Sequence[Mapping]) -> list[dict]:
    out = []
    for r in runs:
        if r.get("tier") != "cheap" or r.get("s4_status") != "ok":
            continue
        s4 = r["s4"]
        out.append(
            {
                "task": r["task"],
                "solved": bool(r["solved"]),
                "cost_usd": float(r["cost_usd"]),
                "markers": int(s4["markers"]),
                "prefix_cost_usd": float(s4["prefix_cost_usd"]),
            }
        )
    return out


def _s4_apply(
    units: Sequence[Mapping], theta_of: Callable[[str], float], strong: Mapping[str, Cell]
) -> dict:
    k = 0.0
    cost = 0.0
    for u in units:
        if u["markers"] >= theta_of(u["task"]):
            rate, avg = _strong_unit(strong, u["task"])
            k += rate
            cost += u["prefix_cost_usd"] + avg
        else:
            k += float(u["solved"])
            cost += u["cost_usd"]
    n = len(units)
    return {
        "k": k,
        "n": n,
        "cost": cost,
        "ratio": k / n if n else None,
        "wilson": wilson(round(k), n),
        "spd": k / cost if cost > 0 else None,
    }


def s4_policy(units: Sequence[Mapping], theta: float, strong: Mapping[str, Cell]) -> dict:
    return _s4_apply(units, lambda _t: theta, strong) | {"theta": theta}


def s4_always_strong(units: Sequence[Mapping], strong: Mapping[str, Cell]) -> dict:
    k = 0.0
    cost = 0.0
    for u in units:
        rate, avg = _strong_unit(strong, u["task"])
        k += rate
        cost += avg
    n = len(units)
    return {
        "k": k,
        "n": n,
        "cost": cost,
        "ratio": k / n if n else None,
        "wilson": wilson(round(k), n),
        "spd": k / cost if cost > 0 else None,
    }


def _s4_theta(units: Sequence[Mapping], strong: Mapping[str, Cell]) -> float:
    if not units:
        return INF
    always = s4_always_strong(units, strong)
    floor = always["ratio"] - RATIO_SLACK
    best: tuple[tuple[float, float], float] | None = None
    for th in sorted({u["markers"] for u in units}) + [INF]:
        p = s4_policy(units, th, strong)
        if p["ratio"] < floor:
            continue
        spd = p["spd"] if p["spd"] is not None else -INF
        key = (spd, th)
        if best is None or key > best[0]:
            best = (key, th)
    return INF if best is None else best[1]


def s4_routed(units: Sequence[Mapping], strong: Mapping[str, Cell]) -> dict:
    tasks = sorted({u["task"] for u in units})
    thetas = {}
    for t in tasks:
        thetas[t] = _s4_theta([u for u in units if u["task"] != t], strong)
    out = _s4_apply(units, lambda t: thetas[t], strong)
    out["thetas"] = thetas
    return out


def _task_auc(
    scores: Mapping[str, float | None], cheap_ok: Mapping[str, bool], tasks: Sequence[str]
) -> float | None:
    ts = [t for t in tasks if scores.get(t) is not None]
    return auroc([scores[t] for t in ts], [not cheap_ok[t] for t in ts])


def _task_metric(name: str, scores: Mapping[str, float | None], ctx: Mapping) -> dict:
    tasks = ctx["tasks"]
    cheap_ok = ctx["cheap_ok"]
    cheap = ctx["cheap_best"]
    strong = ctx["strong"]
    scored = [t for t in tasks if scores.get(t) is not None]
    pos = [not cheap_ok[t] for t in scored]
    vals = [scores[t] for t in scored]
    a = auroc(vals, pos)
    p, method = (None, "n/a") if a is None else perm_p(vals, pos)
    hard = [t for t in scored if ctx["task_set"][t] == HARD_SET]
    th = routed({t: scores[t] for t in scored}, cheap, strong)
    dec = {t: (th[t][1] if t in th else "strong") for t in tasks}
    pol = policy(dec, cheap, strong)
    sp = policy({t: "strong" for t in tasks}, cheap, strong)
    base = auroc([ctx["baseline"][t] for t in scored], pos)
    return {
        "name": name,
        "n": len(scored),
        "n_pos": sum(pos),
        "auroc": a,
        "p": p,
        "method": method,
        "hard_auroc": _task_auc(scores, cheap_ok, hard),
        "baseline": base,
        "spd": pol["spd"],
        "ratio": pol["ratio"],
        "wilson": pol["wilson"],
        "k": pol["k"],
        "cells": pol["n"],
        "cost": pol["cost"],
        "strong_spd": sp["spd"],
        "strong_ratio": sp["ratio"],
        "thetas": {t: th[t][0] for t in th},
        "tiers": {t: th[t][1] for t in th},
        "blocked": [t for t in tasks if t not in th],
        "decisions": dec,
    }


def _s4_metric(units: Sequence[Mapping], ctx: Mapping) -> dict:
    strong = ctx["strong"]
    scores = [float(u["markers"]) for u in units]
    pos = [not u["solved"] for u in units]
    a = auroc(scores, pos)
    p, method = (None, "n/a") if a is None else perm_p(scores, pos)
    hard = [u for u in units if ctx["task_set"][u["task"]] == HARD_SET]
    hard_a = auroc([float(u["markers"]) for u in hard], [not u["solved"] for u in hard])
    routed_pol = s4_routed(units, strong)
    always = s4_always_strong(units, strong)
    return {
        "name": "S4",
        "n": len(units),
        "n_pos": sum(pos),
        "auroc": a,
        "p": p,
        "method": method,
        "hard_auroc": hard_a,
        "baseline": None,
        "spd": routed_pol["spd"],
        "ratio": routed_pol["ratio"],
        "wilson": routed_pol["wilson"],
        "k": routed_pol["k"],
        "cells": routed_pol["n"],
        "cost": routed_pol["cost"],
        "strong_spd": always["spd"],
        "strong_ratio": always["ratio"],
        "thetas": routed_pol["thetas"],
        "tiers": {},
        "blocked": [],
        "decisions": {},
    }


def _gates(name: str, m: Mapping) -> dict:
    auc = m.get("auroc")
    i = auc is not None and auc >= PASS_AUROC
    ii = m.get("p") is not None and m["p"] <= PASS_P
    if name == "S4":
        iii = None
    else:
        iii = auc is not None and m.get("baseline") is not None and auc > m["baseline"]
    sp = m.get("spd")
    ss = m.get("strong_spd")
    iv = (
        sp is not None
        and ss is not None
        and sp > ss
        and m.get("ratio") is not None
        and m.get("strong_ratio") is not None
        and m["ratio"] >= m["strong_ratio"] - RATIO_SLACK
    )
    need = (i, ii, iv) if name == "S4" else (i, ii, iii, iv)
    return {"i": i, "ii": ii, "iii": iii, "iv": iv, "pass": all(need)}


def decide_pass(metrics: Mapping[str, Mapping]) -> tuple[str, list[str]]:
    gates = {n: _gates(n, metrics[n]) for n in ALL_SIGNALS}
    passing = [n for n in ALL_SIGNALS if gates[n]["pass"]]
    if not passing:
        return "FAIL", [FAIL_LINE]
    lines = ["PASS — M19e2 proceeds."]
    if passing == ["S1a"]:
        lines.append("S1a-only PASS: needs a paid strong-judge call in M19e3.")
    if passing == ["S4"]:
        lines.append(
            "S4-only PASS: escalation-trigger candidate, not a pre-router "
            "(blueprint delta in M19e3)."
        )
    return "PASS", lines


def _oracle(
    tasks: Sequence[str], cheap: Mapping[str, Cell], strong: Mapping[str, Cell]
) -> dict[str, str]:
    out = {}
    for t in tasks:
        c, s = cheap[t], strong[t]
        cr, sr = Fraction(c[0], c[1]), Fraction(s[0], s[1])
        if cr > sr:
            out[t] = "cheap"
        elif sr > cr:
            out[t] = "strong"
        else:
            out[t] = "cheap" if c[2] / c[1] <= s[2] / s[1] else "strong"
    return out


def evaluate(runs: Sequence[Mapping], inputs: Sequence[Mapping], judges: Sequence[Mapping]) -> dict:
    cheap_cells, strong_cells = cells(runs)
    tasks = [row["task"] for row in inputs]
    task_set = {row["task"]: row["set"] for row in inputs}
    cheap_ok = labels(runs)
    for t in tasks:
        if t not in cheap_ok:
            raise ValueError(f"no cheap runs for {t}")
    by_set: dict[str, list[str]] = {}
    for t in tasks:
        by_set.setdefault(task_set[t], []).append(t)
    member: dict[str, str] = {}
    cheap_best: dict[str, Cell] = {}
    for s, ts in by_set.items():
        m = best_cheap_member(cheap_cells, ts)
        member[s] = m
        for t in ts:
            cheap_best[t] = cheap_cells[(t, m)]
    strong = {t: strong_cells[t] for t in tasks}
    names = {}
    for r in runs:
        if r["tier"] in ("cheap", "strong"):
            names.setdefault(r["task"], {}).setdefault(r["tier"], r["cell"])

    judge_scores: dict[str, dict[str, float | None]] = {"S1a": {}, "S1b": {}}
    blocked: list[str] = []
    for j in judges:
        if j["status"] == "ok":
            judge_scores[j["judge"]][j["task"]] = float(j["score"])
        else:
            judge_scores[j["judge"]][j["task"]] = None
            blocked.append(f"{j['judge']}:{j['task']}")
    feats = {row["task"]: dict(row["features"]) for row in inputs}
    s1a = {t: judge_scores["S1a"].get(t) for t in tasks}
    s1b = {t: judge_scores["S1b"].get(t) for t in tasks}
    s2 = {t: signal_score(feats[t], signal="scope") for t in tasks}
    with_judge = {t: {**feats[t], "judge": s1a[t]} for t in tasks if s1a[t] is not None}
    s3_raw = s3_scores(with_judge, cheap_ok) if with_judge else {}
    s3 = {t: s3_raw.get(t) for t in tasks}
    baseline = set_baseline(task_set, cheap_ok)
    ctx = {
        "tasks": tasks,
        "task_set": task_set,
        "cheap_ok": cheap_ok,
        "cheap_best": cheap_best,
        "strong": strong,
        "baseline": baseline,
    }
    metrics = {
        "S1a": _task_metric("S1a", s1a, ctx),
        "S1b": _task_metric("S1b", s1b, ctx),
        "S2": _task_metric("S2", s2, ctx),
        "S3": _task_metric("S3", s3, ctx),
    }
    units = s4_units(runs)
    metrics["S4"] = _s4_metric(units, ctx)

    policies: list[tuple[str, dict]] = [
        ("always-best-cheap", policy({t: "cheap" for t in tasks}, cheap_best, strong)),
        ("always-strong", policy({t: "strong" for t in tasks}, cheap_best, strong)),
    ]
    for name in ALL_SIGNALS:
        m = metrics[name]
        policies.append(
            (
                f"routed-{name}",
                {
                    "k": m["k"],
                    "n": m["cells"],
                    "cost": m["cost"],
                    "ratio": m["ratio"],
                    "wilson": m["wilson"],
                    "spd": m["spd"],
                },
            )
        )
    policies.append(("oracle", policy(_oracle(tasks, cheap_best, strong), cheap_best, strong)))

    decision = decide_pass(metrics)
    return {
        "tasks": tasks,
        "task_set": task_set,
        "member": member,
        "names": names,
        "cheap_ok": cheap_ok,
        "cheap_best": cheap_best,
        "strong": strong,
        "baseline": baseline,
        "scores": {"S1a": s1a, "S1b": s1b, "S2": s2, "S3": s3},
        "metrics": metrics,
        "policies": policies,
        "units": len(units),
        "s4_excluded": sum(
            1 for r in runs if r.get("tier") == "cheap" and r.get("s4_status") != "ok"
        ),
        "blocked": blocked,
        "decision": decision,
    }


def _f(x: float | None, nd: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def _w(w: tuple[float, float] | None) -> str:
    return "n/a" if w is None else f"[{w[0]:.3f}, {w[1]:.3f}]"


def render(res: Mapping) -> str:
    tasks = res["tasks"]
    cok = res["cheap_ok"]
    L = ["# M19e1 signals", "", "## Dataset and labels", ""]
    L.append("| task | set | cheap cell | strong cell | member | k/n | cheap_ok |")
    L.append("|---|---|---|---|---|---|---|")
    for t in tasks:
        s = res["task_set"][t]
        c = res["cheap_best"][t]
        st = res["strong"][t]
        nm = res["names"].get(t, {})
        L.append(
            f"| {t} | {s} | {nm.get('cheap', '?')} | {nm.get('strong', '?')} | "
            f"{res['member'][s]} | "
            f"{c[0]}/{c[1]} (strong {st[0]}/{st[1]}) | {cok[t]} |"
        )
    L += ["", "## Per-task decisions", ""]
    for t in tasks:
        parts = []
        for name in ("S1a", "S1b", "S2", "S3"):
            m = res["metrics"][name]
            sc = res["scores"][name][t]
            if sc is None:
                parts.append(f"{name}=blocked")
            else:
                parts.append(f"{name}={sc:.4g} (θ={m['thetas'][t]:.4g}, {m['tiers'][t]})")
        b = res["baseline"][t]
        L.append(f"- {t}: " + "; ".join(parts) + f"; baseline={b:.3g}")
    L.append("")
    for name in TASK_SIGNALS:
        tiers = set(res["metrics"][name]["tiers"].values())
        differ = "yes" if len(tiers) > 1 else "no"
        L.append(f"Decisions differ across tasks ({name}): {differ}")
    L += ["", "## Metrics", ""]
    L.append(
        "| signal | n | n_pos | AUROC | p | method | AUROC hard-only | > baseline "
        "| policy ratio | Wilson | spd | (i) | (ii) | (iii) | (iv) | pass |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    base_all = auroc([res["baseline"][t] for t in tasks], [not cok[t] for t in tasks])
    for name in ALL_SIGNALS:
        m = res["metrics"][name]
        g = _gates(name, m)
        approx = " (approx)" if name == "S4" else ""
        iii = "n/a" if g["iii"] is None else str(g["iii"])
        L.append(
            f"| {name} | {m['n']} | {m['n_pos']} | {_f(m['auroc'])} | {_f(m['p'])} "
            f"| {m['method']} | {_f(m['hard_auroc'])} | {iii} | {_f(m['ratio'])} "
            f"| {_w(m['wilson'])}{approx} | {_f(m['spd'], 2)} | "
            f"{g['i']} | {g['ii']} | {iii} | {g['iv']} | {g['pass']} |"
        )
    n_neg = sum(1 for t in tasks if not cok[t])
    L.append(
        f"| baseline | {len(tasks)} | {n_neg} | {_f(base_all)} "
        "| n/a | n/a | n/a | n/a | n/a | n/a | n/a | | | | | |"
    )
    L += ["", "## Policy table", ""]
    L.append("| policy | k | n | cost | ratio | Wilson | spd |")
    L.append("|---|---|---|---|---|---|---|")
    for name, pol in res["policies"]:
        approx = " (approx)" if name == "routed-S4" else ""
        L.append(
            f"| {name} | {_f(pol['k'], 2)} | {pol['n']} | {_f(pol.get('cost'), 4)} "
            f"| {_f(pol['ratio'])} | "
            f"{_w(pol['wilson'])}{approx} | {_f(pol['spd'], 2)} |"
        )
    s4 = res["metrics"]["S4"]
    L += [
        "",
        "## S4 (run level)",
        "",
        f"- units (cheap runs with s4 status ok): {res['units']}; "
        f"excluded cheap runs (not ok): {res['s4_excluded']}",
        f"- prefix AUROC: {_f(s4['auroc'])}; p: {_f(s4['p'])} ({s4['method']}); "
        f"hard-only AUROC: {_f(s4['hard_auroc'])}",
        "- routed θ per task: "
        + (", ".join(f"{t}={v:.4g}" for t, v in s4["thetas"].items()) or "none"),
        "",
        "## Blocked",
        "",
        "; ".join(res["blocked"]) if res["blocked"] else "none",
        "",
        "## Decision",
        "",
        f"Pass rule: {PASS_RULE}",
        "",
    ]
    L += res["decision"][1]
    L += ["", "cost: $0; openrouter_calls: 0", ""]
    return "\n".join(L)


def committed_bench_results() -> str:
    try:
        r = subprocess.run(
            ["git", "show", "HEAD:.docs/bench-results.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return r.stdout if r.returncode == 0 else ""


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="m19e_signals")
    ap.add_argument("--runs", type=Path, default=FIX / "runs.jsonl")
    ap.add_argument("--inputs", type=Path, default=FIX / "inputs.jsonl")
    ap.add_argument("--judges", type=Path, default=FIX / "judge-scores.jsonl")
    ap.add_argument("--out", type=Path, default=FIX / "signals.md")
    ap.add_argument("--skip-guard", action="store_true")
    args = ap.parse_args(argv)
    if not args.skip_guard and PREREG_PREFIX not in committed_bench_results():
        print("error: pre-registration not committed", file=sys.stderr)
        return 2
    try:
        res = evaluate(_read_jsonl(args.runs), _read_jsonl(args.inputs), _read_jsonl(args.judges))
        text = render(res)
        args.out.write_text(text, encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
