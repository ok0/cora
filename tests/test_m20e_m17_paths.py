from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
M17_FILES = (
    "tests/test_m17_off_identity.py",
    "tests/test_m17b_keys.py",
    "tests/test_m17_agent.py",
)

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(sys.prefix == sys.base_prefix, reason="requires a venv interpreter"),
]


def _long_python(base: Path, min_len: int) -> Path:
    name = Path(sys.executable).name
    pad = max(1, min_len - len(str(base / "p" / "venv" / "bin" / name)) + 1)
    link = base / ("p" * pad) / "venv"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(sys.prefix, target_is_directory=True)
    py = link / "bin" / name
    assert len(str(py)) >= min_len
    return py


@pytest.mark.parametrize("min_len", [0, 87, 171])
def test_m17_files_pass_at_interpreter_length(tmp_path, min_len):
    py = Path(sys.executable) if min_len == 0 else _long_python(tmp_path, min_len)
    probe = subprocess.run(
        [str(py), "-c", "import sys; print(sys.executable)"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert len(probe.stdout.strip()) >= min_len
    r = subprocess.run(
        [str(py), "-m", "pytest", "-q", "-p", "no:cacheprovider", *M17_FILES],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert r.returncode == 0, r.stdout[-3000:]
