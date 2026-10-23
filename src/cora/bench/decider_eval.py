from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cora.bench.live import (
    HARD_MAX_COST_USD,
    Budget,
    _abort_guidance,
    _CallTracker,
    _preflight,
    _TrackedPool,
    bench_clock,
)
from cora.core.config import TIERS, CoraConfig
from cora.core.decider import DecisionHooks, DecisionRecord, accepted
from cora.core.deciders import HeuristicDecider, LLMDecider, ReplayDecider, ReplayStep
from cora.core.errors import ConfigError
from cora.core.metering import CostMeter, estimate_cost
from cora.core.providers import ProviderPool
from cora.core.router import PROMPT_FEATURE_KEYS, HeuristicRouter, prompt_features

EVAL_DECIDERS = ("heuristic", "replay", "llm")
DEFAULT_EVAL_MAX_COST_USD = 0.05
DEFAULT_TASK_TOKENS = (20000, 2000)
REPLAY_KEYS = frozenset({"label", "confidence", "fail", "cost_usd"})
TOKEN_KEYS = frozenset({"input", "output"})


@dataclass(frozen=True)
class EvalCase:
    id: str
    expected: str
    text: str
    features: dict
    input_tokens: int
    output_tokens: int
    replay: ReplayStep | None


class _BadLine(ValueError):
    pass


def _is_count(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _valid_features(f: Any) -> bool:
    if not isinstance(f, dict) or not set(f) <= set(PROMPT_FEATURE_KEYS):
        return False
    for key, value in f.items():
        if PROMPT_FEATURE_KEYS[key] is int:
            if not _is_count(value):
                return False
        elif not isinstance(value, bool):
            return False
    return True


def _valid_tokens(t: Any) -> bool:
    if not isinstance(t, dict) or not set(t) <= TOKEN_KEYS:
        return False
    return all(_is_count(v) for v in t.values())


def _parse_case(line: str, lineno: int) -> EvalCase:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError as e:
        raise _BadLine("invalid JSON") from e
    if not isinstance(raw, dict):
        raise _BadLine("each line must be a JSON object")
    expected = raw.get("expected")
    if expected not in TIERS:
        raise _BadLine(f"'expected' must be one of {list(TIERS)}")
    if "prompt" in raw and not isinstance(raw["prompt"], str):
        raise _BadLine("'prompt' must be a string")
    if "features" in raw and not _valid_features(raw["features"]):
        raise _BadLine("invalid 'features'")
    if "prompt" not in raw and "features" not in raw:
        raise _BadLine("needs 'features' or 'prompt'")
    tokens = raw.get("tokens", {})
    if not _valid_tokens(tokens):
        raise _BadLine("invalid 'tokens'")
    replay: ReplayStep | None = None
    if "replay" in raw:
        rp = raw["replay"]
        if not isinstance(rp, dict) or not set(rp) <= REPLAY_KEYS:
            raise _BadLine("invalid 'replay'")
        try:
            replay = ReplayStep(
                label=rp.get("label"),
                confidence=float(rp.get("confidence", 1.0)),
                fail=rp.get("fail"),
                cost_usd=float(rp.get("cost_usd", 0.0)),
            )
        except (TypeError, ValueError) as e:
            raise _BadLine("invalid 'replay'") from e
    prompt = raw.get("prompt")
    features = dict(raw["features"]) if "features" in raw else prompt_features(prompt)
    return EvalCase(
        id=str(raw.get("id", f"line{lineno}")),
        expected=expected,
        text=prompt or "",
        features=features,
        input_tokens=tokens.get("input", DEFAULT_TASK_TOKENS[0]),
        output_tokens=tokens.get("output", DEFAULT_TASK_TOKENS[1]),
        replay=replay,
    )


def load_cases(path: Path) -> list[EvalCase]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        raise ConfigError(f"cannot read cases file {path}: {e}") from e
    cases: list[EvalCase] = []
    for lineno, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            cases.append(_parse_case(line, lineno))
        except _BadLine as e:
            raise ConfigError(f"{path}:{lineno}: {e}") from e
    if not cases:
        raise ConfigError(f"{path}: no cases")
    return cases


@dataclass
class EvalReport:
    decider: str
    model: str | None
    cases: int
    agree: int
    confusion: dict[str, int]
    fallbacks: int
    low_confidence: int
    decision_cost_usd: float
    model_cost_usd: float
    expected_label_cost_usd: float
    unpriced: int
    rows: list[dict] = field(default_factory=list)
    aborted: str | None = None
    abort_guidance: str | None = None

    @property
    def agreement(self) -> float:
        return self.agree / self.cases

    @property
    def total_cost_usd(self) -> float:
        return self.decision_cost_usd + self.model_cost_usd


def _label_cost(router: HeuristicRouter, label: str, case: EvalCase) -> tuple[float, bool]:
    spec = router.resolve(label)
    if spec is None or not spec.price_known:
        return 0.0, True
    return estimate_cost(spec, case.input_tokens, case.output_tokens), False


async def run_decider_eval(
    config: CoraConfig,
    cases: list[EvalCase],
    kind: str,
    *,
    providers: Any = None,
    account: Mapping[str, Any] | None = None,
    max_cost_usd: float = DEFAULT_EVAL_MAX_COST_USD,
    on_notice=None,
    clock=bench_clock,
) -> EvalReport:
    if kind not in EVAL_DECIDERS:
        raise ConfigError(f"unknown decider '{kind}'; expected one of {list(EVAL_DECIDERS)}")
    heuristic = HeuristicDecider(config)
    records: list[DecisionRecord] = []
    meter = CostMeter()
    gate = None
    tracker: _CallTracker | None = None
    llm: LLMDecider | None = None
    decider: HeuristicDecider | ReplayDecider | LLMDecider
    if kind == "replay":
        decider = ReplayDecider(
            heuristic, {"tier": [c.replay or ReplayStep(fail="no_replay") for c in cases]}
        )
    elif kind == "llm":
        if not 0 < max_cost_usd <= HARD_MAX_COST_USD:
            raise ConfigError(
                f"--max-cost {max_cost_usd} must be > 0 and <= {HARD_MAX_COST_USD}"
            )
        pool = providers if providers is not None else ProviderPool(config)
        tracker = _CallTracker(clock)
        llm = LLMDecider(config, _TrackedPool(pool, tracker), heuristic=heuristic)
        await _preflight(pool, [llm.spec], account, max_cost_usd, on_notice)
        gate = Budget(max_cost_usd, max_cost_usd).gate
        decider = llm
    else:
        decider = heuristic
    decider.begin_request(
        DecisionHooks(meter=meter, call_gate=gate, on_record=records.append)
    )

    threshold = config.decider.min_confidence
    confusion = {f"{a}->{b}": 0 for a in TIERS for b in TIERS}
    rows: list[dict] = []
    agree = fallbacks = low_confidence = unpriced = 0
    model_cost = expected_cost = 0.0
    for c in cases:
        res = await decider.choice("tier", TIERS, text=c.text, features=c.features)
        base = (
            res
            if kind == "heuristic"
            else await heuristic.choice("tier", TIERS, text=c.text, features=c.features)
        )
        ok = accepted(res, threshold)
        pred = res.label if ok else base.label
        if res.fallback_used:
            fallbacks += 1
        elif res.confidence < threshold:
            low_confidence += 1
        if pred == c.expected:
            agree += 1
        confusion[f"{c.expected}->{pred}"] += 1
        cost, missing = _label_cost(heuristic.router, pred, c)
        model_cost += cost
        unpriced += int(missing)
        cost, missing = _label_cost(heuristic.router, c.expected, c)
        expected_cost += cost
        unpriced += int(missing)
        rows.append(
            {
                "id": c.id,
                "expected": c.expected,
                "predicted": pred,
                "decider_label": res.label,
                "confidence": res.confidence,
                "fallback_used": res.fallback_used,
                "reason": res.reason,
            }
        )

    return EvalReport(
        decider=kind,
        model=llm.spec.id if llm is not None else None,
        cases=len(cases),
        agree=agree,
        confusion=confusion,
        fallbacks=fallbacks,
        low_confidence=low_confidence,
        decision_cost_usd=sum(r.cost_usd for r in records),
        model_cost_usd=model_cost,
        expected_label_cost_usd=expected_cost,
        unpriced=unpriced,
        rows=rows,
        aborted=tracker.abort_reason if tracker is not None else None,
        abort_guidance=_abort_guidance(tracker) if tracker is not None else None,
    )


def format_eval(r: EvalReport) -> str:
    c = r.confusion
    lines = [
        f"decider eval: decider={r.decider} model={r.model or '-'} cases={r.cases}",
        f"agreement: {r.agree}/{r.cases} ({r.agreement * 100:.1f}%)",
        "confusion (expected->predicted): "
        f"cheap->cheap={c['cheap->cheap']} cheap->strong={c['cheap->strong']} "
        f"strong->cheap={c['strong->cheap']} strong->strong={c['strong->strong']}",
        f"misroutes: cheap->strong={c['cheap->strong']} strong->cheap={c['strong->cheap']}",
        f"fallbacks: {r.fallbacks} low_confidence: {r.low_confidence}",
        f"decision_cost_usd: {r.decision_cost_usd:.6f}",
        f"expected_model_cost_usd: {r.model_cost_usd:.6f} "
        f"(expected labels: {r.expected_label_cost_usd:.6f})",
        f"expected_total_cost_usd: {r.total_cost_usd:.6f}",
    ]
    if r.unpriced > 0:
        lines.append(f"unpriced_models: {r.unpriced} (counted as $0)")
    if r.aborted:
        lines.append(f"aborted: {r.aborted}")
    return "\n".join(lines)


def eval_json(r: EvalReport) -> str:
    payload = {**asdict(r), "agreement": r.agreement, "total_cost_usd": r.total_cost_usd}
    payload.pop("abort_guidance", None)
    return json.dumps(payload, indent=2, ensure_ascii=False)
