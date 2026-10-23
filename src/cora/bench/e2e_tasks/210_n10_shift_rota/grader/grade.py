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


def mod(name):
    return importlib.import_module(name)


@check
def parse_shift_valid():
    p = mod("rota.parse")
    m = mod("rota.model")
    expect(p.parse_shift("s1", "Mon 22:00-06:00"), m.Shift("s1", 0, 1320, 360), "overnight")
    expect(p.parse_shift("s2", "Sun 08:00-16:30"), m.Shift("s2", 6, 480, 990), "sunday")
    expect(p.parse_shift("s3", "Wed 00:00-23:59"), m.Shift("s3", 2, 0, 1439), "full day")


@check
def parse_errors():
    p = mod("rota.parse")
    for bad in ["Mon 9:00-10:00", "Xyz 08:00-09:00", "Mon 24:00-01:00", "Mon 08:00-08:00"]:
        e = raises(ValueError, p.parse_shift, "s9", bad)
        expect(str(e), f"bad shift '{bad}'", f"message for {bad!r}")
    e = raises(ValueError, p.parse_unavailable, "Mon 12:00-09:00")
    expect(str(e), "bad unavailability 'Mon 12:00-09:00'", "bad unavailability")


@check
def unavailable_rules():
    p = mod("rota.parse")
    r = mod("rota.rules")
    m = mod("rota.model")
    expect(p.parse_unavailable("Sat"), (5, 0, 1440), "whole day")
    expect(p.parse_unavailable("Mon 09:00-12:00"), (0, 540, 720), "window")
    bob = m.Staff("bob", 40, ("Tue",))
    cy = m.Staff("cy", 40, ("Mon 06:00-12:00",))
    expect(r.can_take(bob, p.parse_shift("a", "Tue 08:00-09:00"), []), "unavailable", "whole day")
    expect(r.can_take(bob, p.parse_shift("a", "Tue 23:00-23:30"), []), "unavailable", "whole day late")
    expect(r.can_take(cy, p.parse_shift("a", "Mon 08:00-16:00"), []), "unavailable", "window overlap")
    expect(r.can_take(cy, p.parse_shift("a", "Mon 05:00-07:00"), []), "unavailable", "window overlap early")
    expect(r.can_take(cy, p.parse_shift("a", "Mon 12:00-16:00"), []), None, "touching window end")
    expect(r.can_take(cy, p.parse_shift("a", "Mon 22:00-02:00"), []), None, "no overlap")
    expect(r.can_take(cy, p.parse_shift("a", "Tue 08:00-09:00"), []), None, "other day")


@check
def overlap_rule():
    p = mod("rota.parse")
    r = mod("rota.rules")
    m = mod("rota.model")
    ann = m.Staff("ann", 40)
    held = [p.parse_shift("s1", "Mon 08:00-16:00")]
    expect(r.can_take(ann, p.parse_shift("b", "Mon 15:00-17:00"), held), "overlap", "partial overlap")
    expect(r.can_take(ann, p.parse_shift("b", "Mon 09:00-10:00"), held), "overlap", "inside")
    expect(r.can_take(ann, p.parse_shift("b", "Mon 07:00-17:00"), held), "overlap", "contains")


@check
def rest_rule_overnight():
    p = mod("rota.parse")
    r = mod("rota.rules")
    m = mod("rota.model")
    ann = m.Staff("ann", 40)
    held = [p.parse_shift("s2", "Mon 22:00-06:00")]
    expect(r.can_take(ann, p.parse_shift("c", "Tue 05:00-07:00"), held), "overlap", "into held shift")
    expect(r.can_take(ann, p.parse_shift("c", "Tue 16:00-18:00"), held), "rest", "gap 600")
    expect(r.can_take(ann, p.parse_shift("c", "Tue 17:00-19:00"), held), None, "gap 660")
    expect(r.can_take(ann, p.parse_shift("c", "Mon 08:00-12:00"), held), "rest", "gap before")


@check
def hours_rule():
    p = mod("rota.parse")
    r = mod("rota.rules")
    m = mod("rota.model")
    bob = m.Staff("bob", 8)
    held = [p.parse_shift("s1", "Mon 08:00-16:00")]
    expect(r.can_take(bob, p.parse_shift("c", "Wed 08:00-09:00"), held), "hours", "480 + 60")
    expect(r.can_take(bob, p.parse_shift("c", "Wed 08:00-16:00"), []), None, "exactly 480")
    expect(r.can_take(bob, p.parse_shift("c", "Wed 22:00-06:00"), []), None, "overnight 480")
    expect(r.can_take(bob, p.parse_shift("c", "Wed 08:00-17:00"), []), "hours", "540")


@check
def reason_order():
    p = mod("rota.parse")
    r = mod("rota.rules")
    m = mod("rota.model")
    bob = m.Staff("bob", 1, ("Mon",))
    expect(r.can_take(bob, p.parse_shift("c", "Mon 08:00-16:00"), []), "unavailable", "unavailable before hours")
    ann = m.Staff("ann", 1)
    held = [p.parse_shift("s1", "Mon 08:00-16:00")]
    expect(r.can_take(ann, p.parse_shift("c", "Mon 09:00-10:00"), held), "overlap", "overlap before hours")
    expect(r.can_take(ann, p.parse_shift("c", "Mon 17:00-18:00"), held), "rest", "rest before hours")


@check
def assign_example():
    p = mod("rota.parse")
    a = mod("rota.assign")
    m = mod("rota.model")
    staff = [m.Staff("ann", 40), m.Staff("bob", 8, ("Tue",)), m.Staff("cy", 40, ("Mon 06:00-12:00",))]
    shifts = [
        p.parse_shift("s1", "Mon 08:00-16:00"),
        p.parse_shift("s2", "Mon 22:00-06:00"),
        p.parse_shift("s3", "Tue 08:00-16:00"),
        p.parse_shift("s4", "Tue 14:00-22:00"),
        p.parse_shift("s5", "Wed 00:00-04:00"),
    ]
    rota = a.assign(shifts, staff)
    expect(rota.assignments, {"s1": "ann", "s2": "bob", "s3": "cy", "s4": "ann", "s5": None}, "assignments")
    expect(rota.minutes, {"ann": 960, "bob": 480, "cy": 480}, "minutes")
    expect([s.id for s in rota.shifts], ["s1", "s2", "s3", "s4", "s5"], "processing order")
    again = a.assign(list(reversed(shifts)), staff)
    expect(again.assignments, rota.assignments, "input order does not matter")


@check
def export_and_summary():
    p = mod("rota.parse")
    a = mod("rota.assign")
    m = mod("rota.model")
    ex = mod("rota.export")
    staff = [m.Staff("ann", 40), m.Staff("bob", 8, ("Tue",)), m.Staff("cy", 40, ("Mon 06:00-12:00",))]
    shifts = [
        p.parse_shift("s1", "Mon 08:00-16:00"),
        p.parse_shift("s2", "Mon 22:00-06:00"),
        p.parse_shift("s3", "Tue 08:00-16:00"),
        p.parse_shift("s4", "Tue 14:00-22:00"),
        p.parse_shift("s5", "Wed 00:00-04:00"),
    ]
    rota = a.assign(shifts, staff)
    expect(
        ex.to_csv(rota),
        "shift,day,start,end,staff\ns1,Mon,08:00,16:00,ann\ns2,Mon,22:00,06:00,bob\n"
        "s3,Tue,08:00,16:00,cy\ns4,Tue,14:00,22:00,ann\ns5,Wed,00:00,04:00,\n",
        "csv",
    )
    expect(ex.summary(rota), "ann: 16.0h\nbob: 8.0h\ncy: 8.0h\nunfilled: s5\n", "summary")
    solo = a.assign([p.parse_shift("s1", "Mon 08:00-16:00")], [m.Staff("ann", 40)])
    expect(ex.summary(solo), "ann: 8.0h\nunfilled: none\n", "no unfilled")


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
