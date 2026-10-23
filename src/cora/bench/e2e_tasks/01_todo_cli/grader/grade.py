"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.getcwd()
SCRATCH = os.path.join(ROOT, ".cora_grader")
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


SCRIPT = os.path.join(ROOT, "todo.py")


def run(cwd, *args):
    proc = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=cwd,
                          capture_output=True, text=True, timeout=10)
    return proc.returncode, proc.stdout.splitlines(), proc.stderr


def fresh():
    os.makedirs(SCRATCH, exist_ok=True)
    return tempfile.mkdtemp(dir=SCRATCH)


@check
def add_and_list():
    d = fresh()
    expect(run(d, "add", "buy milk")[:2], (0, ["added 1: buy milk"]), "add")
    expect(run(d, "list")[:2], (0, ["1 [ ] buy milk"]), "list")


@check
def empty_list():
    expect(run(fresh(), "list")[:2], (0, ["no items"]), "list on empty")


@check
def done_marks_item():
    d = fresh()
    run(d, "add", "a")
    run(d, "add", "b")
    expect(run(d, "done", "2")[:2], (0, ["done 2"]), "done")
    expect(run(d, "list")[1], ["1 [ ] a", "2 [x] b"], "list after done")


@check
def remove_item():
    d = fresh()
    run(d, "add", "a")
    run(d, "add", "b")
    expect(run(d, "remove", "1")[:2], (0, ["removed 1"]), "remove")
    expect(run(d, "list")[1], ["2 [ ] b"], "list after remove")
    expect(run(d, "add", "c")[1], ["added 3: c"], "next id")


@check
def storage_format():
    d = fresh()
    run(d, "add", "x")
    with open(os.path.join(d, "todo.json"), encoding="utf-8") as f:
        data = json.load(f)
    expect(data, [{"id": 1, "text": "x", "done": False}], "todo.json")


@check
def errors_and_usage():
    d = fresh()
    code, _, err = run(d, "done", "9")
    expect((code, "error: no item 9" in err), (1, True), "done on missing id")
    expect(run(d)[0], 2, "exit code without a command")
    expect(run(d, "frobnicate")[0], 2, "exit code for an unknown command")


def main():
    results = []
    for fn in CHECKS:
        try:
            fn()
            results.append({"name": fn.__name__, "passed": True, "detail": ""})
        except AssertionError as e:
            results.append({"name": fn.__name__, "passed": False, "detail": str(e)[:300]})
        except Exception as e:  # noqa: BLE001
            results.append({"name": fn.__name__, "passed": False, "detail": type(e).__name__})
    print(json.dumps({"checks": results}, sort_keys=True))


if __name__ == "__main__":
    main()
