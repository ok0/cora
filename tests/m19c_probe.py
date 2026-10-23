from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime
import json
import os
import sys
import unittest.mock
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import cora.core.deciders.llm as llm_mod
from cora.bench.e2e import E2ETask, agent_prompt, select_e2e_tasks
from cora.core.config import TIERS, CoraConfig, find_config, load_config
from cora.core.decider import DecisionHooks
from cora.core.deciders.llm import LLMDecider
from cora.core.errors import ConfigError
from cora.core.metering import CostMeter
from cora.core.providers.base import create_provider
from cora.core.router import HeuristicRouter, prompt_features

TASK_IDS = ("e2e_h01", "e2e_h02", "e2e_h03", "e2e_h04", "e2e_h05", "e2e_h06", "e2e_hx1", "e2e_hx2")
LABELS = {
    "e2e_h01": "strong",
    "e2e_h03": "strong",
    "e2e_h04": "strong",
    "e2e_hx2": "strong",
    "e2e_h02": "cheap",
    "e2e_h05": "cheap",
    "e2e_h06": "cheap",
    "e2e_hx1": "cheap",
}
DEFAULT_MODEL = "gemini-3.5-flash-lite"
PROVIDER = "gemini"
KEY_ENV = "GEMINI_API_KEY"
PROBE_TIMEOUT_S = 60.0
PROBE_INPUT_CAP = 6000
VARIANTS = ("spec", "spec+summary")
HEADLINE = "spec"
DEFAULT_OUT = Path(__file__).parent / "fixtures/m19/m19c-probe.md"
PROTOCOL: tuple[str, ...] = (
    (
        "P-1: task.toml difficulty is medium for e2e_h02 and e2e_h06 and hard for the "
        "other six; the set is the 8 M19 panel tasks and the difficulty column shows "
        "task.toml as-is."
    ),
    (
        "P-2: the model is gemini-3.5-flash-lite (provider gemini, free_tier true), the "
        "first flash-lite free-tier gemini entry in cora.toml order."
    ),
    (
        "P-3: the decider input is built by the probe as agent prompt plus full "
        "REQUIREMENTS.md; spec+summary appends a template and required-file count line; "
        "production routing is unchanged."
    ),
    (
        "P-4: the LLMDecider input cap is patched to 6000 chars inside the probe only "
        "(src default 2000 unchanged); any input over the cap raises."
    ),
    (
        "P-5: the probe decider timeout is 60 s; a timeout is recorded as blocked "
        "(timeout)."
    ),
    (
        "P-6: any decider fallback is recorded as blocked with its reason; blocked rows "
        "are never hits; no script-level retries; one pass per variant."
    ),
    (
        "P-7: k = hits out of 8 (blocked rows are not hits); k >= 6 not adopted; 3 to 5 "
        "near chance; k <= 2 below chance; any blocked row appends an incomplete note."
    ),
    (
        "P-8: no ProviderPool is built; only the gemini provider is reachable through "
        "GeminiOnlyPool; cost is recorded per task by CostMeter."
    ),
)


def template_file_count(task: E2ETask) -> int:
    return sum(1 for p in task.template_dir.rglob("*") if p.is_file())


def build_input(task: E2ETask, variant: str) -> str:
    if variant not in VARIANTS:
        raise ValueError(f"m19c: unknown variant {variant!r}")
    text = (
        agent_prompt(task)
        + "\n\nREQUIREMENTS.md:\n"
        + task.requirements_path.read_text(encoding="utf-8")
    )
    if variant == "spec":
        return text
    return (
        text
        + f"\n\nRepository summary: template files = {template_file_count(task)}, "
        + f"required files = {len(task.required_files)}"
    )


def probe_config(
    base: CoraConfig, model_id: str, timeout_s: float = PROBE_TIMEOUT_S
) -> CoraConfig:
    return dataclasses.replace(
        base,
        decider=dataclasses.replace(
            base.decider, kind="llm", model=model_id, timeout_s=timeout_s
        ),
    )


def redact(s: str, key_env: str = KEY_ENV) -> str:
    key = os.environ.get(key_env)
    if key:
        return s.replace(key, "<redacted>")
    return s


class _Recorder:
    def __init__(self, pool: GeminiOnlyPool) -> None:
        self.pool = pool

    async def complete(self, req):
        try:
            resp = await self.pool.provider.complete(req)
        except Exception as e:
            text = redact(str(e), self.pool.key_env)[:200]
            self.pool.raw.append(f"<error {type(e).__name__}: {text}>")
            raise
        self.pool.raw.append(resp.text)
        return resp


class GeminiOnlyPool:
    def __init__(self, provider, allowed: str = PROVIDER, key_env: str = KEY_ENV) -> None:
        self.provider = provider
        self.allowed = allowed
        self.key_env = key_env
        self.raw: list[str] = []

    def get(self, name: str) -> _Recorder:
        if name != self.allowed:
            raise ConfigError(f"m19c: provider {name!r} not allowed")
        return _Recorder(self)


@dataclass
class ProbeRow:
    task_id: str
    difficulty: str
    label: str
    variant: str
    status: str
    pick: str | None
    confidence: float | None
    hit: bool | None
    reason: str
    heur_wrapper: int
    heur_input: int
    spec_chars: int
    input_chars: int
    required_files: int
    template_files: int
    raw: str
    cost_usd: float
    cost_source: str


async def probe_task(
    decider: LLMDecider,
    pool: GeminiOnlyPool,
    router: HeuristicRouter,
    task: E2ETask,
    variant: str,
    cap: int,
) -> ProbeRow:
    text = build_input(task, variant)
    if len(text) > cap:
        raise ValueError(f"m19c: input {len(text)} chars exceeds cap {cap} for {task.id}")
    meter = CostMeter()
    decider.begin_request(DecisionHooks(meter=meter))
    n0 = len(pool.raw)
    c = await decider.choice("tier", TIERS, text=text, features=prompt_features(text))
    raw = pool.raw[n0] if len(pool.raw) > n0 else "<no call>"
    label = LABELS[task.id]
    if c.fallback_used:
        status, pick, confidence, hit, reason = "blocked", None, None, None, c.reason
    else:
        status, pick, confidence = "ok", c.label, c.confidence
        hit, reason = c.label == label, ""
    heur_wrapper = router.score(agent_prompt(task))[0]
    heur_input = router.score(text)[0]
    spec_chars = len(task.requirements_path.read_text(encoding="utf-8"))
    sources = sorted({r.cost_source for r in meter.records})
    return ProbeRow(
        task_id=task.id,
        difficulty=task.difficulty,
        label=label,
        variant=variant,
        status=status,
        pick=pick,
        confidence=confidence,
        hit=hit,
        reason=reason,
        heur_wrapper=heur_wrapper,
        heur_input=heur_input,
        spec_chars=spec_chars,
        input_chars=len(text),
        required_files=len(task.required_files),
        template_files=template_file_count(task),
        raw=raw,
        cost_usd=meter.total_cost_usd,
        cost_source=",".join(sources) if sources else "none",
    )


async def run_probe(
    config: CoraConfig,
    pool: GeminiOnlyPool,
    tasks: Sequence[E2ETask],
    variants: Sequence[str] = VARIANTS,
    cap: int = PROBE_INPUT_CAP,
) -> list[ProbeRow]:
    if not hasattr(llm_mod, "MAX_INPUT_CHARS"):
        raise RuntimeError("m19c: cora.core.deciders.llm.MAX_INPUT_CHARS is missing")
    decider = LLMDecider(config, pool)
    router = HeuristicRouter(config)
    rows: list[ProbeRow] = []
    with unittest.mock.patch.object(llm_mod, "MAX_INPUT_CHARS", cap):
        for variant in variants:
            for task in tasks:
                rows.append(await probe_task(decider, pool, router, task, variant, cap))
    return rows


def outcome_text(hits: int, blocked: Sequence[str]) -> str:
    if hits >= 6:
        text = "not adopted before paid validation on new tasks (separately approved, about $1)"
    elif hits >= 3:
        text = "near chance: no discrimination from input improvement alone"
    else:
        text = "below chance: no discrimination from input improvement alone"
    if blocked:
        text += f" (incomplete: blocked {', '.join(blocked)})"
    return text


def summarize(rows: Sequence[ProbeRow], variant: str) -> dict:
    mine = [r for r in rows if r.variant == variant]
    hits = sum(1 for r in mine if r.hit is True)
    misses = [r.task_id for r in mine if r.status == "ok" and r.hit is False]
    blocked = [r.task_id for r in mine if r.status == "blocked"]
    return {
        "hits": hits,
        "n": 8,
        "misses": misses,
        "blocked": blocked,
        "line": f"{hits}/8 hits",
        "outcome": outcome_text(hits, blocked),
    }


def _pick(r: ProbeRow) -> str:
    return r.pick if r.pick is not None else "-"


def _hit(r: ProbeRow) -> str:
    if r.hit is None:
        return "-"
    return "hit" if r.hit else "miss"


def render(rows: Sequence[ProbeRow], meta: Mapping[str, str]) -> str:
    lines: list[str] = ["# M19c spec-aware routing probe", ""]
    for k, v in meta.items():
        lines.append(f"- {k}: {v}")
    lines.append("- temperature: 0")
    lines.append("- decider: llm (src/cora/core/deciders/llm.py, unchanged)")
    lines.append("- openrouter_calls: 0 (GeminiOnlyPool)")
    lines += ["", "## Pre-registered labels", ""]
    for tid in TASK_IDS:
        lines.append(f"- {tid}: {LABELS[tid]}")
    lines += ["", "## Protocol", ""]
    for p in PROTOCOL:
        lines.append(f"- {p}")
    variants = list(dict.fromkeys(r.variant for r in rows))
    for variant in variants:
        mine = [r for r in rows if r.variant == variant]
        s = summarize(rows, variant)
        lines += [
            "",
            f"## Results: {variant}",
            "",
            "| task | difficulty | label | pick | conf | hit | status | heur_wrapper | "
            "heur_input | spec_chars | input_chars | required_files | template_files | "
            "cost_usd | cost_source |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in mine:
            conf = f"{r.confidence:.2f}" if r.confidence is not None else "-"
            lines.append(
                f"| {r.task_id} | {r.difficulty} | {r.label} | {_pick(r)} | {conf} | "
                f"{_hit(r)} | {r.status} | {r.heur_wrapper} | {r.heur_input} | "
                f"{r.spec_chars} | {r.input_chars} | {r.required_files} | "
                f"{r.template_files} | {r.cost_usd:.6f} | {r.cost_source} |"
            )
        blocked_txt = (
            ", ".join(f"{r.task_id} ({r.reason})" for r in mine if r.status == "blocked")
            or "none"
        )
        lines += [
            "",
            f"Summary: {s['line']}",
            f"Misses: {', '.join(s['misses']) or 'none'}",
            f"Blocked: {blocked_txt}",
            f"Outcome: {s['outcome']}",
        ]
    lines += ["", "## Raw answers", "", "```jsonl"]
    for r in rows:
        lines.append(
            json.dumps(
                {"variant": r.variant, "task": r.task_id, "raw": r.raw, "reason": r.reason},
                ensure_ascii=False,
            )
        )
    lines.append("```")
    total = sum(r.cost_usd for r in rows)
    sources = sorted({part for r in rows for part in r.cost_source.split(",")})
    lines += [
        "",
        "## Cost",
        "",
        f"- cost_usd total: {total:.6f}",
        f"- cost_source: {', '.join(sources) if sources else 'none'}",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M19c spec-aware routing probe (live Gemini).")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout-s", type=float, default=PROBE_TIMEOUT_S)
    parser.add_argument("--max-input-chars", type=int, default=PROBE_INPUT_CAP)
    parser.add_argument(
        "--date", default=datetime.datetime.now(datetime.UTC).date().isoformat()
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.config if args.config is not None else find_config(None))
    spec = HeuristicRouter(cfg).resolve(args.model)
    if spec is None or spec.provider != PROVIDER or not spec.free_tier:
        print(
            f"m19c: model {args.model!r} is not a free_tier {PROVIDER} model",
            file=sys.stderr,
        )
        return 2
    key_env = cfg.providers[PROVIDER]["api_key_env"]
    if not os.environ.get(key_env):
        print(f"{key_env} not set", file=sys.stderr)
        return 2

    variants = tuple(v for v in args.variants.split(",") if v)
    tasks = select_e2e_tasks(TASK_IDS)
    pool = GeminiOnlyPool(
        create_provider(PROVIDER, cfg.providers[PROVIDER]), key_env=key_env
    )
    rows = asyncio.run(
        run_probe(
            probe_config(cfg, args.model, args.timeout_s),
            pool,
            tasks,
            variants,
            args.max_input_chars,
        )
    )
    meta = {
        "date": args.date,
        "model": args.model,
        "provider": PROVIDER,
        "input_cap": str(args.max_input_chars),
        "timeout_s": str(args.timeout_s),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(rows, meta), encoding="utf-8")
    for variant in variants:
        s = summarize(rows, variant)
        print(f"{variant}: {s['line']}")
        print(s["outcome"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
