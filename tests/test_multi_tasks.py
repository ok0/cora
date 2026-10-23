from __future__ import annotations

import asyncio

import pytest

from cora.bench.live import check_task
from cora.bench.live_tasks import (
    LIVE_TASKS,
    MULTI_TASKS,
    difficulty_bin,
    select_tasks,
    write_task_files,
)
from cora.core.errors import ConfigError

REFERENCES: dict[str, dict[str, str]] = {
    "multi_edit_delay_cap": {
        "svc/config.py": (
            "import os\n\n"
            "DEFAULTS = {\n"
            '    "retries": 3,\n'
            '    "timeout_s": 20,\n'
            '    "region": "eu-west",\n'
            '    "max_delay_ms": 500,\n'
            "}\n\n\n"
            "def get(name):\n"
            '    value = os.environ.get("SVC_" + name.upper())\n'
            "    if value is not None:\n"
            "        return value\n"
            "    return DEFAULTS[name]\n"
        ),
        "svc/backoff.py": (
            "BASE_MS = 150\n\n\n"
            "def delays(retries, max_ms):\n"
            "    return [min(BASE_MS * 2 ** i, max_ms) for i in range(retries)]\n"
        ),
        "svc/client.py": (
            "from svc import config\n"
            "from svc.backoff import delays\n\n\n"
            "class Client:\n"
            "    def __init__(self, timeout_s=None):\n"
            '        self.timeout_s = timeout_s or config.get("timeout_s") * 2\n'
            '        self.retries = config.get("retries")\n\n'
            "    def schedule(self):\n"
            '        return delays(self.retries, config.get("max_delay_ms"))\n'
        ),
    },
    "multi_edit_rename_cents": {
        "svc/units.py": (
            "def as_cents(amount):\n"
            "    return int(round(amount * 100))\n"
        ),
        "svc/pricing.py": (
            "from svc.units import as_cents\n\n\n"
            "def total_cents(prices):\n"
            "    return sum(as_cents(p) for p in prices)\n"
        ),
        "svc/invoice.py": (
            "from svc import units\n\n\n"
            "def line(name, amount):\n"
            '    return f"{name}: {units.as_cents(amount)}"\n'
        ),
    },
    "multi_edit_region": {
        "svc/client.py": (
            "from svc import config\n"
            "from svc.backoff import delays\n\n\n"
            "class Client:\n"
            "    def __init__(self, timeout_s=None, region=None):\n"
            '        self.timeout_s = timeout_s or config.get("timeout_s") * 2\n'
            '        self.retries = config.get("retries")\n'
            '        self.region = region if region is not None else config.get("region")\n\n'
            "    def endpoint(self):\n"
            '        return f"https://{self.region}.svc.example/v1"\n\n'
            "    def schedule(self):\n"
            "        return delays(self.retries)\n"
        ),
        "svc/cli.py": (
            "import sys\n\n"
            "from svc.client import Client\n\n\n"
            "def main(argv=None):\n"
            "    if argv is None:\n"
            "        argv = sys.argv[1:]\n"
            "    region = None\n"
            '    if "--region" in argv:\n'
            '        region = argv[argv.index("--region") + 1]\n'
            "    print(Client(timeout_s=None, region=region).endpoint())\n"
        ),
    },
}

ANSWERS = {
    "query_client_timeout": (["40", "40.0"], ["", "20"]),
    "query_total_backoff": (["1050", "1,050"], ["", "450"]),
    "query_env_override": (["TypeError"], ["", "5"]),
}


def test_difficulty_bin_thresholds():
    assert difficulty_bin(0.5) == "easy"
    assert difficulty_bin(2) == "easy"
    assert difficulty_bin(2.01) == "medium"
    assert difficulty_bin(10) == "medium"
    assert difficulty_bin(10.01) == "hard"
    assert difficulty_bin(None) is None


def test_multi_tasks_shape():
    assert len(MULTI_TASKS) >= 6
    ids = [t.id for t in MULTI_TASKS]
    assert len(set(ids)) == len(ids)
    assert not set(ids) & {t.id for t in LIVE_TASKS}
    assert sum(t.kind == "query" for t in MULTI_TASKS) >= 3
    assert sum(t.kind == "multi_edit" for t in MULTI_TASKS) >= 3
    for t in MULTI_TASKS:
        assert t.estimated_minutes is not None, t.id
        assert t.difficulty == difficulty_bin(t.estimated_minutes), t.id
        assert sum(name.endswith(".py") for name in t.files) >= 3, t.id
        assert (t.check is None) != (t.answer_regex is None), t.id
        assert sum(len(v) for v in t.files.values()) < 4000, t.id
    bins = [t.difficulty for t in MULTI_TASKS]
    assert bins.count("easy") >= 1
    assert bins.count("medium") >= 2
    assert bins.count("hard") >= 2


def test_multi_task_checks_deterministic(tmp_path):
    by_id = {t.id: t for t in MULTI_TASKS}
    for task_id, refs in REFERENCES.items():
        task = by_id[task_id]
        root = tmp_path / task_id
        write_task_files(root, task.files)
        ok, _ = asyncio.run(check_task(task, root, None, frozenset()))
        assert ok is False, task_id
        write_task_files(root, refs)
        ok, detail = asyncio.run(check_task(task, root, None, frozenset()))
        assert ok is True, (task_id, detail)

    for task_id, (good, bad) in ANSWERS.items():
        task = by_id[task_id]
        root = tmp_path / task_id
        for ans in good:
            ok, _ = asyncio.run(check_task(task, root, ans, frozenset()))
            assert ok is True, (task_id, ans)
        for ans in bad:
            ok, _ = asyncio.run(check_task(task, root, ans, frozenset()))
            assert ok is False, (task_id, ans)


def test_select_tasks_multi():
    assert select_tasks(None) == LIVE_TASKS
    assert select_tasks(None, default=MULTI_TASKS) == MULTI_TASKS
    picked = select_tasks(["query_client_timeout"])
    assert [t.id for t in picked] == ["query_client_timeout"]
    with pytest.raises(ConfigError, match="unknown bench task id"):
        select_tasks(["nope"])


def test_query_env_override_regex_anchored(tmp_path):
    task = next(t for t in MULTI_TASKS if t.id == "query_env_override")
    good = ["TypeError", "`TypeError`", "**TypeError**", "TypeError.", "It raises TypeError",
            "raises a TypeError.", "Answer: TypeError",
            "TypeError: '<' not supported between instances of 'int' and 'str'"]
    bad = ["", "5", "there is no TypeError", "No TypeError", "not TypeError",
           "TypeError is not raised", "It returns 5 delays, no TypeError", "ValueError",
           "TypeError\nActually no, it returns 5"]
    for ans in good:
        assert asyncio.run(check_task(task, tmp_path, ans, frozenset()))[0] is True, ans
    for ans in bad:
        assert asyncio.run(check_task(task, tmp_path, ans, frozenset()))[0] is False, ans
