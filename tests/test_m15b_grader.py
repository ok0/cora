from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import m15_baseline as B
from cora.bench import live
from cora.bench.live_tasks import MULTI_TASKS

pytestmark = pytest.mark.usefixtures("no_network")

TASK = {t.id: t for t in MULTI_TASKS}["query_env_override"]
CC_R1_REPLY = (
    "**TypeError**\n\n`config.get(\"retries\")` returns the string `\"5\"` from the environment "
    "without converting it. `delays(\"5\")` then calls `range(\"5\")`, which raises `TypeError`."
)


def _chk(tmp_path: Path, answer: str) -> bool:
    return asyncio.run(live.check_task(TASK, tmp_path, answer, frozenset()))[0]


def test_env_override_passes(tmp_path: Path) -> None:
    for answer in (
        "TypeError",
        "**TypeError**",
        "TypeError: unsupported operand",
        "It raises a TypeError.",
        CC_R1_REPLY,
    ):
        assert _chk(tmp_path, answer) is True, answer


def test_env_override_fails(tmp_path: Path) -> None:
    for answer in (
        "ValueError",
        "**ValueError**\n\nIt is not a TypeError because ...",
        "3",
        "",
        "TypeError\nbut actually ValueError",
    ):
        assert _chk(tmp_path, answer) is False, answer


def test_shared_check(tmp_path: Path) -> None:
    result = B.grade(
        "query_env_override", tmp_path, "**TypeError**\n\nexplanation", tmp_path
    )
    assert result["solved"] is True
