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


def pkg():
    return importlib.import_module("layercfg")


def mod(name):
    return importlib.import_module(f"layercfg.{name}")


@check
def parse_sections_and_comments():
    p = mod("parser").parse
    text = "# top comment\n[Server]\nHost = example.org\n; note\nPORT=8080\n\n[DB]\nName = app\n"
    expect(p(text), {
        "server": {"host": ("example.org", 3), "port": ("8080", 5)},
        "db": {"name": ("app", 8)},
    }, "sections and comments")


@check
def continuation_lines():
    p = mod("parser").parse
    expect(p("[s]\nhosts = a\n  b\n  c\n"), {"s": {"hosts": ("a\nb\nc", 2)}}, "continuation")


@check
def parse_errors_with_line():
    p = mod("parser").parse
    err = pkg().ConfigError
    expect(str(raises(err, p, "x = 1\n")), "line 1: key outside section", "outside section")
    expect(str(raises(err, p, "[a]\nk = 1\nK = 2\n")),
           "line 3: duplicate key 'k' in [a]", "duplicate key")
    expect(str(raises(err, p, "[a]\njust words\n")), "line 2: cannot parse", "cannot parse")


@check
def interpolation_same_and_cross_section():
    load = pkg().load
    text = ("[db]\nhost = dbhost\n[web]\nport = 80\n"
            "url = http://${db:host}:${port}\nprice = $$5\nlabel = ${port}0\n")
    cfg = load({}, text, {})
    expect(cfg.get("web", "url"), "http://dbhost:80", "same and cross section")
    expect(cfg.get("web", "price"), "$5", "escaped dollar")
    expect(cfg.get("web", "label"), "800", "same section reference")


@check
def interpolation_sees_env_override():
    cfg = pkg().load({"server": {"host": "localhost"}},
                     "[server]\nurl = http://${host}\n",
                     {"APP_SERVER__HOST": "x"})
    expect(cfg.get("server", "url"), "http://x", "override seen by interpolation")


@check
def cycle_and_unknown_errors():
    load = pkg().load
    err = pkg().ConfigError
    expect(str(raises(err, load, {}, "[a]\nx = ${y}\ny = ${x}\n", {})),
           "reference cycle: a.x -> a.y -> a.x", "cycle")
    expect(str(raises(err, load, {}, "[a]\nx = ${nope}\n", {})),
           "unknown reference ${nope} in [a] x", "unknown reference")


@check
def env_precedence_and_new_keys():
    cfg = pkg().load({"app": {"level": "info", "name": "d"}},
                     "[app]\nlevel = debug\n",
                     {"APP_APP__LEVEL": "warn", "APP_NEW__K": "1", "OTHER": "1"})
    expect(cfg.get("app", "level"), "warn", "env wins")
    expect(cfg.source("app", "level"), "env:APP_APP__LEVEL", "env source")
    expect(cfg.get("app", "name"), "d", "default kept")
    expect(cfg.source("app", "name"), "default", "default source")
    expect(cfg.get("new", "k"), "1", "new section and key")
    expect(cfg.source("new", "k"), "env:APP_NEW__K", "new key source")
    expect(str(raises(pkg().ConfigError, cfg.get, "other", "other")),
           "missing [other] other", "unprefixed variable ignored")


@check
def typed_getters():
    cfg = pkg().load({}, "[t]\nn = 42\nb = Yes\nc = off\nlist = a, b,\n c,,\n", {})
    expect(cfg.get_int("t", "n"), 42, "int")
    expect(cfg.get_bool("t", "b"), True, "bool yes")
    expect(cfg.get_bool("t", "c"), False, "bool off")
    expect(cfg.get_list("t", "list"), ["a", "b", "c"], "list")


@check
def source_attribution_in_errors():
    load = pkg().load
    err = pkg().ConfigError
    cfg = load({}, "[s]\nx = 1\nk = nope\n", {})
    expect(str(raises(err, cfg.get_int, "s", "k")),
           "[s] k: not an integer: 'nope' (from file:3)", "file source")
    cfg = load({}, "[s]\nk = 1\n", {"APP_S__K": "zz"})
    expect(str(raises(err, cfg.get_int, "s", "k")),
           "[s] k: not an integer: 'zz' (from env:APP_S__K)", "env source")


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
