from __future__ import annotations

import math
import random
import statistics
from collections.abc import Sequence

WILSON_Z = 1.96
BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_SEED = 0
LOW_N = 5


def wilson_interval(k: int, n: int, z: float = WILSON_Z) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    z2 = z * z
    d = 1 + z2 / n
    c = (p + z2 / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def describe(values: Sequence[float]) -> dict:
    if not values:
        return {"mean": None, "median": None, "stdev": None}
    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) >= 2 else None,
    }


def percentile(sorted_values: Sequence[float], q: float) -> float:
    m = len(sorted_values)
    pos = q * (m - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def bootstrap_ratio_ci(
    numer: Sequence[float],
    denom: Sequence[float],
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    n = len(numer)
    if n == 0:
        return None
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(iterations):
        idx = rng.choices(range(n), k=n)
        d = sum(denom[i] for i in idx)
        if d > 0:
            samples.append(sum(numer[i] for i in idx) / d)
    if not samples:
        return None
    s = sorted(samples)
    return (percentile(s, alpha / 2), percentile(s, 1 - alpha / 2))


def bootstrap_mean_diff_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    iterations: int,
    seed: int,
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    if not a or not b:
        return None
    rng = random.Random(seed)
    diffs: list[float] = []
    for _ in range(iterations):
        ma = statistics.fmean(rng.choices(a, k=len(a)))
        mb = statistics.fmean(rng.choices(b, k=len(b)))
        diffs.append(ma - mb)
    s = sorted(diffs)
    return (percentile(s, alpha / 2), percentile(s, 1 - alpha / 2))


def format_n(n_a: int, n_b: int) -> str:
    return f"n={n_a}" if n_a == n_b else f"n={n_a} vs {n_b}"


def fmt_sig(x: float | None, digits: int = 3) -> str:
    if x is None:
        return "n/a"
    if abs(x) >= 10**digits:
        return f"{x:.0f}"
    return f"{x:.{digits}g}"


def fmt_pct(p: float | None) -> str:
    if p is None:
        return "n/a"
    return fmt_sig(p * 100, 2) + "%"


def fmt_interval_pct(iv: Sequence[float] | None) -> str:
    if iv is None:
        return "n/a"
    return f"{fmt_pct(iv[0])}-{fmt_pct(iv[1])}"


def solve_verdict(a: str, k_a: int, n_a: int, b: str, k_b: int, n_b: int) -> str:
    ns = format_n(n_a, n_b)
    if min(n_a, n_b) < LOW_N:
        return f"insufficient data ({ns})"
    lo_a, hi_a = wilson_interval(k_a, n_a) or (0.0, 1.0)
    lo_b, hi_b = wilson_interval(k_b, n_b) or (0.0, 1.0)
    if lo_a <= hi_b and lo_b <= hi_a:
        return f"difference not significant ({ns})"
    if k_a / n_a > k_b / n_b:
        hi, lo = a, b
    else:
        hi, lo = b, a
    return f"{hi} higher than {lo} (intervals do not overlap, {ns})"


def cost_verdict(
    a: str,
    costs_a: Sequence[float],
    b: str,
    costs_b: Sequence[float],
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> str:
    ns = format_n(len(costs_a), len(costs_b))
    if min(len(costs_a), len(costs_b)) < LOW_N:
        return f"insufficient data ({ns})"
    ci = bootstrap_mean_diff_ci(costs_a, costs_b, iterations=iterations, seed=seed)
    if ci is None or ci[0] <= 0 <= ci[1]:
        return f"cost difference not significant ({ns})"
    if statistics.fmean(costs_a) < statistics.fmean(costs_b):
        cheap, other = a, b
    else:
        cheap, other = b, a
    return (
        f"{cheap} cheaper than {other} (bootstrap 95% interval of the mean cost "
        f"difference excludes 0, {ns})"
    )
