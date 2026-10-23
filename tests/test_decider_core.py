from __future__ import annotations

import asyncio
from dataclasses import fields

import pytest

from conftest import COMPLEX_PROMPT
from cora.core.config import TIERS
from cora.core.decider import (
    Choice,
    Decider,
    DecisionHooks,
    DecisionRecord,
    Noul,
    Score,
    accepted,
)
from cora.core.deciders.heuristic import HeuristicDecider
from cora.core.deciders.replay import ReplayDecider, ReplayStep
from test_layering import CORE, FORBIDDEN, _imported_names

TASK = COMPLEX_PROMPT


@pytest.mark.parametrize("cls", [Choice, Score, Noul])
def test_result_types_have_confidence_and_fallback(cls):
    assert {"confidence", "fallback_used", "decider"} <= {f.name for f in fields(cls)}


def test_decision_record_fields_are_exact():
    assert {f.name for f in fields(DecisionRecord)} == {
        "kind",
        "question",
        "input_hash",
        "output",
        "confidence",
        "cost_usd",
        "latency_ms",
        "fallback_used",
        "decider",
        "model",
        "reason",
    }


def test_deciders_satisfy_protocol(mock_config):
    heuristic = HeuristicDecider(mock_config)
    assert isinstance(heuristic, Decider)
    assert isinstance(ReplayDecider(heuristic, {}), Decider)


def test_decider_modules_import_no_ui_or_vendor():
    paths = [CORE / "decider.py", *sorted((CORE / "deciders").glob("*.py"))]
    violations = [
        f"{path}:{lineno} imports {name}"
        for path in paths
        for lineno, name in _imported_names(path)
        if name.startswith(FORBIDDEN)
    ]
    assert not violations, "\n".join(violations)
    text = (CORE / "decider.py").read_text(encoding="utf-8").lower()
    assert not any(word in text for word in ("jev", "openrouter", "typesafe"))


def test_replay_sequence_and_injection(mock_config, no_network, scripted):
    script = {
        "tier": [
            ReplayStep(label="cheap", confidence=0.6),
            ReplayStep(label="strong", confidence=0.9),
            ReplayStep(fail="timeout"),
            ReplayStep(label="strong", confidence=0.2, delay_s=0.05),
        ]
    }
    replay = ReplayDecider(HeuristicDecider(mock_config), script)

    async def run():
        return [await replay.choice("tier", TIERS, text=TASK) for _ in range(5)]

    first, second, third, fourth, fifth = asyncio.run(run())
    assert (first.label, first.confidence, first.fallback_used) == ("cheap", 0.6, False)
    assert (second.label, second.confidence, second.fallback_used) == ("strong", 0.9, False)
    assert third.label == "strong"
    assert third.fallback_used is True
    assert third.reason == "timeout"
    assert fourth.label == "strong"
    assert fourth.confidence == 0.2
    assert fourth.latency_ms >= 40
    assert accepted(fourth, 0.7) is False
    assert fifth.reason == "exhausted"

    replay_noul = ReplayDecider(
        HeuristicDecider(mock_config),
        {
            "group:git": [ReplayStep(p_yes=0.8)],
            "tier": [ReplayStep(label="medium")],
        },
    )
    noul = asyncio.run(replay_noul.noul("group:git", text=TASK))
    assert noul.p_yes == 0.8
    bad = asyncio.run(replay_noul.choice("tier", TIERS, text=TASK))
    assert bad.reason == "schema"
    assert bad.fallback_used is True

    assert scripted.calls == []
    assert replay.calls == [("choice", "tier")] * 5


def test_records_via_hooks(mock_config):
    records: list[DecisionRecord] = []
    decider = HeuristicDecider(mock_config)
    decider.begin_request(DecisionHooks(on_record=records.append))
    asyncio.run(decider.choice("tier", TIERS, text=TASK))
    assert len(records) == 1
    record = records[0]
    assert len(record.input_hash) == 16
    assert TASK not in record.input_hash
    assert TASK not in repr(record.to_event())
