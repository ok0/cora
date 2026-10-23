"""Hidden grader. Prints one JSON line {"checks": [...]} on stdout."""

import importlib
import json
import os
import sys

ROOT = os.getcwd()
CHECKS = []
sys.path.insert(0, ROOT)


def check(fn):
    CHECKS.append(fn)
    return fn


def expect(actual, wanted, what):
    assert actual == wanted, f"{what}: expected {wanted!r}, got {actual!r}"


def raises(exc, fn, *args):
    try:
        fn(*args)
    except exc as e:
        return e
    raise AssertionError(f"{exc.__name__} not raised")


def jp(name):
    return importlib.import_module("jobplan." + name)


def example():
    Job = jp("model").Job
    return [
        Job("fetch", 2),
        Job("build", 3, ("fetch",)),
        Job("lint", 1, (), 5),
        Job("test", 4, ("build",), 1),
        Job("docs", 2, ("fetch",)),
    ]


@check
def load_valid():
    load = jp("loader").load_jobs
    Job = jp("model").Job
    expect(load('[{"name": "a", "duration": 2}]'), [Job("a", 2)], "defaults")
    expect(load('[{"name": "b", "duration": 1, "deps": ["a"], "priority": 3}]'),
           [Job("b", 1, ("a",), 3)], "all fields")
    expect(load('[{"name": "a", "duration": 1, "priority": -2}]'),
           [Job("a", 1, (), -2)], "negative priority")
    expect(load("[]"), [], "empty array")


@check
def load_errors():
    load = jp("loader").load_jobs
    JobError = jp("model").JobError
    cases = [
        ("not json", "invalid JSON"),
        ('{"name": "a"}', "expected a JSON array"),
        ('[{"duration": 1}]', "job 1: missing name"),
        ('[{"name": "a", "duration": 1}, {"duration": 1}]', "job 2: missing name"),
        ('[{"name": "a", "duration": 0}]', "job 1: duration must be a positive integer"),
        ('[{"name": "a", "duration": true}]', "job 1: duration must be a positive integer"),
        ('[{"name": "a", "duration": "2"}]', "job 1: duration must be a positive integer"),
        ('[{"name": "a", "duration": 1, "deps": "b"}]', "job 1: deps must be a list of names"),
        ('[{"name": "a", "duration": 1}, {"name": "a", "duration": 2}]', "duplicate job 'a'"),
    ]
    for text, msg in cases:
        e = raises(JobError, load, text)
        expect(str(e), msg, f"error for {text!r}")


@check
def unknown_dep():
    validate = jp("graph").validate
    Job = jp("model").Job
    JobError = jp("model").JobError
    e = raises(JobError, validate, [Job("a", 1, ("b",))])
    expect(str(e), "job 'a' depends on unknown 'b'", "unknown dependency")
    expect(validate(example()), None, "valid graph")


@check
def cycle_message():
    validate = jp("graph").validate
    Job = jp("model").Job
    JobError = jp("model").JobError
    e = raises(JobError, validate, [Job("a", 1, ("b",)), Job("b", 1, ("c",)), Job("c", 1, ("a",))])
    expect(str(e), "cycle: a -> b -> c -> a", "three-job cycle")
    e = raises(JobError, validate, [Job("x", 1, ("x",))])
    expect(str(e), "cycle: x -> x", "self dependency")


@check
def order_priority_ties():
    order = jp("graph").order
    Job = jp("model").Job
    expect(order(example()), ["lint", "fetch", "build", "test", "docs"], "example")
    expect(order([Job("c", 1), Job("b", 1), Job("a", 1)]), ["a", "b", "c"], "name tie")
    expect(order([Job("b", 1), Job("a", 1, (), 2)]), ["a", "b"], "priority first")
    expect(order([]), [], "no jobs")


@check
def simulate_two_workers():
    s = jp("simulate").simulate(example(), 2)
    expect(s.starts, {"lint": 0, "fetch": 0, "build": 2, "docs": 2, "test": 5}, "starts")
    expect(s.ends, {"lint": 1, "fetch": 2, "build": 5, "docs": 4, "test": 9}, "ends")
    expect(s.worker, {"lint": 0, "fetch": 1, "build": 0, "docs": 1, "test": 0}, "worker")
    expect(s.makespan, 9, "makespan")


@check
def simulate_one_worker():
    s = jp("simulate").simulate(example(), 1)
    expect(s.starts, {"lint": 0, "fetch": 1, "build": 3, "test": 6, "docs": 10}, "starts")
    expect(s.ends, {"lint": 1, "fetch": 3, "build": 6, "test": 10, "docs": 12}, "ends")
    expect(s.worker, {"lint": 0, "fetch": 0, "build": 0, "test": 0, "docs": 0}, "worker")
    expect(s.makespan, 12, "makespan")


@check
def simulate_invalid_workers():
    simulate = jp("simulate").simulate
    for w in (0, -1):
        e = raises(ValueError, simulate, example(), w)
        expect(str(e), "workers must be >= 1", f"workers={w}")


@check
def render_format():
    s = jp("simulate").simulate(example(), 2)
    text = jp("report").render(s)
    expect(
        text,
        "   0    1  w0  lint\n"
        "   0    2  w1  fetch\n"
        "   2    5  w0  build\n"
        "   2    4  w1  docs\n"
        "   5    9  w0  test\n"
        "makespan 9\n",
        "render",
    )


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
