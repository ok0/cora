from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from cora.core.errors import ConfigError

PYTEST_CHECK = "{python} -B -m pytest -q -p no:cacheprovider"

_RNG = """def inclusive_range(a, b):
    \"\"\"Return [a, a+1, ..., b] (b included).\"\"\"
    return list(range(a, b))
"""

_TEST_RNG = """from rng import inclusive_range


def test_inclusive_range():
    assert inclusive_range(1, 3) == [1, 2, 3]
    assert inclusive_range(5, 5) == [5]
"""

_COUNTER = """def count_words(text, counts={}):
    for word in text.split():
        counts[word] = counts.get(word, 0) + 1
    return counts
"""

_TEST_COUNTER = """from counter import count_words


def test_count_words_is_independent():
    assert count_words("a b a") == {"a": 2, "b": 1}
    assert count_words("c") == {"c": 1}
"""

_PEOPLE = """def oldest_first(people):
    \"\"\"people: list of (name, age). Sort by age descending, ties by name ascending.\"\"\"
    return sorted(people, key=lambda p: (p[1], p[0]))
"""

_TEST_PEOPLE = """from people import oldest_first


def test_oldest_first():
    people = [("bob", 30), ("amy", 30), ("cid", 40)]
    assert oldest_first(people) == [("cid", 40), ("amy", 30), ("bob", 30)]
"""

_TEXT_TOOLS = """def is_palindrome(s: str) -> bool:
    \"\"\"True if s reads the same backwards, ignoring case and non-alphanumeric characters.\"\"\"
    raise NotImplementedError
"""

_TEST_TEXT_TOOLS = """from text_tools import is_palindrome


def test_is_palindrome():
    assert is_palindrome("A man, a plan, a canal: Panama")
    assert not is_palindrome("race a car")
    assert is_palindrome("")
"""

_FB = """def fizzbuzz(n: int) -> list[str]:
    \"\"\"Return FizzBuzz strings for 1..n: "Fizz" for multiples of 3, "Buzz" for multiples
    of 5, "FizzBuzz" for multiples of both, otherwise the number itself.\"\"\"
    raise NotImplementedError
"""

_TEST_FB = """from fb import fizzbuzz


def test_fizzbuzz():
    assert fizzbuzz(5) == ["1", "2", "Fizz", "4", "Buzz"]
    assert fizzbuzz(15)[-1] == "FizzBuzz"
    assert fizzbuzz(0) == []
"""

_KV = """def parse_kv(text: str) -> dict[str, str]:
    \"\"\"Parse lines of the form "key = value" into a dict.

    Skip blank lines and lines whose first non-space character is "#".
    Strip whitespace around keys and values. Split on the first "=" only.
    \"\"\"
    raise NotImplementedError
"""

_TEST_KV = r"""from kv import parse_kv


def test_parse_kv():
    text = "a = 1\n  # comment\n\n b=two \nurl = x=y\n"
    assert parse_kv(text) == {"a": "1", "b": "two", "url": "x=y"}
"""

_SHOP_CART = """def calc_total(prices):
    return sum(prices)
"""

_SHOP_CHECKOUT = """from shop.cart import calc_total


def checkout(prices):
    return round(calc_total(prices) * 1.1, 2)
"""

_CHECK_RENAME = """import pathlib

import shop.cart as cart
from shop.checkout import checkout

assert hasattr(cart, "compute_total"), "compute_total missing"
assert not hasattr(cart, "calc_total"), "old name still present"
assert cart.compute_total([1, 2]) == 3
assert checkout([10, 20]) == 33.0
src = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path("shop").glob("*.py"))
assert "calc_total" not in src, "old name still referenced"
print("ok")
"""

_TAX = """def with_tax(amount):
    return round(amount * 1.08, 2)


def tax_only(amount):
    return round(amount * 0.08, 2)
"""

_CHECK_TAX = """import ast

import tax

assert tax.TAX_RATE == 0.08
assert tax.with_tax(100) == 108.0
assert tax.tax_only(50) == 4.0
tree = ast.parse(open("tax.py", encoding="utf-8").read())
for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
    for node in ast.walk(fn):
        if isinstance(node, ast.Constant) and node.value in (1.08, 0.08):
            raise SystemExit(f"literal {node.value} still used in {fn.name}")
print("ok")
"""

_SETTINGS = """DEBUG = False
PORT = 8731
HOST = "127.0.0.1"
"""

_APP_MAIN = """from config.settings import HOST, PORT


def address():
    return f"{HOST}:{PORT}"
"""

_README = """# demo
A tiny demo app.
"""

_TODO_A = """x = 1  # TODO: rename


def f():
    pass  # TODO remove
"""

_TODO_B = """# TODO: docs
VALUE = 2
"""

_LIB_A = """def load(path):
    return open(path).read()
"""

_LIB_B = """def parse(text):
    if not text:
        raise ValueError("empty input")
    return text.split()
"""

_LIB_C = """def save(path, data):
    raise NotImplementedError
"""


@dataclass(frozen=True)
class LiveTask:
    id: str
    kind: str  # bugfix | implement | refactor | explore
    prompt: str
    files: dict[str, str]
    check: str | None = None  # shell command; "{python}" placeholder
    check_files: dict[str, str] = field(default_factory=dict)  # written right before check
    answer_regex: str | None = None
    estimated_minutes: float | None = None

    @property
    def difficulty(self) -> str | None:
        return difficulty_bin(self.estimated_minutes)


DIFFICULTY_THRESHOLDS = (2.0, 10.0)


def difficulty_bin(minutes: float | None) -> str | None:
    if minutes is None:
        return None
    if minutes <= DIFFICULTY_THRESHOLDS[0]:
        return "easy"
    if minutes <= DIFFICULTY_THRESHOLDS[1]:
        return "medium"
    return "hard"


LIVE_TASKS: tuple[LiveTask, ...] = (
    LiveTask(
        id="fix_off_by_one",
        kind="bugfix",
        prompt=(
            "test_rng.py fails. Fix the bug in rng.py so that `python -m pytest -q` passes. "
            "Do not modify the tests."
        ),
        files={"rng.py": _RNG, "test_rng.py": _TEST_RNG},
        check=PYTEST_CHECK + " test_rng.py",
        check_files={"test_rng.py": _TEST_RNG},
    ),
    LiveTask(
        id="fix_mutable_default",
        kind="bugfix",
        prompt=(
            "test_counter.py fails. Fix the bug in counter.py so that `python -m pytest -q` "
            "passes. Do not modify the tests."
        ),
        files={"counter.py": _COUNTER, "test_counter.py": _TEST_COUNTER},
        check=PYTEST_CHECK + " test_counter.py",
        check_files={"test_counter.py": _TEST_COUNTER},
    ),
    LiveTask(
        id="fix_sort_order",
        kind="bugfix",
        prompt=(
            "test_people.py fails. Fix oldest_first in people.py so that `python -m pytest -q` "
            "passes. Do not modify the tests."
        ),
        files={"people.py": _PEOPLE, "test_people.py": _TEST_PEOPLE},
        check=PYTEST_CHECK + " test_people.py",
        check_files={"test_people.py": _TEST_PEOPLE},
    ),
    LiveTask(
        id="implement_is_palindrome",
        kind="implement",
        prompt=(
            "Implement is_palindrome in text_tools.py as described in its docstring so that "
            "`python -m pytest -q` passes."
        ),
        files={"text_tools.py": _TEXT_TOOLS, "test_text_tools.py": _TEST_TEXT_TOOLS},
        check=PYTEST_CHECK + " test_text_tools.py",
        check_files={"test_text_tools.py": _TEST_TEXT_TOOLS},
    ),
    LiveTask(
        id="implement_fizzbuzz",
        kind="implement",
        prompt=(
            "Implement fizzbuzz in fb.py as described in its docstring so that "
            "`python -m pytest -q` passes."
        ),
        files={"fb.py": _FB, "test_fb.py": _TEST_FB},
        check=PYTEST_CHECK + " test_fb.py",
        check_files={"test_fb.py": _TEST_FB},
    ),
    LiveTask(
        id="implement_parse_kv",
        kind="implement",
        prompt=(
            "Implement parse_kv in kv.py as described in its docstring so that "
            "`python -m pytest -q` passes."
        ),
        files={"kv.py": _KV, "test_kv.py": _TEST_KV},
        check=PYTEST_CHECK + " test_kv.py",
        check_files={"test_kv.py": _TEST_KV},
    ),
    LiveTask(
        id="refactor_rename",
        kind="refactor",
        prompt=(
            "Rename the function calc_total in shop/cart.py to compute_total and update every "
            "usage in the shop package. Behaviour must not change and the old name must not "
            "remain anywhere (no alias)."
        ),
        files={
            "shop/__init__.py": "",
            "shop/cart.py": _SHOP_CART,
            "shop/checkout.py": _SHOP_CHECKOUT,
        },
        check="{python} -B check_rename.py",
        check_files={"check_rename.py": _CHECK_RENAME},
    ),
    LiveTask(
        id="refactor_extract_constant",
        kind="refactor",
        prompt=(
            "In tax.py, introduce a module-level constant TAX_RATE = 0.08 and use it in both "
            "functions instead of the literals 1.08 and 0.08. Behaviour must not change."
        ),
        files={"tax.py": _TAX},
        check="{python} -B check_tax.py",
        check_files={"check_tax.py": _CHECK_TAX},
    ),
    LiveTask(
        id="explore_find_port",
        kind="explore",
        prompt=(
            "Which TCP port number is the app in this directory configured to use? "
            "Answer with just the number."
        ),
        files={
            "config/settings.py": _SETTINGS,
            "app/main.py": _APP_MAIN,
            "README.md": _README,
        },
        answer_regex=r"\b8731\b",
    ),
    LiveTask(
        id="explore_count_todos",
        kind="explore",
        prompt=(
            "How many lines containing the text TODO are there across all .py files in this "
            "directory tree (other file types do not count)? Answer with just the number."
        ),
        files={
            "a.py": _TODO_A,
            "pkg/b.py": _TODO_B,
            "pkg/notes.md": "TODO: not python",
            "c.txt": "TODO: not python either",
        },
        answer_regex=r"^\D*\b3\b\D*$",
    ),
    LiveTask(
        id="explore_find_raiser",
        kind="explore",
        prompt=(
            'Which function raises ValueError("empty input")? Answer with just the function name.'
        ),
        files={"lib/a.py": _LIB_A, "lib/b.py": _LIB_B, "lib/c.py": _LIB_C},
        answer_regex=r"\bparse\b",
    ),
)


_SVC_README = "# svc\nSmall service client. Code is in svc/.\n"

_SVC_CONFIG = """import os

DEFAULTS = {"retries": 3, "timeout_s": 20, "region": "eu-west"}


def get(name):
    value = os.environ.get("SVC_" + name.upper())
    if value is not None:
        return value
    return DEFAULTS[name]
"""

_SVC_CLIENT = """from svc import config
from svc.backoff import delays


class Client:
    def __init__(self, timeout_s=None):
        self.timeout_s = timeout_s or config.get("timeout_s") * 2
        self.retries = config.get("retries")

    def schedule(self):
        return delays(self.retries)
"""

_SVC_BACKOFF = """BASE_MS = 150


def delays(retries):
    return [BASE_MS * 2 ** i for i in range(retries)]
"""

_SVC_CLI = """from svc.client import Client


def main():
    c = Client(timeout_s=None)
    print(c.timeout_s, c.schedule())
"""

_SVC_UNITS = """def to_cents(amount):
    return int(round(amount * 100))
"""

_SVC_PRICING = """from svc.units import to_cents


def total_cents(prices):
    return sum(to_cents(p) for p in prices)
"""

_SVC_INVOICE = """from svc import units


def line(name, amount):
    return f"{name}: {units.to_cents(amount)}"
"""

_SVC_FILES: dict[str, str] = {
    "README.md": _SVC_README,
    "svc/__init__.py": "",
    "svc/config.py": _SVC_CONFIG,
    "svc/client.py": _SVC_CLIENT,
    "svc/backoff.py": _SVC_BACKOFF,
    "svc/cli.py": _SVC_CLI,
    "svc/units.py": _SVC_UNITS,
    "svc/pricing.py": _SVC_PRICING,
    "svc/invoice.py": _SVC_INVOICE,
}

_CHECK_DELAY_CAP = """import os

os.environ.pop("SVC_RETRIES", None)
os.environ.pop("SVC_MAX_DELAY_MS", None)
from svc.backoff import delays
from svc.client import Client
from svc.config import DEFAULTS

assert DEFAULTS["max_delay_ms"] == 500
assert delays(4, 500) == [150, 300, 500, 500]
assert delays(2, 1000) == [150, 300]
assert Client().schedule() == [150, 300, 500]
print("ok")
"""

_CHECK_RENAME_CENTS = """import pathlib

from svc import units
from svc.invoice import line
from svc.pricing import total_cents

assert hasattr(units, "as_cents")
assert not hasattr(units, "to_cents")
assert total_cents([1.10, 2.20]) == 330
assert line("a", 1.5) == "a: 150"
src = "".join(p.read_text(encoding="utf-8") for p in pathlib.Path("svc").glob("*.py"))
assert "to_cents" not in src, "old name still referenced"
print("ok")
"""

_CHECK_REGION = """import contextlib
import io
import os

os.environ.pop("SVC_REGION", None)
os.environ.pop("SVC_RETRIES", None)
from svc import cli
from svc.client import Client

assert Client().endpoint() == "https://eu-west.svc.example/v1"
assert Client(region="us-east").endpoint() == "https://us-east.svc.example/v1"
os.environ["SVC_REGION"] = "sa-east"
assert Client().endpoint() == "https://sa-east.svc.example/v1"
del os.environ["SVC_REGION"]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    cli.main(["--region", "ap-south"])
assert buf.getvalue() == "https://ap-south.svc.example/v1\\n", buf.getvalue()
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    cli.main([])
assert buf.getvalue() == "https://eu-west.svc.example/v1\\n", buf.getvalue()
assert Client().schedule() == [150, 300, 600]
print("ok")
"""

_ENV_OVERRIDE_ANSWER = (
    r"""^[\s`*'"]*(?:answer:\s*)?(?:(?:it\s+)?raises\s+(?:an?\s+)?)?"""
    r"""[`*'"]*TypeError[`*'"]*(?::[^\n]*)?[ \t.!`*'"]*(?:\n[ \t]*\n(?s:.*))?\s*$"""
)

MULTI_TASKS: tuple[LiveTask, ...] = (
    LiveTask(
        id="query_client_timeout",
        kind="query",
        prompt=(
            "In this repository, what timeout in seconds does a Client created with no "
            "arguments end up using? Answer with just the number."
        ),
        files=dict(_SVC_FILES),
        answer_regex=r"^\D*\b40(\.0)?\b\D*$",
        estimated_minutes=2,
    ),
    LiveTask(
        id="query_total_backoff",
        kind="query",
        prompt=(
            "With default settings and no SVC_* environment variables set, what is the total "
            "of all retry delays, in milliseconds, returned by Client().schedule()? Answer "
            "with just the number."
        ),
        files=dict(_SVC_FILES),
        answer_regex=r"^\D*\b1,?050(\.0)?\b\D*$",
        estimated_minutes=5,
    ),
    LiveTask(
        id="query_env_override",
        kind="query",
        prompt=(
            'Suppose the environment variable SVC_RETRIES is set to 5 (as the string "5", like '
            "every environment variable). What happens when Client().schedule() is called? If "
            "it returns a list, answer with the number of delays; if it raises, answer with "
            "just the exception class name."
        ),
        files=dict(_SVC_FILES),
        answer_regex=_ENV_OVERRIDE_ANSWER,
        estimated_minutes=12,
    ),
    LiveTask(
        id="multi_edit_delay_cap",
        kind="multi_edit",
        prompt=(
            "Add a cap on retry delays in the svc package: add \"max_delay_ms\": 500 to "
            "DEFAULTS in svc/config.py; change delays in svc/backoff.py to delays(retries, "
            "max_ms) so every delay is at most max_ms; make Client.schedule() in svc/client.py "
            'pass config.get("max_delay_ms"). Behaviour must otherwise stay the same.'
        ),
        files=dict(_SVC_FILES),
        check="{python} -B check_delay_cap.py",
        check_files={"check_delay_cap.py": _CHECK_DELAY_CAP},
        estimated_minutes=6,
    ),
    LiveTask(
        id="multi_edit_rename_cents",
        kind="multi_edit",
        prompt=(
            "Rename the function to_cents in svc/units.py to as_cents and update every usage "
            "in the svc package (some modules import the function, others use the module "
            "attribute). Behaviour must not change and the old name must not remain anywhere "
            "(no alias)."
        ),
        files=dict(_SVC_FILES),
        check="{python} -B check_rename_cents.py",
        check_files={"check_rename_cents.py": _CHECK_RENAME_CENTS},
        estimated_minutes=6,
    ),
    LiveTask(
        id="multi_edit_region",
        kind="multi_edit",
        prompt=(
            "Add region support to the svc package: (1) Client(timeout_s=None, region=None): "
            'when region is None use config.get("region"), read when the Client is created; '
            "(2) add Client.endpoint() returning \"https://<region>.svc.example/v1\"; (3) change "
            'svc/cli.py so main(argv=None) accepts an optional "--region <name>" argument '
            "(argv defaults to sys.argv[1:]) and prints only the endpoint of a Client built with "
            "that region. Keep timeouts and schedule() unchanged."
        ),
        files=dict(_SVC_FILES),
        check="{python} -B check_region.py",
        check_files={"check_region.py": _CHECK_REGION},
        estimated_minutes=15,
    ),
)

ALL_TASK_IDS: tuple[str, ...] = tuple(t.id for t in (*LIVE_TASKS, *MULTI_TASKS))


def select_tasks(
    ids: Sequence[str] | None, default: tuple[LiveTask, ...] = LIVE_TASKS
) -> tuple[LiveTask, ...]:
    if not ids:
        return default
    by_id = {t.id: t for t in (*LIVE_TASKS, *MULTI_TASKS)}
    selected: list[LiveTask] = []
    for x in ids:
        if x not in by_id:
            raise ConfigError(f"unknown bench task id '{x}'; known: {list(ALL_TASK_IDS)}")
        selected.append(by_id[x])
    return tuple(selected)


def write_task_files(root: Path, files: Mapping[str, str]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
