"""Helpers for record/replay tests (not a test module).

IGNORED lists the A3 fields that legitimately differ between a record run and its replay:
wall_s (top level and budget.used), session_id, profile[].p50_latency_s, and the
'+replay' suffix on profile[].cost_source.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

IGNORED = (
    "wall_s",
    "session_id",
    "budget.used.wall_s",
    "profile[].p50_latency_s",
    "profile[].cost_source '+replay' suffix",
)


def comparable(d: dict) -> dict:
    out = copy.deepcopy(d)
    out.pop("wall_s", None)
    out.pop("session_id", None)
    budget = out.get("budget")
    if isinstance(budget, dict) and isinstance(budget.get("used"), dict):
        budget["used"].pop("wall_s", None)
    for entry in out.get("profile", []):
        entry.pop("p50_latency_s", None)
        entry["cost_source"] = entry["cost_source"].replace("+replay", "")
    return out


def seed_ws(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "hello.txt").write_text("hello\n", encoding="utf-8")
    return path


def record_env(monkeypatch: pytest.MonkeyPatch, mode: str, d: Path) -> None:
    monkeypatch.setenv("CORA_RECORD_MODE", mode)
    monkeypatch.setenv("CORA_RECORD_DIR", str(d))


def entries(d: Path) -> list[Path]:
    return sorted(d.glob("??/*.json"))
