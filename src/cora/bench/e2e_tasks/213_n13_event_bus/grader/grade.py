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


@check
def topic_validation():
    t = importlib.import_module("evbus.topics")
    for good in ["a", "orders", "a.b_1", "x9.y0.z"]:
        t.validate_topic(good)
    for bad in ["", "a..b", ".a", "a.", "A.b", "a-b", "a b", "a.*"]:
        e = raises(ValueError, t.validate_topic, bad)
        expect(str(e), f"bad topic '{bad}'", f"topic message for {bad!r}")
    for good in ["a.*", "#", "a.*.#", "a.b"]:
        t.validate_pattern(good)
    for bad in ["", "a..b", "A.b", "a.#.b", "a.**"]:
        e = raises(ValueError, t.validate_pattern, bad)
        expect(str(e), f"bad pattern '{bad}'", f"pattern message for {bad!r}")


@check
def wildcard_star():
    m = importlib.import_module("evbus.topics")
    expect(m.matches("a.*", "a.b"), True, "a.* vs a.b")
    expect(m.matches("a.*", "a"), False, "a.* vs a")
    expect(m.matches("a.*", "a.b.c"), False, "a.* vs a.b.c")
    expect(m.matches("a.*.c", "a.b.c"), True, "middle star")
    expect(m.matches("*", "x"), True, "star alone")
    expect(m.matches("*", "x.y"), False, "star alone, two segments")
    expect(m.matches("a.b", "a.b"), True, "exact")
    expect(m.matches("a.b", "a.c"), False, "exact mismatch")


@check
def wildcard_hash():
    m = importlib.import_module("evbus.topics")
    for topic in ["orders", "orders.a", "orders.a.b"]:
        expect(m.matches("orders.#", topic), True, f"orders.# vs {topic}")
    expect(m.matches("orders.#", "order"), False, "orders.# vs order")
    expect(m.matches("#", "a.b.c"), True, "hash alone, deep")
    expect(m.matches("#", "z"), True, "hash alone, one segment")
    expect(m.matches("a.*.#", "a.b"), True, "star then hash")


@check
def priority_then_order():
    mod = importlib.import_module("evbus")
    b = mod.Bus()
    calls = []
    b.subscribe("t", lambda t, p: calls.append("low-first"), priority=0)
    b.subscribe("t", lambda t, p: calls.append("high-first"), priority=5)
    b.subscribe("t", lambda t, p: calls.append("high-second"), priority=5)
    b.subscribe("t", lambda t, p: calls.append("neg"), priority=-1)
    b.subscribe("t", lambda t, p: calls.append("low-second"), priority=0)
    expect(b.publish("t", 1), 5, "handler count")
    expect(calls, ["high-first", "high-second", "low-first", "low-second", "neg"], "order")


@check
def errors_collected():
    mod = importlib.import_module("evbus")
    b = mod.Bus()
    calls = []

    def bad_one(t, p):
        calls.append("a")
        raise KeyError("boom")

    def good(t, p):
        calls.append("g")

    def bad_two(t, p):
        calls.append("b")
        raise ValueError("late")

    t1 = b.subscribe("x", bad_one, priority=2)
    b.subscribe("x", good, priority=1)
    t3 = b.subscribe("x", bad_two, priority=0)
    err = raises(mod.DispatchError, b.publish, "x", None)
    expect(calls, ["a", "g", "b"], "all handlers ran")
    expect([(tok, type(e)) for tok, e in err.errors], [(t1, KeyError), (t3, ValueError)], "errors")
    expect(str(err.errors[1][1]), "late", "exception kept")


@check
def once_semantics():
    mod = importlib.import_module("evbus")
    b = mod.Bus()
    calls = []

    def boom(t, p):
        calls.append(p)
        raise RuntimeError("x")

    b.subscribe("e", lambda t, p: calls.append(("ok", p)), once=True)
    expect(b.publish("e", 1), 1, "first publish")
    expect(b.publish("e", 2), 0, "removed after first delivery")
    b.subscribe("e", boom, once=True)
    raises(mod.DispatchError, b.publish, "e", 3)
    expect(b.publish("e", 4), 0, "removed even after raising")
    expect(calls, [("ok", 1), 3], "calls")


@check
def mutation_during_publish():
    mod = importlib.import_module("evbus")
    b = mod.Bus()
    calls = []
    state = {}

    def adder(t, p):
        calls.append("adder")
        if "new" not in state:
            state["new"] = b.subscribe("e", lambda t, p: calls.append("new"))
            state["removed"] = b.unsubscribe(state["victim"])

    def victim(t, p):
        calls.append("victim")

    b.subscribe("e", adder, priority=2)
    state["victim"] = b.subscribe("e", victim, priority=1)
    expect(b.publish("e", None), 2, "first publish count")
    expect(calls, ["adder", "victim"], "added not called, removed still called")
    expect(state["removed"], True, "unsubscribe during publish")
    calls.clear()
    expect(b.publish("e", None), 2, "second publish count")
    expect(calls, ["adder", "new"], "second publish")


@check
def history_replay():
    mod = importlib.import_module("evbus")
    hist = importlib.import_module("evbus.history")
    raises(ValueError, hist.History, -1)
    h = hist.History(2)
    h.record("a", 1)
    h.record("b", 2)
    h.record("a", 3)
    expect(h.matching("a"), [("a", 3)], "history keeps last two")
    expect(h.matching("#"), [("b", 2), ("a", 3)], "history oldest first")

    b = mod.Bus(history=2)
    for i in (1, 2, 3):
        b.publish("e.x", i)
    got = []
    b.subscribe("e.#", lambda t, p: got.append((t, p)), replay=True)
    expect(got, [("e.x", 2), ("e.x", 3)], "last two replayed, oldest first")
    once_got = []
    b.subscribe("e.#", lambda t, p: once_got.append(p), replay=True, once=True)
    expect(once_got, [2], "once with replay delivers one")
    expect(b.publish("e.x", 4), 1, "once subscriber removed")
    expect(got, [("e.x", 2), ("e.x", 3), ("e.x", 4)], "live delivery")
    expect(once_got, [2], "no second delivery")


@check
def unsubscribe():
    mod = importlib.import_module("evbus")
    b = mod.Bus()
    calls = []
    t1 = b.subscribe("s", lambda t, p: calls.append(1))
    t2 = b.subscribe("s", lambda t, p: calls.append(2))
    expect(t1, 1, "first token")
    expect(t2, 2, "second token")
    expect(b.unsubscribe(t1), True, "remove active")
    expect(b.unsubscribe(t1), False, "already removed")
    expect(b.unsubscribe(99), False, "unknown token")
    expect(b.publish("s"), 1, "one handler left")
    expect(calls, [2], "calls")
    expect(b.subscribe("s", lambda t, p: None), 3, "tokens keep increasing")


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
