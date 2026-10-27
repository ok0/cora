from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from cora.bench import e2e
from cora.bench.stats import wilson_interval
from cora.cli.common import load_resolved
from cora.core.config import find_model, load_config
from cora.core.errors import ConfigError
from cora.core.observability import read_events

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / ".cora" / "m21"
MODEL = "gemini-3.5-flash-lite"
PRICE_MODEL = "google/gemini-2.5-flash-lite"
GEMINI_ID_LINE = f'id = "{MODEL}"'
SINGLE_ARMS = ("OFF", "M", "D", "C", "L", "S")
SWITCH_ARMS = ("L", "S", "M", "D", "C")
SWITCH_LINES = {
    "L": ("ledger = false", "ledger = true"),
    "S": ('summarize = "off"', 'summarize = "llm"'),
    "M": ("repo_map = false", "repo_map = true"),
    "D": ("dedupe_reads = false", "dedupe_reads = true"),
    "C": ("compress_observations = false", "compress_observations = true"),
}
TASK_ORDER = (
    "e2e_n03",
    "e2e_n06",
    "e2e_n14",
    "e2e_n12",
    "e2e_n13",
    "e2e_n01",
    "e2e_n02",
    "e2e_n04",
    "e2e_n05",
    "e2e_n07",
    "e2e_n08",
    "e2e_n09",
    "e2e_n10",
    "e2e_n11",
)
CAL_ITERATIONS = {
    "e2e_n01": 12,
    "e2e_n02": 13,
    "e2e_n03": 30,
    "e2e_n04": 16,
    "e2e_n05": 22,
    "e2e_n06": 21,
    "e2e_n07": 20,
    "e2e_n08": 7,
    "e2e_n09": 20,
    "e2e_n10": 30,
    "e2e_n11": 18,
    "e2e_n12": 20,
    "e2e_n13": 23,
    "e2e_n14": 25,
}
SEC_PER_CALL = 13.0
REPEATS = 3
RETRY_WAIT_S = 60
MARGIN = 0.10
MIN_COMMON = 6
MIN_EVICT_RUNS = 5
D_COUNTER = {"L": "evictions", "S": "evictions", "C": "compressed"}
BLOCKED_RE = re.compile(
    r"\b(429|5\d\d)\b|UNAVAILABLE|RESOURCE_EXHAUSTED|overloaded|rate limited"
    r"|timed? ?out|ConnectError|ReadError|RemoteProtocolError",
    re.I,
)
SWITCH_EVENTS = (
    "ledger_update",
    "ledger_evict_note",
    "summary_call",
    "read_dedupe",
    "observation_compress",
    "repo_map",
)
PREREG_HEADING = "## M21 사전 등록"
FLIP_TEXT = "flip ON (free-tier directional; user confirmation required)"
SKIP_DIRS = frozenset({".git", ".venv", "__pycache__", "node_modules"})
BUDGET_ARMS = ("OFF", "L", "S", "C")
BUDGET_LINE = "context_budget_tokens = 12000"


def _fail(msg: str) -> NoReturn:
    print(msg, file=sys.stderr)
    raise SystemExit(2)


def _split(text: str) -> list[str]:
    ids = [x.strip() for x in text.split(",") if x.strip()]
    if not ids:
        _fail("empty task list")
    return ids


def _select(ids: Sequence[str]) -> tuple[e2e.E2ETask, ...]:
    if not ids:
        _fail("empty task list")
    try:
        return e2e.select_e2e_tasks(list(ids))
    except ConfigError as e:
        _fail(str(e))


def arm_name(arm: str, budget: int | None) -> str:
    return arm if budget is None else f"{arm}-b{budget}"


def _gemini_block(lines: list[str]) -> tuple[int, int]:
    hits = [i for i, line in enumerate(lines) if line.strip() == GEMINI_ID_LINE]
    if len(hits) != 1:
        _fail(f"expected one '{GEMINI_ID_LINE}' line in cora.toml, found {len(hits)}")
    i = hits[0]
    start = i
    while not lines[start].startswith("[[models]]"):
        start -= 1
    end = i + 1
    while end < len(lines) and not lines[end].startswith("["):
        end += 1
    return start, end


def arm_text(arm: str, best: Sequence[str] = (), budget: int | None = None) -> str:
    best = tuple(best)
    if arm == "BEST":
        if len(best) < 2 or any(s not in SWITCH_ARMS for s in best):
            _fail("BEST needs at least two switches from L,S,M,D,C")
        switches: tuple[str, ...] = best
    elif arm in SINGLE_ARMS:
        if best:
            _fail("best switches are only valid for BEST")
        switches = () if arm == "OFF" else (arm,)
    else:
        _fail(f"unknown arm '{arm}'")
    if budget is not None:
        if arm not in BUDGET_ARMS or budget <= 0:
            _fail("budget stress is only valid for OFF, L, S, C with a positive budget")
    raw = (ROOT / "cora.toml").read_bytes()
    lines = raw.decode("utf-8").splitlines(keepends=True)
    start, end = _gemini_block(lines)
    block = lines[start:end]
    del lines[start:end]
    first = next((i for i, line in enumerate(lines) if line.startswith("[[models]]")), None)
    if first is None:
        _fail("cora.toml has no [[models]] entry")
    lines[first:first] = block
    for s in switches:
        old, new = SWITCH_LINES[s]
        hits = [i for i, line in enumerate(lines) if line.startswith(old)]
        if len(hits) != 1:
            _fail(f"switch line '{old}' found {len(hits)} times")
        lines[hits[0]] = lines[hits[0]].replace(old, new, 1)
    if budget is not None:
        hits = [i for i, line in enumerate(lines) if line.startswith(BUDGET_LINE)]
        if len(hits) != 1:
            _fail(f"budget line '{BUDGET_LINE}' found {len(hits)} times")
        lines[hits[0]] = lines[hits[0]].replace(BUDGET_LINE, f"context_budget_tokens = {budget}", 1)
    digest = hashlib.sha256(raw).hexdigest()[:12]
    header = (
        f"# M21 arm {arm_name(arm, budget)} "
        f"(generated by tests/m21_ab.py from cora.toml sha256 {digest})\n"
    )
    return header + "".join(lines)


def check_arm(path: Path, switches: set[str]) -> None:
    _, cfg = load_resolved(path, ROOT)
    cheap = next((m for m in cfg.models if m.tier == "cheap"), None)
    if (
        cheap is None
        or cheap.id != MODEL
        or cheap.provider != "gemini"
        or cheap.free_tier is not True
    ):
        _fail(f"{path.name}: first cheap-tier model is not the free {MODEL}")
    want = {
        "ledger": "L" in switches,
        "summarize": "S" in switches,
        "repo_map": "M" in switches,
        "dedupe_reads": "D" in switches,
        "compress_observations": "C" in switches,
    }
    got = {
        "ledger": cfg.memory.ledger,
        "summarize": cfg.memory.summarize == "llm",
        "repo_map": cfg.context.repo_map,
        "dedupe_reads": cfg.context.dedupe_reads,
        "compress_observations": cfg.cache.compress_observations,
    }
    for name, value in want.items():
        if got[name] != value:
            _fail(f"{path.name}: {name} is {got[name]}, expected {value}")


def write_arms(root: Path, best: Sequence[str] = (), budget: int | None = None) -> dict[str, str]:
    best = tuple(best)
    if best and budget is not None:
        _fail("--best and --budget cannot be combined")
    if best:
        plan = [("BEST", best, None)]
    elif budget is not None:
        plan = [(a, (), budget) for a in BUDGET_ARMS]
    else:
        plan = [(a, (), None) for a in SINGLE_ARMS]
    arms_dir = root / "arms"
    arms_dir.mkdir(parents=True, exist_ok=True)
    index_path = arms_dir / "arms.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    out: dict[str, str] = {}
    for arm, arm_best, b in plan:
        name = arm_name(arm, b)
        path = arms_dir / f"{name}.toml"
        path.write_text(arm_text(arm, arm_best, b), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        index[name] = digest
        out[name] = digest
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for arm, arm_best, b in plan:
        if arm_best:
            switches = set(arm_best)
        else:
            switches = {arm} if arm in SWITCH_ARMS else set()
        check_arm(arms_dir / f"{arm_name(arm, b)}.toml", switches)
    return out


def child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
    key = env.get("GEMINI_API_KEY")
    if not key or len(key) < 8:
        _fail("GEMINI_API_KEY is missing or too short")
    return env


def bench_command(cfg: Path, task: str, r: int, out: Path) -> list[str]:
    return [
        "uv",
        "run",
        "cora",
        "bench",
        "--live",
        "--suite",
        "e2e",
        "--tasks",
        task,
        "--models",
        MODEL,
        "--protocols",
        "react",
        "--max-iterations",
        "30",
        "--max-cost",
        "0.30",
        "--repeats",
        "1",
        "--seed",
        str(r),
        "--config",
        str(cfg),
        "--out",
        str(out),
    ]


def classify(result: dict) -> str:
    end = result.get("end_reason")
    detail = str(result.get("detail") or "")
    if (end == "error" and BLOCKED_RE.search(detail)) or result.get(
        "stop_reason"
    ) == "provider_timeout":
        return "blocked"
    if end is None or end in ("error", "aborted"):
        return "defect"
    return "ok"


@functools.lru_cache(maxsize=1)
def _prices() -> tuple[float, float]:
    cfg = load_config(ROOT / "cora.toml")
    spec = find_model(cfg.models, PRICE_MODEL)
    if spec is None or not spec.price_known:
        _fail(f"no price for {PRICE_MODEL} in cora.toml")
    return float(spec.input_usd_per_mtok), float(spec.output_usd_per_mtok)


def _num(x: object) -> float:
    return float(x) if isinstance(x, (int, float)) else 0.0


def _session_events(run_dir: Path) -> list[dict]:
    events: list[dict] = []
    for p in sorted((run_dir / "state" / "sessions").glob("*/events.jsonl")):
        events.extend(read_events(p))
    return events


def _memory_kinds(run_dir: Path) -> list[str]:
    kinds: list[str] = []
    for p in sorted((run_dir / "state" / "memory").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                kinds.append(json.loads(line).get("kind"))
    return kinds


def _path_keys(run_dir: Path) -> dict:
    name = run_dir.name
    return {
        "arm": run_dir.parent.parent.name,
        "task": run_dir.parent.name,
        "repeat": int(name[1:].split("-")[0]),
        "attempt": 1 if name.endswith("-retry1") else 0,
    }


def run_record(run_dir: Path) -> dict:
    keys = _path_keys(run_dir)
    report_path = run_dir / "report.json"
    if not report_path.exists():
        return {"class": "defect", **keys}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = report.get("results") or []
    if not results:
        return {"class": "defect", **keys}
    res = results[0]
    events = _session_events(run_dir)
    by = {
        t: [e for e in events if e.get("type") == t]
        for t in (
            "llm_call",
            "repo_map",
            "summary_call",
            "ledger_update",
            "ledger_evict_note",
            "read_dedupe",
            "observation_compress",
        )
    }
    llm = by["llm_call"]
    repo = by["repo_map"]
    providers = sorted({e["provider"] for e in llm if e.get("provider")})
    in_t = int(_num(res.get("input_tokens")))
    out_t = int(_num(res.get("output_tokens")))
    cost_usd = _num(res.get("cost_usd"))
    p_in, p_out = _prices()
    return {
        **keys,
        "run_id": res.get("run_id"),
        "status": res.get("status"),
        "solved": res.get("full_pass") is True,
        "class": classify(res),
        "end_reason": res.get("end_reason"),
        "stop_reason": res.get("stop_reason"),
        "iterations": int(_num(res.get("iterations"))),
        "calls": int(_num(res.get("calls"))),
        "input_tokens": in_t,
        "output_tokens": out_t,
        "cost_usd": cost_usd,
        "cost_eq_usd": (in_t * p_in + out_t * p_out) / 1e6,
        "wall_s": _num(report.get("wall_s")),
        "evictions": sum(1 for k in _memory_kinds(run_dir) if k == "evicted"),
        "ledger_update": len(by["ledger_update"]),
        "ledger_evict_note": len(by["ledger_evict_note"]),
        "summary_ok": sum(1 for e in by["summary_call"] if e.get("ok") is True),
        "summary_failed": sum(1 for e in by["summary_call"] if e.get("ok") is False),
        "read_dedupe": sum(int(_num(e.get("superseded"))) for e in by["read_dedupe"]),
        "compressed": sum(int(_num(e.get("compressed"))) for e in by["observation_compress"]),
        "repo_map_chars": int(_num(repo[0].get("chars"))) if repo else 0,
        "repo_map_tokens": int(_num(repo[0].get("tokens"))) if repo else 0,
        "peak_prompt_tokens": max(
            (int(_num(e.get("prompt_tokens_estimate"))) for e in llm), default=0
        ),
        "providers": providers,
        "openrouter_calls": sum(1 for e in llm if e.get("provider") == "openrouter"),
        "cost_source": "free_tier" if providers == ["gemini"] and cost_usd == 0 else "CHECK",
    }


def counted(records: list[dict]) -> tuple[dict[str, dict[str, list[dict]]], list[dict]]:
    groups: dict[tuple, dict[int, dict]] = {}
    for r in records:
        groups.setdefault((r["arm"], r["task"], r["repeat"]), {})[r["attempt"]] = r
    out: dict[str, dict[str, list[dict]]] = {}
    blocked: list[dict] = []
    for (arm, task, _rep), by_attempt in sorted(groups.items()):
        first = by_attempt.get(0)
        second = by_attempt.get(1)
        chosen = None
        if first is not None and first["class"] == "ok":
            chosen = first
        elif second is not None and second["class"] == "ok":
            chosen = second
        if chosen is None:
            blocked.extend(by_attempt[a] for a in sorted(by_attempt))
            continue
        out.setdefault(arm, {}).setdefault(task, []).append(chosen)
        blocked.extend(by_attempt[a] for a in sorted(by_attempt) if by_attempt[a] is not chosen)
    return out, blocked


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def overlap_label(a: tuple[float, float], b: tuple[float, float]) -> str:
    alo, ahi = a
    blo, bhi = b
    if (alo <= blo and bhi <= ahi) or (blo <= alo and ahi <= bhi):
        return "full"
    if max(alo, blo) <= min(ahi, bhi):
        return "partial"
    return "none"


def verdict(
    switch: str | None, off: dict[str, list], on: dict[str, list], tasks: Sequence[str]
) -> dict:
    common = [t for t in tasks if len(off.get(t, [])) == REPEATS and len(on.get(t, [])) == REPEATS]
    if len(common) < MIN_COMMON:
        return {"verdict": "not measured", "common": len(common)}
    off_runs = [r for t in common for r in off[t]]
    on_runs = [r for t in common for r in on[t]]
    n = len(off_runs)
    k_off = sum(1 for r in off_runs if r["solved"])
    k_on = sum(1 for r in on_runs if r["solved"])
    drops = [
        t
        for t in common
        if sum(1 for r in off[t] if r["solved"]) - sum(1 for r in on[t] if r["solved"]) >= 2
    ]
    a = k_on >= k_off and len(drops) <= len(common) / 4
    in_off = _mean([r["input_tokens"] for r in off_runs])
    in_on = _mean([r["input_tokens"] for r in on_runs])
    b = in_on <= (1 - MARGIN) * in_off
    it_off = _mean([r["iterations"] for r in off_runs])
    it_on = _mean([r["iterations"] for r in on_runs])
    c = it_on <= (1 + MARGIN) * it_off
    d_runs = None
    d = None
    if switch in D_COUNTER:
        d_runs = sum(1 for r in on_runs if r[D_COUNTER[switch]] > 0)
        d = d_runs >= MIN_EVICT_RUNS
    if d is False:
        text = "not evaluable (no eviction)"
    elif a and b and c:
        text = FLIP_TEXT
    else:
        text = "stays OFF"
    wo = wilson_interval(k_off, n)
    wn = wilson_interval(k_on, n)
    return {
        "verdict": text,
        "switch": switch,
        "common": len(common),
        "n": n,
        "k_off": k_off,
        "k_on": k_on,
        "wilson_off": list(wo) if wo else None,
        "wilson_on": list(wn) if wn else None,
        "overlap": overlap_label(wo, wn),
        "drops": drops,
        "a": a,
        "b": b,
        "c": c,
        "d": d,
        "d_runs": d_runs,
        "in_off": in_off,
        "in_on": in_on,
        "it_off": it_off,
        "it_on": it_on,
        "cost_eq_off": _mean([r["cost_eq_usd"] for r in off_runs]),
        "cost_eq_on": _mean([r["cost_eq_usd"] for r in on_runs]),
    }


def best_set(verdicts: dict[str, dict]) -> tuple[str, ...]:
    flips = tuple(
        s for s in SWITCH_ARMS if str(verdicts.get(s, {}).get("verdict", "")).startswith("flip")
    )
    if flips:
        return flips
    ratios: dict[str, float] = {}
    for s in SWITCH_ARMS:
        v = verdicts.get(s)
        if not v or v.get("verdict") == "not measured":
            continue
        if v["k_on"] >= v["k_off"]:
            ratios[s] = v["k_on"] / v["n"]
    if not ratios:
        return ()
    top = max(ratios.values())
    return tuple(s for s in SWITCH_ARMS if ratios.get(s) == top)


def _select_ids(ids: Sequence[str]) -> tuple[e2e.E2ETask, ...]:
    return _select(ids)


def plan_text(arm: str, tasks: Sequence[str]) -> str:
    selected = _select_ids(tasks)
    ids = [t.id for t in selected]
    runs = len(ids) * REPEATS
    est_calls = REPEATS * sum(CAL_ITERATIONS.get(t.id, t.max_iterations) for t in selected)
    upper = REPEATS * sum(t.max_iterations for t in selected)
    hours = est_calls * SEC_PER_CALL / 3600
    return "\n".join(
        [
            f"arm {arm}: tasks {len(ids)}, runs {runs}",
            f"예상 호출 {est_calls} (상한 {upper}), "
            f"예상 시간 {hours:.1f} h (호출당 {SEC_PER_CALL:g} s)",
            "rpm_limit 5, 지출 $0 (paid $0, OpenRouter key unset)",
        ]
    )


def prereg_committed() -> bool:
    proc = subprocess.run(
        ["git", "show", "HEAD:.docs/bench-results.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0 and PREREG_HEADING in proc.stdout


def _line(rec: dict) -> str:
    cls = rec.get("class", "defect")
    if cls == "ok":
        status = "solved" if rec.get("solved") else "failed"
    else:
        status = cls
    suffix = "-retry1" if rec.get("attempt") else ""
    return (
        f"{rec.get('arm')} {rec.get('task')} r{rec.get('repeat')}{suffix} {status} "
        f"it={rec.get('iterations')} in={rec.get('input_tokens')} "
        f"evict={rec.get('evictions')} compressed={rec.get('compressed')} "
        f"dedupe={rec.get('read_dedupe')}"
    )


def _execute(cfg: Path, task: str, r: int, run_dir: Path, env: dict[str, str]) -> dict:
    if not (run_dir / "report.json").exists():
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        log = run_dir.with_name(run_dir.name + ".log")
        with log.open("w", encoding="utf-8") as fh:
            subprocess.run(
                bench_command(cfg, task, r, run_dir),
                cwd=ROOT,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=fh,
                stderr=subprocess.STDOUT,
                check=False,
            )
    rec = run_record(run_dir)
    print(_line(rec))
    return rec


def run_segment(arm: str, tasks: Sequence[str], phase: str, root: Path, dry_run: bool) -> int:
    if phase not in ("rehearsal", "counted"):
        _fail(f"unknown phase '{phase}'")
    ids = list(tasks)
    _select(ids)
    if phase == "rehearsal":
        if len(ids) != 1:
            _fail("rehearsal takes exactly one task")
    else:
        if tuple(ids) != TASK_ORDER[: len(ids)]:
            _fail("counted tasks must be a prefix of TASK_ORDER")
        if not prereg_committed():
            _fail(
                f"pre-registration is not in HEAD (no '{PREREG_HEADING}' in .docs/bench-results.md)"
            )
    cfg = root / "arms" / f"{arm}.toml"
    if not cfg.exists():
        _fail(f"missing arm config {cfg}")
    index_path = root / "arms" / "arms.json"
    if not index_path.exists():
        _fail(f"missing {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if phase == "counted":
        if index.get(arm) != hashlib.sha256(cfg.read_bytes()).hexdigest():
            _fail(f"{cfg.name} sha256 does not match arms.json")
    repeats = REPEATS if phase == "counted" else 1
    if dry_run:
        for task in ids:
            for r in range(repeats):
                print(" ".join(bench_command(cfg, task, r, root / phase / arm / task / f"r{r}")))
        return 0
    env = child_env()
    resume = (
        f"uv run python tests/m21_ab.py run --arm {arm} --tasks {','.join(ids)} "
        f"--phase {phase} --root {root}"
    )
    consecutive = 0
    for task in ids:
        for r in range(repeats):
            run_dir = root / phase / arm / task / f"r{r}"
            rec = _execute(cfg, task, r, run_dir, env)
            if rec["class"] == "defect":
                print(f"DEFECT {run_dir}")
                return 4
            if rec["class"] == "blocked":
                retry_dir = root / phase / arm / task / f"r{r}-retry1"
                if not (retry_dir / "report.json").exists():
                    time.sleep(RETRY_WAIT_S)
                rec = _execute(cfg, task, r, retry_dir, env)
                if rec["class"] == "defect":
                    print(f"DEFECT {retry_dir}")
                    return 4
                if rec["class"] == "blocked":
                    print(f"BLOCKED {arm} {task} r{r}")
                    consecutive += 1
                    if consecutive >= 2:
                        print(f"resume: {resume}")
                        return 3
                    continue
            consecutive = 0
    return 0


def rehearsal_check(root: Path, task: str) -> int:
    fails: list[str] = []
    blocked: list[str] = []
    rows: list[str] = [
        "| 팔 | run dir | 상태 | iterations | 축출 | 스위치 이벤트 | 비고 |",
        "|---|---|---|---|---|---|---|",
    ]
    infos: list[str] = []
    for arm in SINGLE_ARMS:
        base = root / "rehearsal" / arm / task / "r0"
        retry = root / "rehearsal" / arm / task / "r0-retry1"
        rec = run_record(base)
        run_dir = base
        if rec["class"] == "blocked" and (retry / "report.json").exists():
            rec = run_record(retry)
            run_dir = retry
        if rec["class"] == "blocked":
            blocked.append(arm)
            rows.append(f"| {arm} | {run_dir} | BLOCKED | - | - | - | 재실행 필요(결함 아님) |")
            continue
        if rec["class"] != "ok":
            fails.append(f"{arm}: missing or defect ({run_dir})")
            rows.append(f"| {arm} | {run_dir} | DEFECT | - | - | - | - |")
            continue
        ev = _session_events(run_dir)
        kinds = Counter(e.get("type") for e in ev)
        if rec["openrouter_calls"] > 0:
            fails.append(f"{arm}: openrouter calls {rec['openrouter_calls']}")
        if rec["cost_usd"] != 0:
            fails.append(f"{arm}: cost_usd {rec['cost_usd']}")
        if arm == "OFF":
            present = [t for t in SWITCH_EVENTS if kinds.get(t)]
            if present:
                fails.append(f"OFF: switch events {present}")
        if arm == "M" and not kinds.get("repo_map"):
            fails.append("M: no repo_map event")
        if arm == "L" and not kinds.get("ledger_update"):
            fails.append("L: no ledger_update event")
        if (
            arm == "S"
            and rec["evictions"] > 0
            and not any(e.get("type") == "llm_call" and e.get("purpose") == "summary" for e in ev)
        ):
            fails.append("S: evictions but no summary llm_call")
        switch_events = ", ".join(f"{t}:{kinds[t]}" for t in SWITCH_EVENTS if kinds.get(t)) or "-"
        rows.append(
            f"| {arm} | {run_dir} | {rec['class']} | {rec['iterations']} | {rec['evictions']} "
            f"| {switch_events} | - |"
        )
        if arm == "D":
            infos.append(f"INFO D: read_dedupe seen = {bool(kinds.get('read_dedupe'))}")
        if arm == "C":
            infos.append(
                f"INFO C: observation_compress seen = {bool(kinds.get('observation_compress'))}"
            )
        infos.append(f"INFO {arm}: evictions {rec['evictions']}")
    print("\n".join(rows))
    for line in infos:
        print(line)
    for arm in blocked:
        print(f"BLOCKED {arm}")
    for line in fails:
        print(f"FAIL {line}")
    if fails:
        print("rehearsal-check: FAIL")
        return 1
    if blocked:
        print("rehearsal-check: INCOMPLETE (blocked arms need a re-run)")
        return 0
    print("rehearsal-check: PASS")
    return 0


def _pct(new: float, old: float) -> str:
    if not old:
        return "n/a"
    return f"{(new - old) / old * 100:+.1f}%"


def _fmt_wilson(k: int, n: int) -> str:
    w = wilson_interval(k, n)
    if w is None:
        return "-"
    return f"[{w[0]:.3f}, {w[1]:.3f}]"


def _arm_order(names: Sequence[str]) -> list[str]:
    head = [a for a in (*SINGLE_ARMS, "BEST") if a in names]
    return head + sorted(a for a in names if a not in head)


def summary_md(root: Path, tasks: Sequence[str]) -> tuple[str, dict]:
    tasks = list(tasks)
    records: list[dict] = []
    for d in sorted((root / "counted").glob("*/*/r*")):
        if d.is_dir() and d.parent.name in tasks:
            records.append(run_record(d))
    counted_map, blocked = counted(records)
    chosen = {
        (r["arm"], r["task"], r["repeat"])
        for arm in counted_map
        for t in counted_map[arm]
        for r in counted_map[arm][t]
    }
    missing = sorted({(r["arm"], r["task"], r["repeat"]) for r in records} - chosen)
    arms = _arm_order({r["arm"] for r in records})
    md: list[str] = []

    md.append("### 1. 축출/압축 카운터")
    for arm in arms:
        md.append(f"\n**팔 {arm}**\n")
        md.append(
            "| 과제 | 실행 n | 축출 있는 실행 | 축출 합 | 압축 합 | 중복 대체 합 "
            "| repo map 토큰(평균) | 표시 |"
        )
        md.append("|---|---|---|---|---|---|---|---|")
        all_runs: list[dict] = []
        for t in tasks:
            runs = counted_map.get(arm, {}).get(t, [])
            all_runs += runs
            ev = sum(1 for r in runs if r["evictions"] > 0)
            comp = sum(r["compressed"] for r in runs)
            label = "축출 없음" if ev == 0 and comp == 0 else "축출/압축 있음"
            md.append(
                f"| {t} | {len(runs)} | {ev} | {sum(r['evictions'] for r in runs)} | {comp} "
                f"| {sum(r['read_dedupe'] for r in runs)} "
                f"| {_mean([r['repo_map_tokens'] for r in runs]):.0f} | {label if runs else '-'} |"
            )
        ev = sum(1 for r in all_runs if r["evictions"] > 0)
        comp = sum(r["compressed"] for r in all_runs)
        label = "축출 없음" if ev == 0 and comp == 0 else "축출/압축 있음"
        md.append(
            f"| 합계 | {len(all_runs)} | {ev} | {sum(r['evictions'] for r in all_runs)} | {comp} "
            f"| {sum(r['read_dedupe'] for r in all_runs)} "
            f"| {_mean([r['repo_map_tokens'] for r in all_runs]):.0f} | {label} |"
        )

    md.append("\n### 2. 팔별 과제 결과")
    for arm in arms:
        md.append(f"\n**팔 {arm}**\n")
        md.append(
            "| 과제 | k/n | 평균 반복 | 평균 입력 토큰 | 평균 출력 토큰 | 평균 환산 비용 $ "
            "| 평균 벽시계 s | blocked |"
        )
        md.append("|---|---|---|---|---|---|---|---|")
        for t in tasks:
            runs = counted_map.get(arm, {}).get(t, [])
            if not runs and not any(b["arm"] == arm and b["task"] == t for b in blocked):
                continue
            nb = sum(1 for b in blocked if b["arm"] == arm and b["task"] == t)
            md.append(
                f"| {t} | {sum(1 for r in runs if r['solved'])}/{len(runs)} "
                f"| {_mean([r['iterations'] for r in runs]):.1f} "
                f"| {_mean([r['input_tokens'] for r in runs]):.0f} "
                f"| {_mean([r['output_tokens'] for r in runs]):.0f} "
                f"| {_mean([r['cost_eq_usd'] for r in runs]):.5f} "
                f"| {_mean([r['wall_s'] for r in runs]):.0f} | {nb} |"
            )

    md.append("\n### 3. 팔별 합산")
    md.append("| 팔 | 과제 수 | k/n | Wilson 95% | 평균 반복 | 평균 입력 토큰 | 평균 환산 비용 $ |")
    md.append("|---|---|---|---|---|---|---|")
    pooled: dict[str, dict] = {}
    for arm in arms:
        runs = [r for t in tasks for r in counted_map.get(arm, {}).get(t, [])]
        if not runs:
            continue
        k = sum(1 for r in runs if r["solved"])
        n = len(runs)
        ntask = sum(1 for t in tasks if counted_map.get(arm, {}).get(t))
        pooled[arm] = {
            "tasks": ntask,
            "k": k,
            "n": n,
            "wilson": list(wilson_interval(k, n) or ()),
            "iterations": _mean([r["iterations"] for r in runs]),
            "input_tokens": _mean([r["input_tokens"] for r in runs]),
            "cost_eq_usd": _mean([r["cost_eq_usd"] for r in runs]),
        }
        p = pooled[arm]
        md.append(
            f"| {arm} | {ntask} | {k}/{n} | {_fmt_wilson(k, n)} | {p['iterations']:.1f} "
            f"| {p['input_tokens']:.0f} | {p['cost_eq_usd']:.5f} |"
        )

    md.append("\n### 4. 스위치 판정 (R5)")
    off = counted_map.get("OFF", {})
    verdicts: dict[str, dict] = {}
    for x in SWITCH_ARMS:
        v = verdict(x, off, counted_map.get(x, {}), tasks)
        verdicts[x] = v
        if v["verdict"] == "not measured":
            md.append(f"- {x}: not measured (공통 과제 {v['common']} < {MIN_COMMON})")
            continue
        d_text = "n/a" if v["d"] is None else f"{v['d_runs']} ({'pass' if v['d'] else 'fail'})"
        md.append(
            f"- {x}: (a) k {v['k_on']}/{v['n']} vs OFF {v['k_off']}/{v['n']}, "
            f"2회 이상 하락 과제 {len(v['drops'])}/{v['common']} (≤1/4?) "
            f"→ {'pass' if v['a'] else 'fail'}; "
            f"(b) 평균 입력 토큰 {v['in_on']:.0f} vs {v['in_off']:.0f} "
            f"({_pct(v['in_on'], v['in_off'])}) → {'pass' if v['b'] else 'fail'}; "
            f"(c) 평균 반복 {v['it_on']:.1f} vs {v['it_off']:.1f} "
            f"({_pct(v['it_on'], v['it_off'])}) → {'pass' if v['c'] else 'fail'}; "
            f"(d) 축출/압축 실행 {d_text}; "
            f"Wilson 구간 겹침 {v['overlap']}; 공통 과제 {v['common']} → {v['verdict']}"
        )

    best = best_set(verdicts)
    md.append("\n### 5. BEST")
    md.append(f"- BEST 스위치 집합: {', '.join(best) if best else '없음'}")
    best_aux = None
    if counted_map.get("BEST"):
        bv = verdict(None, off, counted_map["BEST"], tasks)
        best_aux = bv
        if bv["verdict"] == "not measured":
            md.append(
                f"- 보조 결과(기본값 변경 근거 아님): not measured (공통 과제 {bv['common']})"
            )
        else:
            md.append(
                f"- 보조 결과(기본값 변경 근거 아님): k {bv['k_on']}/{bv['n']} "
                f"vs OFF {bv['k_off']}/{bv['n']}, "
                f"입력 토큰 {_pct(bv['in_on'], bv['in_off'])}, "
                f"반복 {_pct(bv['it_on'], bv['it_off'])}"
            )

    md.append("\n### 6. blocked 목록 (재시도 포함)")
    for b in blocked:
        md.append(
            f"- {b['arm']} {b['task']} r{b['repeat']} attempt {b['attempt']}: class {b['class']}, "
            f"end_reason {b.get('end_reason')}, stop_reason {b.get('stop_reason')}"
        )
    if not blocked:
        md.append("- 없음")
    md.append(
        "- 결측(재시도 후에도 blocked): "
        + (", ".join(f"{a} {t} r{r}" for a, t, r in missing) if missing else "없음")
    )

    md.append("\n### 7. 지출")
    total = sum(r["cost_usd"] for r in records)
    openrouter = sum(r["openrouter_calls"] for r in records)
    sources = sorted({r["cost_source"] for r in records})
    md.append(f"- Σ cost_usd {total:.6f}, Σ openrouter_calls {openrouter}, cost_source {sources}")

    summary = {
        "tasks": tasks,
        "arms": arms,
        "pooled": pooled,
        "verdicts": verdicts,
        "best": list(best),
        "best_aux": best_aux,
        "blocked": blocked,
        "missing": [list(k) for k in missing],
        "spend": {"cost_usd": total, "openrouter_calls": openrouter, "cost_sources": sources},
        "runs": records,
    }
    return "\n".join(md), summary


def keygrep(paths: list[Path]) -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key or len(key) < 8:
        _fail("GEMINI_API_KEY is missing or too short")
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


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="m21_ab")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_root(q: argparse.ArgumentParser) -> None:
        q.add_argument("--root", type=Path, default=OUT_ROOT)

    a = sub.add_parser("arms")
    add_root(a)
    a.add_argument("--best")
    a.add_argument("--budget", type=int)

    pl = sub.add_parser("plan")
    add_root(pl)
    pl.add_argument("--arm", required=True)
    pl.add_argument("--tasks", required=True)

    rn = sub.add_parser("run")
    add_root(rn)
    rn.add_argument("--arm", required=True)
    rn.add_argument("--tasks", required=True)
    rn.add_argument("--phase", required=True, choices=("rehearsal", "counted"))
    rn.add_argument("--dry-run", action="store_true")

    rc = sub.add_parser("rehearsal-check")
    add_root(rc)
    rc.add_argument("--task", required=True)

    sm = sub.add_parser("summary")
    add_root(sm)
    sm.add_argument("--tasks", default=",".join(TASK_ORDER))

    bs = sub.add_parser("best")
    add_root(bs)

    kg = sub.add_parser("keygrep")
    add_root(kg)
    kg.add_argument("paths", nargs="+", type=Path)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "keygrep":
        print(json.dumps(keygrep(args.paths), ensure_ascii=False, indent=2))
        return 0
    root = args.root.resolve()
    if args.cmd == "arms":
        best = _split(args.best) if args.best else ()
        print(json.dumps(write_arms(root, best, args.budget), indent=2, sort_keys=True))
        return 0
    if args.cmd == "plan":
        print(plan_text(args.arm, _split(args.tasks)))
        return 0
    if args.cmd == "run":
        return run_segment(args.arm, _split(args.tasks), args.phase, root, args.dry_run)
    if args.cmd == "rehearsal-check":
        return rehearsal_check(root, args.task)
    if args.cmd == "summary":
        md, summary = summary_md(root, _split(args.tasks))
        root.mkdir(parents=True, exist_ok=True)
        (root / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(md)
        return 0
    if args.cmd == "best":
        path = root / "summary.json"
        if not path.exists():
            _fail(f"missing {path}; run summary first")
        summary = json.loads(path.read_text(encoding="utf-8"))
        print(",".join(best_set(summary["verdicts"])) or "none")
        return 0
    _fail(f"unknown command '{args.cmd}'")


if __name__ == "__main__":
    raise SystemExit(main())
