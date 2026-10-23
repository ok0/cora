from __future__ import annotations

import shlex
import sys
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from cora.bench.stats import LOW_N, fmt_interval_pct, fmt_pct, wilson_interval
from cora.bench.tasks import BENCH_TASKS, BenchTask
from cora.core.agent import Agent
from cora.core.config import CoraConfig
from cora.core.providers import ProviderPool
from cora.core.state import StopReason
from cora.core.tools import ApprovalPolicy


@dataclass
class BenchResult:
    task: str
    success: bool
    stop_reason: str
    iterations: int
    calls: int
    cost_usd: float
    baseline_cost_usd: float | None
    repeat_index: int = 0
    seed: int = 0


def load_baseline(path: Path) -> dict[str, float]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {k: float(v) for k, v in data.get("baseline", {}).items()}


async def run_bench(
    config: CoraConfig,
    tasks: Sequence[BenchTask] = BENCH_TASKS,
    *,
    providers: ProviderPool | None = None,
    baseline: Mapping[str, float] | None = None,
    repeats: int = 1,
    seed: int = 0,
) -> list[BenchResult]:
    base = baseline or {}
    results: list[BenchResult] = []
    for repeat_index in range(repeats):
        for t in tasks:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                for name, content in t.files.items():
                    (root / name).write_text(content, encoding="utf-8")
                check = (
                    t.check_command.format(python=shlex.quote(sys.executable))
                    if t.check_command
                    else None
                )
                agent = Agent(config, root, ApprovalPolicy("auto"), providers=providers)
                r = await agent.run(t.prompt, check_command=check)
            success = r.stop_reason == StopReason.FINAL_ANSWER and (
                t.expect_in_answer is None
                or t.expect_in_answer.lower() in (r.answer or "").lower()
            )
            results.append(
                BenchResult(
                    task=t.name,
                    success=success,
                    stop_reason=r.stop_reason.value,
                    iterations=r.session.total_iterations,
                    calls=r.summary["calls"],
                    cost_usd=r.summary["total_cost_usd"],
                    baseline_cost_usd=base.get(t.name),
                    repeat_index=repeat_index,
                    seed=seed + repeat_index,
                )
            )
    return results


def format_table(results: Sequence[BenchResult]) -> str:
    repeated = any(x.repeat_index > 0 for x in results)
    lines = [
        "| task | success | stop_reason | iterations | calls | cost_usd | baseline_cost_usd |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        baseline = "-" if r.baseline_cost_usd is None else f"{r.baseline_cost_usd:.6f}"
        label = f"{r.task}#{r.repeat_index}" if repeated else r.task
        lines.append(
            f"| {label} | {'yes' if r.success else 'no'} | {r.stop_reason} | "
            f"{r.iterations} | {r.calls} | {r.cost_usd:.6f} | {baseline} |"
        )
    n = len(results)
    n_success = sum(1 for r in results if r.success)
    sum_iter = sum(r.iterations for r in results)
    sum_calls = sum(r.calls for r in results)
    sum_cost = sum(r.cost_usd for r in results)
    baselines = [r.baseline_cost_usd for r in results if r.baseline_cost_usd is not None]
    sum_baseline = f"{sum(baselines):.6f}" if baselines else "-"
    lines.append(
        f"| TOTAL | {n_success}/{n} | - | {sum_iter} | {sum_calls} | "
        f"{sum_cost:.6f} | {sum_baseline} |"
    )
    if repeated:
        lines += [
            "",
            "| task | solved | solve_rate | wilson95 | flags |",
            "|---|---|---|---|---|",
        ]
        tasks: dict[str, list[BenchResult]] = {}
        for r in results:
            tasks.setdefault(r.task, []).append(r)
        for task_id, rs in tasks.items():
            k = sum(1 for r in rs if r.success)
            m = len(rs)
            lines.append(
                f"| {task_id} | {k}/{m} | {fmt_pct(k / m)} | "
                f"{fmt_interval_pct(wilson_interval(k, m))} | "
                f"{'low_n' if m < LOW_N else '-'} |"
            )
    return "\n".join(lines)
