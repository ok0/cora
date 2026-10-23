from __future__ import annotations

from pathlib import Path

import pytest

from cora.bench import e2e
from cora.bench.e2e import E2ETask, load_e2e_tasks
from e2e_util import CHECK_COUNTS, EXPECTED_PARTIAL_SCORE, materialize

pytestmark = pytest.mark.slow

SAMPLE_IDS = [
    "e2e_todo_cli",
    "e2e_text_stats",
    "e2e_rest_notes",
    "e2e_md_to_html",
    "e2e_refactor_inventory",
]


def _task(tid: str) -> E2ETask:
    return {t.id: t for t in load_e2e_tasks()}[tid]


def _grade(task: E2ETask, variant: str, tmp: Path):
    ws = materialize(task, variant, tmp)
    return e2e.run_grader(task, ws, tmp / "harness")


@pytest.mark.parametrize("tid", SAMPLE_IDS)
def test_reference_full_pass(tid: str, tmp_path: Path) -> None:
    result = _grade(_task(tid), "reference", tmp_path)
    assert result.status == "ok", result.reason
    assert result.full_pass
    assert result.score == 1.0
    assert len(result.checks) == CHECK_COUNTS[tid] >= 4


@pytest.mark.parametrize("tid", SAMPLE_IDS)
def test_template_fails(tid: str, tmp_path: Path) -> None:
    result = _grade(_task(tid), "template", tmp_path)
    assert not result.full_pass
    assert result.score == 0.0


@pytest.mark.parametrize("tid", SAMPLE_IDS)
def test_partial_scores_between_zero_and_one(tid: str, tmp_path: Path) -> None:
    result = _grade(_task(tid), "partial", tmp_path)
    assert result.status == "ok", result.reason
    assert not result.full_pass
    assert result.score == pytest.approx(EXPECTED_PARTIAL_SCORE[tid])
    assert 0 < result.score < 1


@pytest.mark.parametrize("tid", SAMPLE_IDS)
def test_grader_is_deterministic(tid: str, tmp_path: Path) -> None:
    task = _task(tid)
    for variant in ("reference", "partial"):
        runs = []
        for i in range(3):
            result = _grade(task, variant, tmp_path / f"{variant}{i}")
            runs.append([(c["name"], c["passed"], c["detail"]) for c in result.checks])
        assert runs[0] == runs[1] == runs[2]
