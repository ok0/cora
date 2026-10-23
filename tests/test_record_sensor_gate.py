from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cora.core.observability import read_events
from cora.core.outcome import exit_code
from record_util import record_env
from test_headless import base, doc, events, run_cli

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "recordings"
SENSOR_KINDS = ("check", "check_skipped", "stop")
CASES = sorted(FIXTURES.glob("sensor_gate_*/case.json"))


def sensor_events(evts: list[dict]) -> list[list]:
    return [[e["type"], e.get("ok")] for e in evts if e["type"] in SENSOR_KINDS]


def _load(case: Path) -> tuple[dict, dict]:
    spec = json.loads(case.read_text(encoding="utf-8"))
    expected = json.loads((case.parent / "expected.json").read_text(encoding="utf-8"))
    return spec, expected


if not CASES:

    def test_sensor_gate_replay():
        pytest.skip("no sensor_gate recording yet (M11 live step)")

else:

    @pytest.mark.parametrize("case", CASES, ids=lambda p: p.parent.name)
    def test_sensor_gate_replay(case, no_network, tmp_path, monkeypatch):
        stale = case.parent / "STALE"
        if stale.exists():
            pytest.skip(f"stale recording: {stale.read_text(encoding='utf-8').strip()}")
        spec, expected = _load(case)
        ws = tmp_path / "ws"
        for rel, content in spec["files"].items():
            target = ws / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        record_env(monkeypatch, "replay", case.parent / "entries")
        result = run_cli(
            [
                "run",
                spec["task"],
                "--headless",
                "--json",
                "--check",
                spec["check"],
                *base(ws, case.parent / "cora.toml"),
            ]
        )
        d = doc(result)
        assert d["stop_reason"] == expected["stop_reason"]
        assert d["final_answer"] == expected["final_answer"]
        assert d["iterations"] == expected["iterations"]
        assert sensor_events(events(ws, d["session_id"])) == expected["sensor_events"]
        assert result.exit_code == exit_code(d["stop_reason"])


def capture(fixture: Path, outcome_path: Path, events_path: Path) -> None:
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    expected = {
        "stop_reason": outcome["stop_reason"],
        "final_answer": outcome["final_answer"],
        "iterations": outcome["iterations"],
        "sensor_events": sensor_events(read_events(events_path)),
    }
    (fixture / "expected.json").write_text(
        json.dumps(expected, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "capture":
        capture(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    else:
        raise SystemExit(
            "usage: test_record_sensor_gate.py capture <fixture_dir> <outcome.json> <events.jsonl>"
        )
