# Weekly shift rota

Finish the `rota` package in this directory. Four modules are stubs that raise `NotImplementedError`:
`rota/parse.py`, `rota/rules.py`, `rota/assign.py` and `rota/export.py`. Implement them.
`rota/model.py` and `rota/__init__.py` are complete; keep them unchanged. Keep every function name and signature.

## Model

- `DAYS` is `("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")`. A day number is an index into it (Mon = 0).
- `Shift(id, day, start, end)`: `start` and `end` are minutes after midnight on `day`. If `end <= start`, the shift ends the next day. `Staff(name, max_hours, unavailable)`: `unavailable` is a tuple of unavailability texts.

## Parsing (`rota/parse.py`)

`parse_shift(id, text) -> Shift`
- `text` is a day name, one space, then `HH:MM-HH:MM`. `"Mon 22:00-06:00"` gives `Shift(id, 0, 1320, 360)`.
- Day names are exact and case-sensitive. Times are two-digit `HH:MM`, 00:00 to 23:59; `9:00` is invalid. `start == end` is invalid.
- Invalid text raises `ValueError(f"bad shift '{text}'")`, with the original text.

`parse_unavailable(text) -> tuple[int, int, int]` returns `(day, start, end)` in day number and minutes.
- A whole day is the day name alone: `"Sat"` gives `(5, 0, 1440)`.
- A timed window: `"Mon 09:00-12:00"` gives `(0, 540, 720)`. It must have start < end.
- Invalid text raises `ValueError(f"bad unavailability '{text}'")`.

## Timeline

A shift occupies `[day*1440 + start, day*1440 + start + d)`, where `d = (end - start) % 1440` is its length.
So `Mon 22:00-06:00` has length 480. The week does not wrap: a Sunday shift past midnight just ends after the last day.

## Eligibility (`rota/rules.py`)

`can_take(staff, shift, assigned) -> str | None`, where `assigned` is the shifts already given to this staff member.
Return the first failing reason, checked in this order, or `None` if the shift is allowed:

1. `"unavailable"`: the shift starts on a whole-day entry of `staff.unavailable`, or its interval overlaps a timed window of `staff.unavailable`.
2. `"overlap"`: its interval overlaps the interval of any assigned shift. Touching ends do not overlap.
3. `"rest"`: for any assigned shift, the gap between the intervals is less than 660 minutes. Touching intervals have gap 0.
4. `"hours"`: the total length of the assigned shifts plus this shift is more than `max_hours * 60`.

## Assignment (`rota/assign.py`)

`assign(shifts, staff) -> Rota`
- Process shifts in ascending `(day, start, id)` order, with `id` compared as text.
- The eligible staff are those for which `can_take` returns `None`, given the shifts they already hold. Pick the eligible one with the fewest assigned minutes; ties go to the name that sorts first.
- If nobody is eligible, the shift is unfilled (`None`) and adds no minutes.
- Return `Rota(shifts, assignments, minutes)`:
  - `shifts`: the shifts in processing order.
  - `assignments`: every shift id mapped to a staff name, or `None` when unfilled.
  - `minutes`: every staff name, including 0, mapped to the total length of their shifts.

## Export (`rota/export.py`)

`to_csv(rota) -> str`
- Header line `shift,day,start,end,staff`, then one row per shift in `rota.shifts` order: id, day name, start and end as `HH:MM`, and the staff name (empty when unfilled). Every line ends with `\n`, including the last.

`summary(rota) -> str`
- One line per staff name, sorted: `name: H.Hh`, the minutes divided by 60 with one decimal. No shifts gives `0.0h`.
- A final line `unfilled: id, id` listing unfilled ids in processing order, joined with `", "`, or `unfilled: none`.
- Every line ends with `\n`.

## Worked example

Staff: `ann` (max 40 hours); `bob` (max 8 hours, unavailable `Tue`); `cy` (max 40 hours, unavailable `Mon 06:00-12:00`).

Shifts, given in any order: `s1` `Mon 08:00-16:00`; `s2` `Mon 22:00-06:00`; `s3` `Tue 08:00-16:00`; `s4` `Tue 14:00-22:00`; `s5` `Wed 00:00-04:00`.

- `s1` goes to `ann`: `cy` is unavailable, and `ann` and `bob` tie at 0 minutes, so `ann` sorts first.
- `s2` goes to `bob`: `bob` and `cy` tie at 0 minutes.
- `s3` goes to `cy`: `bob` is unavailable on Tuesday, and `ann` has 480 minutes.
- `s4` goes to `ann`: `cy` overlaps `s3`, and `bob` is unavailable on Tuesday.
- `s5` is unfilled: `ann` has a 240-minute gap after `s4`, `bob` would exceed 8 hours, and `cy` has a 480-minute gap after `s3`.

`to_csv(rota)` returns:

```
shift,day,start,end,staff
s1,Mon,08:00,16:00,ann
s2,Mon,22:00,06:00,bob
s3,Tue,08:00,16:00,cy
s4,Tue,14:00,22:00,ann
s5,Wed,00:00,04:00,
```

`summary(rota)` returns:

```
ann: 16.0h
bob: 8.0h
cy: 8.0h
unfilled: s5
```
