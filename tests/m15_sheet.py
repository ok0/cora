from __future__ import annotations

import shlex
from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    id: str
    stage: str  # "smoke" | "probe" | "arm"
    arm: str  # "A" | "B" | "C"
    tier: str  # "cheap" | "strong"
    argv: tuple[str, ...]  # tokens after "cora"
    max_cost: float
    estimate_usd: float


def render(e: Entry) -> str:
    return "uv run cora " + shlex.join(e.argv)


CHEAP = "google/gemini-2.5-flash-lite"
STRONG = "deepseek/deepseek-v3.2"
MULTI = (
    "query_client_timeout",
    "query_total_backoff",
    "query_env_override",
    "multi_edit_delay_cap",
    "multi_edit_rename_cents",
    "multi_edit_region",
)
E2E = (
    "e2e_todo_cli",
    "e2e_text_stats",
    "e2e_rest_notes",
    "e2e_md_to_html",
    "e2e_refactor_inventory",
)
STRONG_E2E_TASK_COST = 0.10
MULTI_TASK_COST = 0.05


def _e(
    eid: str,
    stage: str,
    arm: str,
    tier: str,
    model: str,
    rest: tuple[str, ...],
    max_cost: float,
    estimate_usd: float,
) -> Entry:
    argv = (
        "bench",
        "--live",
        "--protocols",
        "react",
        "--models",
        model,
        *rest,
        "--max-cost",
        f"{max_cost:.2f}",
        "--out",
        f".cora/bench/m15/{eid}",
    )
    return Entry(eid, stage, arm, tier, argv, max_cost, estimate_usd)


_E2E_ARG = ",".join(E2E)
_MULTI_ARG = ",".join(MULTI)
_MULTI_RUN = ("--repeats", "3", "--max-task-cost", f"{MULTI_TASK_COST:.2f}")
_E2E_RUN = ("--suite", "e2e", "--repeats", "3")
_SENSOR = ("--sensor", "--sensor-source", "auto")
_STRONG_E2E_COST = ("--e2e-task-cost", f"{STRONG_E2E_TASK_COST:.2f}")

ENTRIES: tuple[Entry, ...] = (
    _e(
        "s1-smoke-strong",
        "smoke",
        "C",
        "strong",
        STRONG,
        ("--tasks", "fix_off_by_one"),
        0.30,
        0.030000,
    ),
    _e(
        "p1-probe-cheap",
        "probe",
        "A",
        "cheap",
        CHEAP,
        ("--suite", "e2e", "--tasks", _E2E_ARG, "--repeats", "1"),
        0.30,
        0.190000,
    ),
    _e(
        "p2-probe-strong",
        "probe",
        "C",
        "strong",
        STRONG,
        ("--suite", "e2e", "--tasks", _E2E_ARG, "--repeats", "1", *_STRONG_E2E_COST),
        0.50,
        0.496403,
    ),
    _e("A-multi", "arm", "A", "cheap", CHEAP, ("--tasks", _MULTI_ARG, *_MULTI_RUN), 0.50, 0.434074),
    _e(
        "A-e2e-1",
        "arm",
        "A",
        "cheap",
        CHEAP,
        (*_E2E_RUN, "--tasks", "e2e_todo_cli,e2e_text_stats,e2e_rest_notes,e2e_md_to_html"),
        0.50,
        0.420000,
    ),
    _e(
        "A-e2e-2",
        "arm",
        "A",
        "cheap",
        CHEAP,
        (*_E2E_RUN, "--tasks", "e2e_refactor_inventory"),
        0.30,
        0.150000,
    ),
    _e(
        "B-multi",
        "arm",
        "B",
        "cheap",
        CHEAP,
        ("--tasks", _MULTI_ARG, *_MULTI_RUN, *_SENSOR),
        0.50,
        0.434074,
    ),
    _e(
        "B-e2e-1",
        "arm",
        "B",
        "cheap",
        CHEAP,
        (
            *_E2E_RUN,
            "--tasks",
            "e2e_todo_cli,e2e_text_stats,e2e_rest_notes,e2e_md_to_html",
            *_SENSOR,
        ),
        0.50,
        0.420000,
    ),
    _e(
        "B-e2e-2",
        "arm",
        "B",
        "cheap",
        CHEAP,
        (*_E2E_RUN, "--tasks", "e2e_refactor_inventory", *_SENSOR),
        0.30,
        0.150000,
    ),
    _e(
        "C-multi-1",
        "arm",
        "C",
        "strong",
        STRONG,
        ("--tasks", "query_client_timeout,query_total_backoff,query_env_override", *_MULTI_RUN),
        0.50,
        0.450000,
    ),
    _e(
        "C-multi-2",
        "arm",
        "C",
        "strong",
        STRONG,
        ("--tasks", "multi_edit_delay_cap,multi_edit_rename_cents,multi_edit_region", *_MULTI_RUN),
        0.50,
        0.450000,
    ),
    _e(
        "C-e2e-1",
        "arm",
        "C",
        "strong",
        STRONG,
        (*_E2E_RUN, "--tasks", "e2e_todo_cli", *_STRONG_E2E_COST),
        0.30,
        0.294605,
    ),
    _e(
        "C-e2e-2",
        "arm",
        "C",
        "strong",
        STRONG,
        (*_E2E_RUN, "--tasks", "e2e_text_stats", *_STRONG_E2E_COST),
        0.30,
        0.294605,
    ),
    _e(
        "C-e2e-3",
        "arm",
        "C",
        "strong",
        STRONG,
        (*_E2E_RUN, "--tasks", "e2e_rest_notes", *_STRONG_E2E_COST),
        0.30,
        0.300000,
    ),
    _e(
        "C-e2e-4",
        "arm",
        "C",
        "strong",
        STRONG,
        (*_E2E_RUN, "--tasks", "e2e_md_to_html", *_STRONG_E2E_COST),
        0.30,
        0.300000,
    ),
    _e(
        "C-e2e-5",
        "arm",
        "C",
        "strong",
        STRONG,
        (*_E2E_RUN, "--tasks", "e2e_refactor_inventory", *_STRONG_E2E_COST),
        0.30,
        0.300000,
    ),
)
