from __future__ import annotations

import asyncio

from conftest import act, with_gates_off
from cora.bench.harness import format_table, run_bench


def test_bench_table(scripted, mock_config):
    scripted.script[:] = [
        act("edit_file", {"path": "calc.py", "old": "return a - b", "new": "return a + b"}),
        "Final Answer: fixed",
        act(
            "edit_file",
            {
                "path": "text_utils.py",
                "old": "    raise NotImplementedError\n",
                "new": (
                    "    import re\n"
                    "    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')\n"
                ),
            },
        ),
        "Final Answer: done",
        "Final Answer: Hello, Bob",
    ]
    results = asyncio.run(run_bench(with_gates_off(mock_config), baseline={"fix_add": 0.05}))
    assert all(r.success for r in results)
    table = format_table(results)
    header = "| task | success | stop_reason | iterations | calls | cost_usd | baseline_cost_usd |"
    assert header in table
    assert "| fix_add | yes |" in table
    assert "0.050000" in table
    assert "| TOTAL | 3/3 |" in table
