from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

CAPS = ("cost", "iterations", "wall", "tool_calls")

_CAP_FIELDS = {
    "cost": "cost_usd",
    "iterations": "iterations",
    "wall": "wall_s",
    "tool_calls": "tool_calls",
}


def _clamp_one(own: Any, ceiling: Any) -> Any:
    if ceiling is None:
        return own
    if own is None:
        return ceiling
    return min(own, ceiling)


@dataclass(frozen=True)
class BudgetLimits:
    cost_usd: float | None = None
    iterations: int | None = None
    wall_s: float | None = None
    tool_calls: int | None = None

    @classmethod
    def from_agent(cls, agent: Any) -> BudgetLimits:
        return cls(
            cost_usd=float(agent.max_cost_usd),
            iterations=int(agent.max_iterations),
            wall_s=float(agent.max_wall_s) if agent.max_wall_s > 0 else None,
            tool_calls=int(agent.max_tool_calls) if agent.max_tool_calls > 0 else None,
        )

    def clamp(self, ceiling: BudgetLimits) -> BudgetLimits:
        return BudgetLimits(
            cost_usd=_clamp_one(self.cost_usd, ceiling.cost_usd),
            iterations=_clamp_one(self.iterations, ceiling.iterations),
            wall_s=_clamp_one(self.wall_s, ceiling.wall_s),
            tool_calls=_clamp_one(self.tool_calls, ceiling.tool_calls),
        )

    def to_dict(self) -> dict:
        return {
            "cost_usd": self.cost_usd,
            "iterations": self.iterations,
            "wall_s": self.wall_s,
            "tool_calls": self.tool_calls,
        }


@dataclass
class BudgetUsage:
    cost_usd: float = 0.0
    iterations: int = 0
    wall_s: float = 0.0
    tool_calls: int = 0

    def to_dict(self) -> dict:
        return {
            "cost_usd": self.cost_usd,
            "iterations": self.iterations,
            "wall_s": round(self.wall_s, 3),
            "tool_calls": self.tool_calls,
        }


def projected_call_cost(spec: Any, input_tokens: int, max_output_tokens: int) -> float:
    if getattr(spec, "free_tier", False):
        return 0.0
    if getattr(spec, "cost_model", "catalog") == "self_hosted":
        return 0.0
    if not getattr(spec, "price_known", False):
        return 0.0
    return (
        input_tokens * spec.input_usd_per_mtok / 1e6
        + max_output_tokens * spec.output_usd_per_mtok / 1e6
    )


class BudgetGovernor:
    def __init__(
        self,
        limits: BudgetLimits,
        *,
        warn_fraction: float = 0.8,
        clock: Callable[[], float] = time.monotonic,
        on_warn: Callable[[str, float, float], None] | None = None,
        seed: BudgetUsage | None = None,
        project_cost: bool = True,
    ) -> None:
        if (
            isinstance(warn_fraction, bool)
            or not isinstance(warn_fraction, (int, float))
            or not 0 < warn_fraction <= 1
        ):
            raise ValueError("warn_fraction must be > 0 and <= 1")
        self.limits = limits
        self.warn_fraction = warn_fraction
        self.project_cost = project_cost
        self.on_warn = on_warn
        self._clock = clock
        self.begin(seed)

    def begin(self, seed: BudgetUsage | None = None) -> None:
        s = seed if seed is not None else BudgetUsage()
        self._cost = s.cost_usd
        self._iterations = s.iterations
        self._tool_calls = s.tool_calls
        self._wall_seed = s.wall_s
        self._t0 = self._clock()
        self._attempt_base = 0
        self.tripped: str | None = None
        self._warned: list[str] = []
        self._pending: list[tuple[str, float, float]] = []
        self.tool_counts: dict[str, int] = {}

    def _elapsed(self) -> float:
        return self._wall_seed + max(0.0, self._clock() - self._t0)

    def _observe(self, cap: str, value: float) -> None:
        limit = getattr(self.limits, _CAP_FIELDS[cap])
        if limit is None or limit <= 0 or cap in self._warned:
            return
        if value >= self.warn_fraction * limit:
            self._warned.append(cap)
            self._pending.append((cap, value, limit))
            if self.on_warn is not None:
                self.on_warn(cap, value, limit)

    def _trip(self, cap: str) -> str:
        if self.tripped is None:
            self.tripped = cap
        return self.tripped

    def _check_wall(self) -> str | None:
        w = self._elapsed()
        self._observe("wall", w)
        if self.limits.wall_s is not None and w >= self.limits.wall_s:
            return self._trip("wall")
        return None

    def add_cost(self, usd: float) -> None:
        self._cost += usd
        self._observe("cost", self._cost)

    def add_iteration(self) -> None:
        self._iterations += 1
        self._observe("iterations", self._iterations - self._attempt_base)

    def new_attempt(self) -> None:
        self._attempt_base = self._iterations

    def add_tool_calls(self, n: int = 1, *, name: str | None = None) -> None:
        self._tool_calls += n
        if name:
            self.tool_counts[name] = self.tool_counts.get(name, 0) + n
        self._observe("tool_calls", self._tool_calls)

    def check_model_call(
        self, projected_cost_usd: float = 0.0, *, iterations: bool = True
    ) -> str | None:
        if self.tripped is not None:
            return self.tripped
        if (
            iterations
            and self.limits.iterations is not None
            and self._iterations - self._attempt_base >= self.limits.iterations
        ):
            return self._trip("iterations")
        wall = self._check_wall()
        if wall is not None:
            return wall
        if self.limits.cost_usd is not None:
            if self._cost >= self.limits.cost_usd:
                return self._trip("cost")
            if (
                self.project_cost
                and projected_cost_usd > 0
                and self._cost + projected_cost_usd > self.limits.cost_usd
            ):
                return self._trip("cost")
        return None

    def check_tool_call(self) -> str | None:
        if self.tripped is not None:
            return self.tripped
        if self.limits.tool_calls is not None and self._tool_calls >= self.limits.tool_calls:
            return self._trip("tool_calls")
        return self._check_wall()

    def drain_warnings(self) -> list[tuple[str, float, float]]:
        out = list(self._pending)
        self._pending.clear()
        return out

    @property
    def warned(self) -> frozenset[str]:
        return frozenset(self._warned)

    def usage(self) -> BudgetUsage:
        return BudgetUsage(self._cost, self._iterations, self._elapsed(), self._tool_calls)

    def to_dict(self) -> dict:
        return {
            "limits": self.limits.to_dict(),
            "used": self.usage().to_dict(),
            "tripped": self.tripped,
            "warned": bool(self._warned),
        }
