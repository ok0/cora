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


def close(actual, wanted, what):
    assert abs(actual - wanted) < 1e-9, f"{what}: expected {wanted!r}, got {actual!r}"


def raises(exc, fn, *args):
    try:
        fn(*args)
    except exc as e:
        return e
    raise AssertionError(f"{exc.__name__} not raised")


def mod(name):
    return importlib.import_module(name)


@check
def starts_full_and_drains():
    tb = mod("throttle.bucket")
    clk = mod("throttle.clock").FakeClock()
    b = tb.TokenBucket(5, 1.0, clock=clk)
    expect([b.allow() for _ in range(5)], [True] * 5, "five allowed")
    expect(b.allow(), False, "sixth denied")


@check
def refill_capped():
    tb = mod("throttle.bucket")
    clk = mod("throttle.clock").FakeClock()
    b = tb.TokenBucket(5, 1.0, clock=clk)
    for _ in range(5):
        b.allow()
    clk.advance(2.5)
    close(b.tokens, 2.5, "tokens after 2.5s")
    expect(b.allow(3), False, "allow(3) with 2.5 tokens")
    close(b.tokens, 2.5, "tokens after denied allow")
    expect(b.allow(2), True, "allow(2) with 2.5 tokens")
    close(b.tokens, 0.5, "tokens after allow(2)")
    clk.advance(100)
    close(b.tokens, 5.0, "tokens capped at capacity")


@check
def wait_time_values():
    tb = mod("throttle.bucket")
    clk = mod("throttle.clock").FakeClock()
    b = tb.TokenBucket(5, 1.0, clock=clk)
    for _ in range(5):
        b.allow()
    clk.advance(0.5)
    close(b.wait_time(3), 2.5, "wait_time(3)")
    close(b.wait_time(1), 0.5, "wait_time(1)")
    full = tb.TokenBucket(5, 1.0, clock=mod("throttle.clock").FakeClock())
    close(full.wait_time(), 0.0, "wait_time when full")


@check
def invalid_arguments():
    tb = mod("throttle.bucket")
    clk = mod("throttle.clock").FakeClock()
    raises(ValueError, tb.TokenBucket, 0, 1.0)
    raises(ValueError, tb.TokenBucket, 5, 0.0)
    b = tb.TokenBucket(5, 1.0, clock=clk)
    raises(ValueError, b.allow, 0)
    raises(ValueError, b.allow, 6)
    raises(ValueError, b.wait_time, 6)


@check
def keyed_independent():
    kl = mod("throttle.keyed")
    clk = mod("throttle.clock").FakeClock()
    k = kl.KeyedLimiter(2, 1.0, 100.0, clock=clk)
    expect([k.allow("a"), k.allow("a"), k.allow("a")], [True, True, False], "key a")
    expect(k.allow("b"), True, "key b")
    expect(k.active_keys(), ["a", "b"], "active keys")


@check
def idle_eviction():
    kl = mod("throttle.keyed")
    clk = mod("throttle.clock").FakeClock()
    k = kl.KeyedLimiter(2, 1.0, 10.0, clock=clk)
    k.allow("a")
    k.allow("b")
    clk.advance(5)
    k.allow("a")
    clk.advance(5)
    expect(k.active_keys(), ["a"], "b evicted after ttl")
    clk.advance(10)
    expect(k.active_keys(), [], "a evicted after ttl")
    expect([k.allow("a"), k.allow("a")], [True, True], "evicted key starts full")


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
