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


def _raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        return e
    raise AssertionError(f"no exception from {fn.__name__}")


@check
def parse_hhmm():
    tp = importlib.import_module("booking.timeparse")
    expect(tp.parse_hhmm("00:00"), 0, "midnight")
    expect(tp.parse_hhmm("09:30"), 570, "09:30")
    expect(tp.parse_hhmm("23:59"), 1439, "23:59")
    expect(tp.parse_hhmm("24:00", end=True), 1440, "24:00 with end")
    for bad in ("24:00", "9:30", "12:60", "12:5", "ab:cd", "12:30 "):
        e = _raises(tp.parse_hhmm, bad)
        expect(type(e).__name__, "ValueError", f"type for {bad!r}")
        expect(str(e), f"bad time: {bad!r}", f"message for {bad!r}")
    e = _raises(tp.parse_hhmm, "24:01", end=True)
    expect(str(e), "bad time: '24:01'", "24:01 with end")


@check
def overlaps_half_open():
    iv = importlib.import_module("booking.intervals")
    expect(iv.overlaps(iv.Interval(0, 60), iv.Interval(60, 90)), False, "touching")
    expect(iv.overlaps(iv.Interval(60, 90), iv.Interval(0, 60)), False, "touching reversed")
    expect(iv.overlaps(iv.Interval(0, 60), iv.Interval(59, 90)), True, "overlap")
    expect(iv.overlaps(iv.Interval(0, 100), iv.Interval(10, 20)), True, "contained")


@check
def invalid_interval():
    iv = importlib.import_module("booking.intervals")
    for start, end in ((10, 10), (10, 5)):
        e = _raises(iv.Interval, start, end)
        expect(type(e).__name__, "ValueError", f"type for {start},{end}")
        expect(str(e), "empty interval", f"message for {start},{end}")
    expect(iv.Interval(5, 10).end, 10, "valid interval")


@check
def merge_touching_and_unsorted():
    iv = importlib.import_module("booking.intervals")
    got = iv.merge([iv.Interval(30, 40), iv.Interval(0, 10), iv.Interval(10, 20),
                    iv.Interval(15, 25), iv.Interval(40, 50)])
    expect(got, [iv.Interval(0, 25), iv.Interval(30, 50)], "merge")
    expect(iv.merge([]), [], "merge empty")


@check
def book_conflicts():
    rooms = importlib.import_module("booking.rooms")
    s = rooms.Schedule()
    expect(s.book("A", "09:00", "10:00"), True, "first booking")
    expect(s.book("A", "09:30", "10:30"), False, "overlap")
    expect(s.book("A", "10:00", "11:00"), True, "touching")
    expect(s.book("A", "08:00", "12:00"), False, "covers existing bookings")
    expect(s.book("B", "09:30", "10:30"), True, "other room")
    expect(s.book("A", "11:00", "11:30"), True, "after")
    expect(s.book("A", "08:00", "09:00"), True, "failed booking stored nothing")


@check
def book_overnight():
    rooms = importlib.import_module("booking.rooms")
    s = rooms.Schedule()
    expect(s.book("A", "22:00", "02:00"), True, "overnight")
    expect(s.book("A", "23:00", "23:30"), False, "late part conflicts")
    expect(s.book("A", "01:00", "03:00"), False, "early part conflicts")
    expect(s.book("A", "21:00", "22:30"), False, "starts before")
    expect(s.book("A", "02:00", "22:00"), True, "day between the two parts")
    expect(s.book("B", "23:00", "24:00"), True, "ends at 24:00")
    expect(s.book("B", "23:30", "23:45"), False, "inside 24:00 booking")
    expect(s.book("C", "22:00", "00:00"), True, "ends at midnight")
    expect(s.book("C", "23:00", "23:10"), False, "inside midnight booking")
    expect(s.book("C", "00:00", "01:00"), True, "nothing stored before midnight")


@check
def free_slots_basic():
    rooms = importlib.import_module("booking.rooms")
    s = rooms.Schedule()
    s.book("A", "09:00", "10:00")
    s.book("A", "12:00", "13:30")
    expect(s.free_slots("A", "08:00", "18:00", 30),
           [("08:00", "09:00"), ("10:00", "12:00"), ("13:30", "18:00")], "min 30")
    expect(s.free_slots("A", "08:00", "18:00", 120),
           [("10:00", "12:00"), ("13:30", "18:00")], "min 120")
    expect(s.free_slots("Z", "08:00", "10:00", 30), [("08:00", "10:00")], "unknown room")


@check
def free_slots_edges():
    rooms = importlib.import_module("booking.rooms")
    s = rooms.Schedule()
    s.book("E", "22:00", "23:00")
    expect(s.free_slots("E", "20:00", "24:00", 60),
           [("20:00", "22:00"), ("23:00", "24:00")], "day ends at 24:00")
    s.book("F", "08:00", "18:00")
    expect(s.free_slots("F", "08:00", "18:00", 1), [], "fully booked day")
    s.book("G", "09:00", "10:00")
    s.book("G", "10:00", "11:00")
    expect(s.free_slots("G", "08:00", "12:00", 30),
           [("08:00", "09:00"), ("11:00", "12:00")], "touching bookings")
    s.book("H", "07:00", "08:30")
    expect(s.free_slots("H", "08:00", "10:00", 1), [("08:30", "10:00")],
           "booking starts before the day")
    s.book("I", "17:00", "19:00")
    expect(s.free_slots("I", "08:00", "18:00", 30), [("08:00", "17:00")],
           "booking runs past the day")
    s.book("J", "08:00", "09:00")
    expect(s.free_slots("J", "08:00", "10:00", 60), [("09:00", "10:00")], "gap of exactly min_len")
    expect(s.free_slots("J", "08:00", "10:00", 61), [], "gap shorter than min_len")


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
