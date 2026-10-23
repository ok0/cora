from __future__ import annotations

import argparse
import asyncio
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest.mock
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import cora.core.deciders.llm as llm_mod
from cora.core.config import find_config, find_model, load_config
from cora.core.decider import DecisionHooks
from cora.core.deciders.llm import LLMDecider
from cora.core.metering import CostMeter
from cora.core.providers.base import create_provider
from m15_baseline import FORBIDDEN_DEFAULT, HIDDEN_ENV, audit
from m19c_probe import KEY_ENV, GeminiOnlyPool, probe_config
from m19e_data import require_prereg

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/m19e"
S1A_PROMPT = FIX / "judge-prompt-s1a.txt"
S1B_PROMPT = FIX / "judge-prompt-s1b.txt"
INPUTS_DEFAULT = FIX / "inputs.jsonl"
OUT_DEFAULT = FIX / "judge-scores.jsonl"
JUDGE_INPUT_CAP = 8000
S1B_MODEL = "gemini-3.5-flash-lite"
S1A_MODEL = "claude-sonnet-5-5"
S1A_TIMEOUT_S = 300
SCORE_HI = 24
CRITERIA = tuple(f"c{i}" for i in range(1, 9))
FORBIDDEN = FORBIDDEN_DEFAULT + (
    ".cora_grader",
    "judge-scores",
    "signals.md",
    "bench-results",
    "report.json",
)
_OBJ_RE = re.compile(r"\{[^{}]*\}")


def prompt_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def parse_s1a(text: str) -> dict | None:
    found = _OBJ_RE.findall(text)
    if not found:
        return None
    try:
        data = json.loads(found[-1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    criteria: dict[str, int] = {}
    for key in CRITERIA:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3:
            return None
        criteria[key] = value
    total = sum(criteria.values())
    return {
        "criteria": criteria,
        "total": total,
        "total_mismatch": data.get("total") != total,
    }


def s1a_env(environ: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in environ.items() if k not in HIDDEN_ENV}


def s1a_command(prompt: str, model: str) -> list[str]:
    return [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--model",
        model,
        "--max-budget-usd",
        "0.50",
        "--strict-mcp-config",
        "--mcp-config",
        '{"mcpServers":{}}',
        "--disallowedTools",
        "WebFetch",
        "WebSearch",
        "Bash",
        "Edit",
        "Write",
        "--allowedTools",
        "Read Glob Grep",
    ]


def judge_dir(judge_input: str = "") -> Path:
    d = Path(tempfile.mkdtemp(prefix="cora-m19e-"))
    resolved = d.resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise RuntimeError("m19e: judge directory must be outside the repository")
    (d / "judge-input.md").write_text(judge_input, encoding="utf-8")
    return d


def _audit_session(session_id: str | None) -> tuple[str, list[str]]:
    if not session_id:
        return "not_found", []
    matches = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{session_id}.jsonl"))
    if not matches:
        return "not_found", []
    hits = audit(Path(matches[0]), FORBIDDEN)
    return ("violations" if hits else "ok"), hits


def _row(
    row_in: Mapping[str, Any],
    judge: str,
    judge_id: str,
    *,
    status: str,
    score: int | None,
    criteria: dict | None,
    raw: str,
    attempts: int,
    reason: str,
    subscription_usd: float | None,
    session_id: str | None,
    audit_status: str | None,
) -> dict:
    return {
        "task": row_in["task"],
        "judge": judge,
        "judge_id": judge_id,
        "prompt_hash": prompt_hash(S1A_PROMPT if judge == "S1a" else S1B_PROMPT),
        "input_sha": row_in["judge_input_sha"],
        "status": status,
        "score": score,
        "criteria": criteria,
        "raw": raw,
        "attempts": attempts,
        "reason": reason,
        "cost_usd": 0.0,
        "subscription_equiv_usd": subscription_usd,
        "session_id": session_id,
        "audit": audit_status,
    }


def run_s1a_task(row_in: Mapping[str, Any], model: str) -> dict:
    template = S1A_PROMPT.read_text(encoding="utf-8")
    prompt_text = template.replace("{INPUT}", row_in["judge_input"])
    reason = "not_run"
    raw = ""
    for attempt in (1, 2):
        d = judge_dir(row_in["judge_input"])
        try:
            proc = subprocess.run(
                s1a_command(prompt_text, model),
                cwd=d,
                env=s1a_env(os.environ),
                capture_output=True,
                text=True,
                timeout=S1A_TIMEOUT_S,
                check=False,
            )
        except subprocess.TimeoutExpired:
            reason = "timeout"
            continue
        if proc.returncode != 0:
            reason = f"exit {proc.returncode}"
            continue
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            reason = "bad_json"
            continue
        raw = str(out.get("result", ""))
        session_id = out.get("session_id")
        usage = out.get("modelUsage") or {}
        judge_id = ",".join(sorted(usage)) or model
        subscription = out.get("total_cost_usd")
        subscription_usd = float(subscription) if subscription is not None else None
        audit_status, hits = _audit_session(session_id)
        if audit_status == "violations":
            return _row(
                row_in, "S1a", judge_id, status="blocked", score=None,
                criteria=None, raw=raw, attempts=attempt, reason="isolation",
                subscription_usd=subscription_usd, session_id=session_id,
                audit_status=audit_status,
            )
        parsed = parse_s1a(raw)
        if parsed is None:
            reason = "unparsed"
            continue
        note = "total_mismatch" if parsed["total_mismatch"] else ""
        return _row(
            row_in, "S1a", judge_id, status="ok", score=parsed["total"],
            criteria=parsed["criteria"], raw=raw, attempts=attempt, reason=note,
            subscription_usd=subscription_usd, session_id=session_id,
            audit_status=audit_status,
        )
    return _row(
        row_in, "S1a", model, status="blocked", score=None, criteria=None,
        raw=raw, attempts=2, reason=reason, subscription_usd=None, session_id=None,
        audit_status=None,
    )


async def _s1b_task(
    decider: LLMDecider, pool: GeminiOnlyPool, question: str, row_in: Mapping[str, Any], model: str
) -> dict:
    reason = "not_run"
    raw = ""
    for attempt in (1, 2):
        meter = CostMeter()
        decider.begin_request(DecisionHooks(meter=meter))
        n0 = len(pool.raw)
        s = await decider.score(question, 0, SCORE_HI, text=row_in["judge_input"])
        raw = "\n".join(pool.raw[n0:])
        if meter.total_cost_usd != 0.0:
            raise RuntimeError("m19e: S1b cost must be zero")
        if not s.fallback_used:
            return _row(
                row_in, "S1b", f"gemini:{model}", status="ok", score=int(s.value),
                criteria=None, raw=raw, attempts=attempt, reason="", subscription_usd=None,
                session_id=None, audit_status=None,
            )
        reason = s.reason
    return _row(
        row_in, "S1b", f"gemini:{model}", status="blocked", score=None,
        criteria=None, raw=raw, attempts=2, reason=reason, subscription_usd=None,
        session_id=None, audit_status=None,
    )


async def _run_s1b_async(
    rows_in: Sequence[Mapping[str, Any]],
    config: Any,
    pool: GeminiOnlyPool,
    model: str,
) -> list[dict]:
    question = S1B_PROMPT.read_text(encoding="utf-8")
    decider = LLMDecider(probe_config(config, model), pool)
    out: list[dict] = []
    with unittest.mock.patch.object(llm_mod, "MAX_INPUT_CHARS", JUDGE_INPUT_CAP):
        for row_in in rows_in:
            if len(row_in["judge_input"]) > JUDGE_INPUT_CAP:
                raise ValueError(f"m19e: judge input for {row_in['task']} exceeds cap")
            out.append(await _s1b_task(decider, pool, question, row_in, model))
    return out


def run_s1b(
    rows_in: Sequence[Mapping[str, Any]], config: Any, pool: GeminiOnlyPool, model: str
) -> list[dict]:
    return asyncio.run(_run_s1b_async(rows_in, config, pool, model))


def write_rows(path: Path, judge: str, rows: Sequence[dict]) -> None:
    kept: list[dict] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if item["judge"] != judge:
                    kept.append(item)
    merged = sorted(kept + list(rows), key=lambda r: (r["judge"], r["task"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged), encoding="utf-8"
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="m19e_judge")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_a = sub.add_parser("s1a")
    p_a.add_argument("--model", default=S1A_MODEL)
    p_b = sub.add_parser("s1b")
    p_b.add_argument("--model", default=S1B_MODEL)
    for p in (p_a, p_b):
        p.add_argument("--inputs", type=Path, default=INPUTS_DEFAULT)
        p.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args(argv)
    try:
        require_prereg()
    except SystemExit as exc:
        return int(exc.code or 2)
    try:
        rows_in = _read_jsonl(args.inputs)
        if args.cmd == "s1a":
            rows = [run_s1a_task(r, args.model) for r in rows_in]
            judge = "S1a"
        else:
            cfg = load_config(find_config(None))
            spec = find_model(cfg.models, args.model)
            if spec is None or spec.provider != "gemini" or spec.free_tier is not True:
                print(
                    f"m19e: model {args.model!r} is not a free_tier gemini model",
                    file=sys.stderr,
                )
                return 2
            key_env = cfg.providers["gemini"].get("api_key_env", KEY_ENV)
            if not os.environ.get(key_env):
                print(f"{key_env} not set", file=sys.stderr)
                return 2
            pool = GeminiOnlyPool(
                create_provider("gemini", cfg.providers["gemini"]), key_env=key_env
            )
            rows = run_s1b(rows_in, cfg, pool, args.model)
            judge = "S1b"
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_rows(args.out, judge, rows)
    blocked = [r["task"] for r in rows if r["status"] == "blocked"]
    print(f"{judge}: ok {len(rows) - len(blocked)}, blocked {len(blocked)}")
    print(f"blocked: {', '.join(blocked) or 'none'}")
    print("openrouter_calls: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
