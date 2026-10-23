"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import ast
import dataclasses
import importlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.getcwd()
SCRATCH = os.path.join(ROOT, ".cora_grader")
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


def _tmp():
    os.makedirs(SCRATCH, exist_ok=True)
    return tempfile.mkdtemp(dir=SCRATCH)


def _cli(db, *args):
    return subprocess.run([sys.executable, "-B", "-m", "tracker", "--db", db, *args],
                          cwd=ROOT, capture_output=True, text=True, timeout=30)


def _raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        return e
    raise AssertionError(f"no exception from {fn.__name__}")


@check
def existing_behaviour_kept():
    svc = importlib.import_module("tracker.service")
    path = os.path.join(_tmp(), "t.jsonl")
    t = svc.Tracker(path)
    a = t.add("write")
    b = t.add("test")
    expect((a.id, b.id), (1, 2), "ids")
    t.complete(2)
    expect([(x.id, x.title, x.done) for x in t.list()],
           [(1, "write", False), (2, "test", True)], "list")
    e = _raises(t.complete, 9)
    expect(type(e).__name__, "KeyError", "complete unknown id")
    proc = _cli(path, "done", "9")
    expect(proc.returncode, 1, "done unknown exit status")
    expect(proc.stderr.strip(), "error: no task 9", "done unknown stderr")
    proc = _cli(path, "add", "fresh")
    expect(proc.stdout.strip(), "added 3", "cli add")
    proc = _cli(path, "done", "1")
    expect(proc.stdout.strip(), "done 1", "cli done")


@check
def model_default_and_validation():
    models = importlib.import_module("tracker.models")
    expect([f.name for f in dataclasses.fields(models.Task)],
           ["id", "title", "done", "priority"], "fields")
    t = models.Task(1, "a")
    expect(t.priority, "normal", "default priority")
    expect(t.done, False, "default done")
    for p in ("low", "normal", "high"):
        expect(models.Task(1, "a", priority=p).priority, p, f"priority {p}")
    e = _raises(models.Task, 1, "a", priority="urgent")
    expect(type(e).__name__, "ValueError", "invalid priority type")
    expect(str(e), "invalid priority: urgent", "invalid priority message")


@check
def storage_roundtrip():
    models = importlib.import_module("tracker.models")
    storage = importlib.import_module("tracker.storage")
    path = os.path.join(_tmp(), "s.jsonl")
    expect(storage.load(path), [], "missing file")
    tasks = [models.Task(1, "a"), models.Task(2, "b", True, "high"),
             models.Task(3, "c", priority="low")]
    storage.save(path, tasks)
    expect(storage.load(path), tasks, "roundtrip")


@check
def storage_backward_compat():
    storage = importlib.import_module("tracker.storage")
    path = os.path.join(_tmp(), "old.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"id": 1, "title": "old", "done": False}) + "\n")
    tasks = storage.load(path)
    expect([(t.id, t.title, t.done, t.priority) for t in tasks],
           [(1, "old", False, "normal")], "legacy record")


@check
def service_sort_priority():
    svc = importlib.import_module("tracker.service")
    path = os.path.join(_tmp(), "p.jsonl")
    t = svc.Tracker(path)
    t.add("low one", priority="low")
    t.add("normal one")
    t.add("high one", priority="high")
    t.add("high two", priority="high")
    expect([x.id for x in t.list()], [1, 2, 3, 4], "default order")
    expect([x.id for x in t.list(sort="id")], [1, 2, 3, 4], "sort id")
    expect([x.id for x in t.list(sort="priority")], [3, 4, 2, 1], "sort priority")
    e = _raises(t.list, sort="title")
    expect(type(e).__name__, "ValueError", "unknown sort")


@check
def service_add_invalid():
    svc = importlib.import_module("tracker.service")
    path = os.path.join(_tmp(), "i.jsonl")
    t = svc.Tracker(path)
    t.add("first")
    e = _raises(t.add, "bad", priority="urgent")
    expect(type(e).__name__, "ValueError", "invalid add type")
    expect(str(e), "invalid priority: urgent", "invalid add message")
    expect([x.title for x in t.list()], ["first"], "nothing saved on error")


@check
def formatting_marker():
    fmt = importlib.import_module("tracker.formatting")
    models = importlib.import_module("tracker.models")
    text = fmt.render([models.Task(1, "a"), models.Task(12, "b", True, "high"),
                       models.Task(3, "c", priority="low")])
    expect(text, "  1 [N] [ ] a\n 12 [H] [x] b\n  3 [L] [ ] c", "render")
    expect(fmt.render([]), "", "render empty")


@check
def cli_add_and_list():
    path = os.path.join(_tmp(), "c.jsonl")
    proc = _cli(path, "add", "write docs", "--priority", "high")
    expect(proc.returncode, 0, "add high exit")
    expect(proc.stdout.strip(), "added 1", "add high stdout")
    proc = _cli(path, "add", "fix bug", "--priority", "low")
    expect(proc.stdout.strip(), "added 2", "add low stdout")
    proc = _cli(path, "add", "plain")
    expect(proc.stdout.strip(), "added 3", "add default stdout")
    proc = _cli(path, "add", "bad", "--priority", "urgent")
    expect(proc.returncode, 2, "invalid priority exit status")
    proc = _cli(path, "list", "--sort", "priority")
    expect(proc.returncode, 0, "list priority exit")
    expect(proc.stdout.splitlines(),
           ["  1 [H] [ ] write docs", "  3 [N] [ ] plain", "  2 [L] [ ] fix bug"],
           "list sorted by priority")
    proc = _cli(path, "list")
    expect(proc.stdout.splitlines(),
           ["  1 [H] [ ] write docs", "  2 [L] [ ] fix bug", "  3 [N] [ ] plain"],
           "list by id")


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
