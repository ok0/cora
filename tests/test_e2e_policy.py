from __future__ import annotations

import asyncio
import dataclasses
import json
import shutil
from pathlib import Path
from shlex import quote

import pytest

from conftest import act
from cora.bench.e2e import load_e2e_tasks
from cora.bench.live import run_live_bench
from cora.bench.report import report_json, report_markdown
from cora.core import shellguard
from cora.core.config import CoraConfig
from cora.core.observability import read_events
from cora.core.policy import parse_policy
from e2e_util import GRADER_OK, make_task

pytestmark = pytest.mark.slow

GRADER_MARK = "GRADER-SECRET-9a2c"
REFERENCE_MARK = "REFERENCE-SECRET-7d1f"
USER_POLICY = {
    "rules": [
        {"id": "allow-all", "decision": "allow", "tool": "*"},
        {"id": "allow-shell", "decision": "allow",
         "command": ["cat *", "python *", "python3 *"]},
    ]
}


def test_strict_profile_blocks_reference_grader_and_package_data(
    scripted, mock_config: CoraConfig, tmp_path: Path, monkeypatch
) -> None:
    make_task(
        tmp_path / "tasks", "e2e_leak", GRADER_OK + f"# {GRADER_MARK}\n",
        **{"limits.max_iterations": 20, "limits.cost_usd": 0.25},
    )
    task_dir = tmp_path / "tasks" / "e2e_leak"
    (task_dir / "reference" / "README.txt").write_text(
        REFERENCE_MARK + "\n", encoding="utf-8"
    )
    task = load_e2e_tasks(tmp_path / "tasks")[0]
    ref = task.reference_dir / "README.txt"
    grader = task.grader_dir / task.grader_entry

    pkg_root = tmp_path / "site-packages" / "cora" / "data"
    pkg_task = pkg_root / "e2e_leak"
    shutil.copytree(task.reference_dir, pkg_task / "reference")
    shutil.copytree(task.grader_dir, pkg_task / "grader")
    pkg = pkg_task / "reference" / "README.txt"
    real_dirs = shellguard.package_data_dirs()
    monkeypatch.setattr(
        shellguard, "package_data_dirs", lambda: (pkg_root, *real_dirs)
    )

    config = dataclasses.replace(mock_config, policy=parse_policy(USER_POLICY, "test"))
    scripted.script.extend([
        act("run_shell", {"command": f"cat {quote(str(ref))}"}),
        act("run_shell", {"command": f"python -c \"print(open('{ref}').read())\""}),
        act("run_shell", {"command": f"cat $(echo {grader})"}),
        act("read_file", {"path": str(ref)}),
        act("read_file", {"path": str(grader)}),
        act("run_shell", {"command": f"cat {quote(str(pkg))}"}),
        act("list_files", {"path": str(task.root)}),
        "Final Answer: done",
    ])
    report = asyncio.run(
        run_live_bench(
            config,
            models=["mock/cheap"],
            protocols=["react"],
            tasks=[task],
            max_cost_usd=0.30,
            max_task_cost_usd=0.30,
            max_iterations=40,
            state_dir=tmp_path / "state",
        )
    )
    r = report.results[0]
    assert r.policy_denies == 7
    assert r.policy_asks == 0
    assert r.human_interventions == 0
    assert r.policy is not None
    assert [d["rule"] for d in r.policy["decisions"]] == [
        "floor:protected-path",
        "confine:one-liner",
        "confine:substitution",
        "floor:protected-path",
        "floor:protected-path",
        "floor:protected-path",
        "floor:protected-path",
    ]

    for call in scripted.calls:
        for m in call.messages:
            assert GRADER_MARK not in m.content
            assert REFERENCE_MARK not in m.content

    events = []
    for path in (tmp_path / "state").rglob("events.jsonl"):
        events.extend(read_events(path))
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    assert len(tool_calls) == 7
    assert all(e["ok"] is False for e in tool_calls)
    dumped = json.dumps(events)
    assert GRADER_MARK not in dumped
    assert REFERENCE_MARK not in dumped

    obj = json.loads(report_json(report, None))
    assert obj["results"][0]["policy_denies"] == 7
    assert obj["e2e"]["policy_deny_total"] == 7
    assert obj["e2e"]["human_interventions_total"] == 0
    assert "human_interventions" in obj["results"][0]
    assert obj["settings"]["e2e"]["policy_profile"] == "strict"
    assert "policy (strict e2e profile" in report_markdown(report, None)
