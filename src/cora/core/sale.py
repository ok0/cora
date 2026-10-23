from __future__ import annotations

import math
import re
import tomllib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

from cora.core.config import SaleSettings
from cora.core.errors import ConfigError

SALE_TIERS_FILE = "sale_tiers.toml"
BUILTIN_TIERS_LABEL = "built-in sale_tiers.toml"
DEFAULT_UNIT = "arbitrary cost units"
PLACEHOLDER_WARNING = (
    "WARNING: SYNTHETIC / PLACEHOLDER tier table, 실측 아님 (not measured). "
    "Replace cost and solve_rate with your live bench results."
)
W_STEPS = 0.05
W_FILES = 0.1
W_RISK = 0.25
W_UNCERTAINTY = 0.25
SIZE_PER_STEP = 0.05
FAIL_SLOPE = 1.5
TIE_DIGITS = 9
PLAN_KEYS = ("steps", "files", "tool_risk", "uncertainty")
TABLE_KEYS = frozenset({"placeholder", "unit", "tiers"})
TIER_KEYS = frozenset({"name", "cost", "solve_rate"})
FILE_REF = re.compile(r"[\w./-]+\.(?:py|ts|js|go|rs|java|toml|json|ya?ml|md|txt|cfg|ini|sh)\b")
RISKY = re.compile(
    r"\b(?:edit|write|delete|remove|rm|run|execute|install|migrate|deploy|push|overwrite"
    r"|rename|move)\b"
    r"|(?:수정|삭제|실행|설치|이동)",
    re.I,
)
VAGUE = re.compile(
    r"\b(?:maybe|probably|might|unclear|unknown|investigate|explore|somehow|possibly"
    r"|guess|tbd)\b"
    r"|\?|(?:아마|불확실|모름|조사)",
    re.I,
)
ESC_RUNNING, ESC_PASSED, ESC_FAILED = "running", "passed", "failed"


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


@dataclass(frozen=True)
class PlanFeatures:
    steps: int
    files: int
    tool_risk: float = 0.0
    uncertainty: float = 0.0

    def __post_init__(self) -> None:
        for name in ("steps", "files"):
            v = getattr(self, name)
            if not (_is_int(v) and v >= 0):
                raise ValueError(f"{name} must be an integer >= 0")
        for name in ("tool_risk", "uncertainty"):
            v = getattr(self, name)
            if not (_is_num(v) and 0 <= v <= 1):
                raise ValueError(f"{name} must be a number from 0 to 1")
            object.__setattr__(self, name, float(v))

    @classmethod
    def from_mapping(cls, raw: Any) -> PlanFeatures:
        if not isinstance(raw, dict):
            raise ValueError("must be an object")
        missing = set(PLAN_KEYS) - set(raw)
        if missing:
            raise ValueError(f"missing keys {sorted(missing)}")
        unknown = set(raw) - set(PLAN_KEYS)
        if unknown:
            raise ValueError(f"unknown keys {sorted(unknown)}")
        return cls(raw["steps"], raw["files"], raw["tool_risk"], raw["uncertainty"])


def plan_features_from_text(text: str) -> PlanFeatures:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    steps = len(lines)
    files = len({m.group(0) for m in FILE_REF.finditer(text)})
    if steps == 0:
        return PlanFeatures(0, files, 0.0, 0.0)
    risky = sum(1 for ln in lines if RISKY.search(ln))
    vague = sum(1 for ln in lines if VAGUE.search(ln))
    return PlanFeatures(steps, files, risky / steps, vague / steps)


@dataclass(frozen=True)
class SaleTier:
    name: str
    cost: float
    solve_rate: float


@dataclass(frozen=True)
class TierTable:
    tiers: tuple[SaleTier, ...]
    placeholder: bool = True
    unit: str = DEFAULT_UNIT
    source: str = ""

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(t.name for t in self.tiers)


def parse_tier_table(data: Mapping[str, Any], source: str) -> TierTable:
    def fail(msg: str) -> ConfigError:
        return ConfigError(f"{source}: {msg}")

    unknown = sorted(set(data) - TABLE_KEYS)
    if unknown:
        raise fail(f"unknown keys {unknown}")
    placeholder = data.get("placeholder", True)
    if not isinstance(placeholder, bool):
        raise fail("'placeholder' must be true or false")
    unit = data.get("unit", DEFAULT_UNIT)
    if not isinstance(unit, str) or not unit:
        raise fail("'unit' must be a non-empty string")
    raw = data.get("tiers")
    if not isinstance(raw, list) or len(raw) < 2:
        raise fail("needs at least two [[tiers]] entries")
    tiers: list[SaleTier] = []
    for i, t in enumerate(raw, 1):
        if not isinstance(t, dict) or set(t) != TIER_KEYS:
            raise fail(f"tiers[{i}] needs exactly 'name', 'cost' and 'solve_rate'")
        if not isinstance(t["name"], str) or not t["name"]:
            raise fail(f"tiers[{i}].name must be a non-empty string")
        if not _is_num(t["cost"]) or t["cost"] <= 0:
            raise fail(f"tiers[{i}].cost must be a number > 0")
        if not _is_num(t["solve_rate"]) or not 0 <= t["solve_rate"] <= 1:
            raise fail(f"tiers[{i}].solve_rate must be a number from 0 to 1")
        tiers.append(SaleTier(t["name"], float(t["cost"]), float(t["solve_rate"])))
    names = [t.name for t in tiers]
    if len(set(names)) != len(names):
        raise fail("tier names must be unique")
    if any(tiers[i + 1].cost <= tiers[i].cost for i in range(len(tiers) - 1)):
        raise fail("tiers must be listed from cheapest to strongest (cost strictly increasing)")
    return TierTable(tuple(tiers), placeholder, unit, source)


def builtin_tiers_path() -> Path:
    return Path(str(resources.files("cora") / "data" / SALE_TIERS_FILE))


def load_tier_table(path: Path | None = None) -> TierTable:
    target = builtin_tiers_path() if path is None else path
    source = BUILTIN_TIERS_LABEL if path is None else str(path)
    try:
        with target.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"tier table not found: {source}") from e
    except OSError as e:
        raise ConfigError(f"cannot read tier table {source}: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid tier table {source}: {e}") from e
    return parse_tier_table(data, source)


@dataclass(frozen=True)
class Bid:
    tier: str
    index: int
    estimated_cost: float
    expected_success: float
    value: float
    difficulty: float
    size: float


def difficulty(f: PlanFeatures) -> float:
    raw = (
        W_STEPS * f.steps + W_FILES * f.files + W_RISK * f.tool_risk + W_UNCERTAINTY * f.uncertainty
    )
    return min(1.0, raw)


def plan_size(f: PlanFeatures) -> float:
    return 1.0 + SIZE_PER_STEP * f.steps


def make_bid(tier: SaleTier, index: int, f: PlanFeatures, reward: float) -> Bid:
    d = difficulty(f)
    size = plan_size(f)
    cost = tier.cost * size
    success = min(1.0, max(0.0, tier.solve_rate - FAIL_SLOPE * d * (1.0 - tier.solve_rate)))
    return Bid(tier.name, index, cost, success, success * reward - cost, d, size)


class BidGenerator(Protocol):
    kind: str

    def bids(
        self, task: str, table: TierTable, features: PlanFeatures | None = None
    ) -> tuple[Bid, ...]: ...


class HeuristicBidGenerator:
    kind = "heuristic"

    def __init__(self, reward: float) -> None:
        self.reward = reward

    def bids(
        self, task: str, table: TierTable, features: PlanFeatures | None = None
    ) -> tuple[Bid, ...]:
        f = features if features is not None else plan_features_from_text(task)
        return tuple(make_bid(t, i, f, self.reward) for i, t in enumerate(table.tiers))


Planner = Callable[[str, SaleTier], str]


class LLMBidGenerator:
    kind = "llm"

    def __init__(self, planner: Planner, reward: float) -> None:
        self.planner = planner
        self.reward = reward

    def bids(
        self, task: str, table: TierTable, features: PlanFeatures | None = None
    ) -> tuple[Bid, ...]:
        return tuple(
            make_bid(
                t,
                i,
                plan_features_from_text(self.planner(task, t)),
                self.reward,
            )
            for i, t in enumerate(table.tiers)
        )


class ReplayPlanner:
    def __init__(self, plans: Mapping[str, str]) -> None:
        self.plans = dict(plans)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, task: str, tier: SaleTier) -> str:
        self.calls.append((task, tier.name))
        return self.plans.get(tier.name, "")


def make_bid_generator(settings: SaleSettings, planner: Planner | None = None) -> BidGenerator:
    if settings.enabled and settings.bids == "llm":
        if planner is None:
            raise ConfigError(
                '[sale] bids = "llm" needs a planner adapter; none is connected in this version'
            )
        return LLMBidGenerator(planner, settings.reward)
    return HeuristicBidGenerator(settings.reward)


@dataclass(frozen=True)
class SaleDecision:
    tier: str
    bid: Bid
    bids: tuple[Bid, ...]
    over_budget: bool
    reason: str


def choose_tier(bids: Sequence[Bid], budget_cap: float) -> SaleDecision:
    all_bids = tuple(bids)
    if not all_bids:
        raise ValueError("no bids")
    feasible = [b for b in all_bids if b.estimated_cost <= budget_cap]
    if feasible:
        best = max(
            feasible,
            key=lambda b: (
                round(b.value, TIE_DIGITS),
                -round(b.estimated_cost, TIE_DIGITS),
                -b.index,
            ),
        )
        return SaleDecision(best.tier, best, all_bids, False, "max_value")
    cheapest = min(all_bids, key=lambda b: (b.estimated_cost, b.index))
    return SaleDecision(cheapest.tier, cheapest, all_bids, True, "all_over_budget")


@dataclass(frozen=True)
class Escalation:
    tiers: tuple[str, ...]
    projected: tuple[float, ...]
    max_escalations: int
    budget_cap: float
    index: int
    escalations: int = 0
    spent: float = 0.0
    status: str = ESC_RUNNING
    reason: str = ""
    attempts: tuple[str, ...] = ()

    @property
    def tier(self) -> str:
        return self.tiers[self.index]


def start_escalation(
    bids: Sequence[Bid], start_tier: str, *, max_escalations: int, budget_cap: float
) -> Escalation:
    ordered = tuple(sorted(bids, key=lambda b: b.index))
    names = tuple(b.tier for b in ordered)
    if start_tier not in names:
        raise ValueError(f"unknown tier {start_tier!r}")
    if max_escalations < 0:
        raise ValueError("max_escalations must be >= 0")
    return Escalation(
        names,
        tuple(b.estimated_cost for b in ordered),
        max_escalations,
        budget_cap,
        names.index(start_tier),
    )


def record_attempt(state: Escalation, *, passed: bool, cost: float | None = None) -> Escalation:
    if state.status != ESC_RUNNING:
        raise ValueError("escalation already finished")
    spent = state.spent + (state.projected[state.index] if cost is None else cost)
    attempts = state.attempts + (state.tier,)
    if passed:
        return replace(
            state, spent=spent, attempts=attempts, status=ESC_PASSED, reason="sensor_passed"
        )
    nxt = state.index + 1
    if nxt >= len(state.tiers):
        reason = "top_tier_failed"
    elif state.escalations >= state.max_escalations:
        reason = "max_escalations"
    elif spent + state.projected[nxt] > state.budget_cap:
        reason = "budget_cap"
    else:
        return replace(
            state,
            index=nxt,
            escalations=state.escalations + 1,
            spent=spent,
            attempts=attempts,
            reason="escalated",
        )
    return replace(state, spent=spent, attempts=attempts, status=ESC_FAILED, reason=reason)


def run_escalation(state: Escalation, sensor_results: Iterable[bool]) -> Escalation:
    for passed in sensor_results:
        if state.status != ESC_RUNNING:
            break
        state = record_attempt(state, passed=passed)
    return state
