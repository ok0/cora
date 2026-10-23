from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime

from cora.core.config import ModelSpec


@dataclass
class CallRecord:
    ts: str
    model: str
    tier: str
    purpose: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    price_known: bool = True
    cost_source: str = "legacy"
    cached_input_tokens: int = 0
    provider: str = "unknown"
    latency_s: float | None = None


_LEGACY_SOURCES = {"provider": "provider_usage", "unknown": "unpriced", "price": "legacy"}
_RECORD_FIELDS = frozenset(f.name for f in fields(CallRecord))


CONSERVATIVE_USD_PER_MTOK = (15.0, 75.0)


def base_cost_source(source: str) -> str:
    return source.removesuffix("+replay")


def estimate_cost(
    spec: ModelSpec,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float:
    if not spec.price_known:
        return 0.0
    cached = (
        min(max(cached_input_tokens, 0), input_tokens)
        if spec.cache_read_usd_per_mtok is not None
        else 0
    )
    cost = (input_tokens - cached) * spec.input_usd_per_mtok / 1e6
    if cached:
        cost += cached * spec.cache_read_usd_per_mtok / 1e6
    return cost + output_tokens * spec.output_usd_per_mtok / 1e6


def projected_cost(spec: ModelSpec, input_tokens: int, max_output_tokens: int) -> float:
    if getattr(spec, "free_tier", False):
        return 0.0
    if getattr(spec, "cost_model", "catalog") == "self_hosted":
        return 0.0
    inp, out = (
        (spec.input_usd_per_mtok, spec.output_usd_per_mtok)
        if spec.price_known
        else CONSERVATIVE_USD_PER_MTOK
    )
    return input_tokens * inp / 1e6 + max_output_tokens * out / 1e6


@dataclass
class DelegationStats:
    explore_calls: int = 0
    general_calls: int = 0
    ok: int = 0
    failed: int = 0
    refused: int = 0
    busy_s: float = 0.0
    wall_s: float = 0.0
    max_fanout: int = 0
    tool_result_tokens: int = 0
    summary_tokens: int = 0
    avoided_tokens_est: int = 0
    attempts: int = 0
    attempts_unparsed: int = 0

    @property
    def invocations(self) -> int:
        return self.explore_calls + self.general_calls

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> DelegationStats:
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in names})

    def merged(self, other: DelegationStats) -> DelegationStats:
        out = DelegationStats()
        for f in fields(self):
            a, b = getattr(self, f.name), getattr(other, f.name)
            setattr(out, f.name, max(a, b) if f.name == "max_fanout" else a + b)
        return out

    def summary_fields(self) -> dict:
        return {"invocations": self.invocations, **self.to_dict()}


class CostMeter:
    def __init__(self, records: list[CallRecord] | None = None) -> None:
        self.records: list[CallRecord] = records if records is not None else []

    def record(
        self,
        spec: ModelSpec,
        tier: str,
        purpose: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float | None = None,
        cached_input_tokens: int = 0,
        latency_s: float | None = None,
        *,
        replayed: bool = False,
    ) -> CallRecord:
        self_hosted = getattr(spec, "cost_model", "catalog") == "self_hosted"
        if getattr(spec, "free_tier", False):
            cost, known, source = 0.0, True, "free_tier"
        elif cost_usd is not None:
            cost, known = float(cost_usd), True
            source = "self_hosted" if self_hosted else "provider_usage"
        elif spec.price_known:
            cost = estimate_cost(spec, input_tokens, output_tokens, cached_input_tokens)
            known = True
            source = "self_hosted" if self_hosted else f"catalog:{spec.id}@{spec.provider}"
        else:
            cost, known = 0.0, False
            source = "self_hosted" if self_hosted else "unpriced"
        if replayed:
            source = source + "+replay"
        rec = CallRecord(
            ts=datetime.now(UTC).isoformat(),
            model=spec.id,
            tier=tier,
            purpose=purpose,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            price_known=known,
            cost_source=source,
            cached_input_tokens=max(int(cached_input_tokens), 0),
            provider=spec.provider,
            latency_s=None if latency_s is None else max(float(latency_s), 0.0),
        )
        self.records.append(rec)
        return rec

    @property
    def total_cost_usd(self) -> float:
        return sum(
            r.cost_usd for r in self.records if base_cost_source(r.cost_source) != "self_hosted"
        )

    @property
    def self_hosted_cost_usd(self) -> float:
        return sum(
            r.cost_usd for r in self.records if base_cost_source(r.cost_source) == "self_hosted"
        )

    def summary(self, delegation: dict | None = None) -> dict:
        by_model: dict[str, dict] = {}
        cached_by_model: dict[str, int] = {}
        for r in self.records:
            m = by_model.setdefault(
                r.model,
                {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                    "price_known": True,
                },
            )
            m["calls"] += 1
            m["input_tokens"] += r.input_tokens
            m["output_tokens"] += r.output_tokens
            m["cost_usd"] += r.cost_usd
            m["price_known"] = m["price_known"] and r.price_known
            cached_by_model[r.model] = cached_by_model.get(r.model, 0) + r.cached_input_tokens
        for model_id, cached in cached_by_model.items():
            if cached > 0:
                by_model[model_id]["cached_input_tokens"] = cached
        deleg = [r for r in self.records if r.purpose == "delegate"]
        groups: dict[str, list[CallRecord]] = {}
        for r in self.records:
            groups.setdefault(f"{r.model}@{r.provider}", []).append(r)
        by_group: dict[str, dict] = {}
        for key, recs in groups.items():
            lats = [r.latency_s for r in recs if r.latency_s is not None]
            by_group[key] = {
                "model": recs[0].model,
                "provider": recs[0].provider,
                "calls": len(recs),
                "input_tokens": sum(r.input_tokens for r in recs),
                "output_tokens": sum(r.output_tokens for r in recs),
                "cached_input_tokens": sum(r.cached_input_tokens for r in recs),
                "cost_usd": sum(r.cost_usd for r in recs),
                "price_known": all(r.price_known for r in recs),
                "cost_source": ",".join(sorted({r.cost_source for r in recs})),
                "latency_calls": len(lats),
                "p50_latency_s": statistics.median(lats) if lats else None,
                "self_hosted": any(base_cost_source(r.cost_source) == "self_hosted" for r in recs),
            }
        sh = [r for r in self.records if base_cost_source(r.cost_source) == "self_hosted"]
        out = {
            "calls": len(self.records),
            "by_model": by_model,
            "by_model_provider": by_group,
            "self_hosted": {
                "calls": len(sh),
                "input_tokens": sum(r.input_tokens for r in sh),
                "output_tokens": sum(r.output_tokens for r in sh),
                "cost_usd": sum(r.cost_usd for r in sh),
                "excluded_from_total": True,
            },
            "total_cost_usd": self.total_cost_usd,
            "unknown_cost_calls": sum(1 for r in self.records if not r.price_known),
            "provider_cost_calls": sum(
                1 for r in self.records
                if base_cost_source(r.cost_source) in ("provider_usage", "provider")
            ),
            "delegated": {
                "calls": len(deleg),
                "input_tokens": sum(r.input_tokens for r in deleg),
                "output_tokens": sum(r.output_tokens for r in deleg),
                "cost_usd": sum(r.cost_usd for r in deleg),
                "price_known": all(r.price_known for r in deleg),
            },
        }
        if delegation:
            stats = DelegationStats.from_dict(delegation)
            if stats.invocations or stats.refused or stats.attempts:
                out["delegated"].update(stats.summary_fields())
        return out

    def to_list(self) -> list[dict]:
        return [asdict(r) for r in self.records]

    @classmethod
    def from_list(cls, data: list[dict]) -> CostMeter:
        recs = []
        for d in data:
            kw = {k: v for k, v in d.items() if k in _RECORD_FIELDS}
            src = kw.get("cost_source", "legacy")
            kw["cost_source"] = _LEGACY_SOURCES.get(src, src)
            recs.append(CallRecord(**kw))
        return cls(recs)


def format_summary(summary: dict) -> str:
    lines = ["== CORA cost summary ==", f"calls: {summary['calls']}"]
    for model_id, m in summary["by_model"].items():
        cost = f"${m['cost_usd']:.6f}" if m.get("price_known", True) else "unknown"
        cached = f" cached={m['cached_input_tokens']}" if "cached_input_tokens" in m else ""
        lines.append(
            f"model {model_id}: calls={m['calls']} in={m['input_tokens']} "
            f"out={m['output_tokens']}{cached} cost={cost}"
        )
    groups = summary.get("by_model_provider") or {}
    ids = [g["model"] for g in groups.values()]
    show = len(ids) != len(set(ids)) or any(
        base_cost_source(g["cost_source"]) != f"catalog:{g['model']}@{g['provider']}"
        for g in groups.values())
    if show:
        for key, g in groups.items():
            cost = f"${g['cost_usd']:.6f}" if g.get("price_known", True) else "unknown"
            p50 = "n/a" if g.get("p50_latency_s") is None else f"{g['p50_latency_s']:.3f}"
            tail = " [self_hosted: excluded from total]" if g.get("self_hosted") else ""
            lines.append(f"profile {key}: calls={g['calls']} in={g['input_tokens']} "
                         f"out={g['output_tokens']} cost={cost} cost_source={g['cost_source']} "
                         f"p50_latency_s={p50}{tail}")
    d = summary.get("delegated")
    if d and d["calls"]:
        cost = f"${d['cost_usd']:.6f}" if d.get("price_known", True) else "unknown"
        lines.append(
            f"delegated (sub-agents): calls={d['calls']} in={d['input_tokens']} "
            f"out={d['output_tokens']} cost={cost}"
        )
    if d and (d.get("invocations") or d.get("refused") or d.get("attempts")):
        lines.append(
            f"delegated detail: invocations={d['invocations']} (explore={d['explore_calls']} "
            f"general={d['general_calls']}) ok={d['ok']} failed={d['failed']} "
            f"refused={d['refused']} attempts={d.get('attempts', 0)} "
            f"attempts_unparsed={d.get('attempts_unparsed', 0)} "
            f"wall_s={d['wall_s']:.2f} busy_s={d['busy_s']:.2f} max_fanout={d['max_fanout']} "
            f"avoided_tokens_est={d['avoided_tokens_est']} (estimate)"
        )
    dec = summary.get("decider")
    if dec:
        lines.append(
            f"decider: decisions={dec['decisions']} fallbacks={dec['fallbacks']} "
            f"cost=${dec['cost_usd']:.6f}"
        )
    pol = summary.get("policy")
    if pol:
        lines.append(f"policy: mode={pol['mode']} allow={pol['allow']} ask={pol['ask']} "
                     f"deny={pol['deny']} (ask resolved as deny: {pol['ask_resolved_deny']}; "
                     f"rules: {pol['source']})")
    lines.append(f"total_estimated_cost_usd: {summary['total_cost_usd']:.6f}")
    sh = summary.get("self_hosted")
    if sh and sh.get("calls"):
        lines.append(f"self_hosted_cost_usd: {sh['cost_usd']:.6f} (calls={sh['calls']}; "
                     "reported separately, excluded from total_estimated_cost_usd "
                     "and baseline comparisons)")
    if summary.get("unknown_cost_calls"):
        lines.append(
            f"unknown_cost_calls: {summary['unknown_cost_calls']} "
            "(models without price; not included in total)"
        )
    return "\n".join(lines)
