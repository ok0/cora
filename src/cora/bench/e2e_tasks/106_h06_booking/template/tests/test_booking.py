from booking import Interval, Schedule, overlaps, parse_hhmm


def test_parse_hhmm():
    assert parse_hhmm("09:30") == 570
    assert parse_hhmm("24:00", end=True) == 1440


def test_overlaps_half_open():
    assert overlaps(Interval(0, 60), Interval(60, 90)) is False
    assert overlaps(Interval(0, 60), Interval(59, 90)) is True


def test_book_conflicts():
    s = Schedule()
    assert s.book("A", "09:00", "10:00") is True
    assert s.book("A", "09:30", "10:30") is False
    assert s.book("A", "10:00", "11:00") is True
    assert s.book("B", "09:30", "10:30") is True
