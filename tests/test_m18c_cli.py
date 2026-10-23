from __future__ import annotations

import pytest
from typer.testing import CliRunner

from conftest import ScriptedProvider
from cora.cli.main import app


@pytest.mark.parametrize(
    "args, needle",
    [
        (["bench", "--verify-attempts", "3"], "requires --live --suite e2e"),
        (["bench", "--live", "--verify-attempts", "3"], "requires --suite e2e"),
        (
            [
                "bench",
                "--live",
                "--suite",
                "e2e",
                "--sensor",
                "--sensor-source",
                "auto",
                "--verify-attempts",
                "3",
            ],
            "mutually exclusive",
        ),
        (["bench", "--live", "--suite", "e2e", "--verify-attempts", "1"], "from 2 to 5"),
        (["bench", "--live", "--suite", "e2e", "--verify-attempts", "6"], "from 2 to 5"),
        (["bench", "--live", "--suite", "e2e", "--verify-attempts", "x"], "--verify-attempts"),
    ],
)
def test_verify_attempts_misuse_exit_2(args, needle):
    r = CliRunner().invoke(app, args)
    assert r.exit_code == 2
    assert needle in r.output
    assert "Traceback" not in r.output
    assert ScriptedProvider.calls == []
