from __future__ import annotations

from dataclasses import dataclass

PY_CHECK = "{python} -B -m pytest -q -p no:cacheprovider"


@dataclass(frozen=True)
class BenchTask:
    name: str
    prompt: str
    files: dict[str, str]
    check_command: str | None = None
    expect_in_answer: str | None = None


BENCH_TASKS: tuple[BenchTask, ...] = (
    BenchTask(
        "fix_add",
        "test_calc.py fails. Fix the bug in calc.py so that the tests pass.",
        {
            "calc.py": "def add(a, b):\n    return a - b\n",
            "test_calc.py": (
                "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
            ),
        },
        PY_CHECK,
    ),
    BenchTask(
        "implement_slugify",
        "Implement slugify in text_utils.py so that test_text_utils.py passes.",
        {
            "text_utils.py": "def slugify(s: str) -> str:\n    raise NotImplementedError\n",
            "test_text_utils.py": (
                "from text_utils import slugify\n\n\ndef test_slugify():\n"
                "    assert slugify('Hello World!') == 'hello-world'\n"
            ),
        },
        PY_CHECK,
    ),
    BenchTask(
        "explain_code",
        "What string does greet('Bob') in greet.py return? Answer with the exact string.",
        {"greet.py": 'def greet(name):\n    return f"Hello, {name}"\n'},
        None,
        "Hello, Bob",
    ),
)
