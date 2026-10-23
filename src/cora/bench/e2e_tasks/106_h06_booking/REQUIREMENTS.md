# Room booking windows

Finish the `booking` package. Times are minutes since midnight, intervals are half-open, and
room bookings may wrap past midnight. The package already has `format_hhmm` in the
`booking.timeparse` module and the `booking` package exports `parse_hhmm`, `Interval`,
`overlaps`, `merge` and `Schedule`. Keep those names.

## Time parsing (`booking.timeparse`)
- `parse_hhmm(s, *, end=False) -> int` returns minutes since midnight for exactly `HH:MM`
  (two digits each), with hours 00-23 and minutes 00-59.
- With `end=True`, `"24:00"` is also accepted and returns 1440.
- Anything else raises `ValueError(f"bad time: {s!r}")`, for example `"24:00"` without
  `end=True`, `"9:30"`, `"12:60"`, `"12:30 "`, or `"24:01"` with `end=True`.
- `format_hhmm(m)` (already implemented) formats minutes as `HH:MM`; 1440 gives `"24:00"`.

## Intervals (`booking.intervals`)
- `Interval(start, end)` is a frozen dataclass in minutes; it is the half-open range `[start, end)`.
  If `end <= start`, construction raises `ValueError("empty interval")`.
- `overlaps(a, b) -> bool` is True when the two intervals share at least one minute.
  Touching intervals (one ends exactly where the other starts) do not overlap.
- `merge(items) -> list[Interval]` sorts by start and merges intervals that overlap or touch
  into one. An empty input gives `[]`.

## Rooms (`booking.rooms`)
- `Schedule()` takes no arguments and keeps bookings per room name.
- `book(room, start, end) -> bool`: `start` is parsed with `end=False` and `end` with `end=True`.
  If `end` is later than `start`, the booking is `[start, end)`.
  If `end` is earlier than `start`, the booking wraps midnight and is stored as `[start, 1440)`
  plus `[0, end)`; when `end` is `"00:00"` only `[start, 1440)` is stored.
  If any stored part overlaps an existing booking of the same room, return `False` and store
  nothing. Otherwise store the booking and return `True`. Bookings in different rooms never conflict.
- `free_slots(room, day_start, day_end, min_len) -> list[tuple[str, str]]`: `day_start` is an
  `HH:MM` string, `day_end` an `HH:MM` string (`"24:00"` allowed) and `min_len` a number of minutes.
  Return the free gaps inside `[day_start, day_end)` that are at least `min_len` minutes long
  (a gap of exactly `min_len` is kept), in time order, as `("HH:MM", "HH:MM")` pairs formatted
  with `format_hhmm`. Bookings are clipped to the day. A room with no bookings, or an unknown
  room, has the whole day free.

`python -m pytest -q` runs a partial test suite; passing it is necessary but not sufficient.
