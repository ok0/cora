# Contact list de-duplication

We keep a CSV export of contacts. The same person often appears more than once,
with different email spellings and missing fields. Write the Python package
`contacts/` (keep `contacts/__init__.py`) that normalizes values and removes duplicates.

## Email normalization

`normalize_email(s: str) -> str` in `contacts/normalize.py`:

- Strip surrounding whitespace and lowercase the whole value.
- If there is no `@`, return that value and nothing else.
- If the domain is `gmail.com` or `googlemail.com`: remove every `.` from the
  local part, drop a `+` suffix (the `+` and everything after it), and return
  `<local>@gmail.com`.
- For any other domain, keep the local part as it is (dots and `+` stay).

Examples:

- `"  John.Doe+news@GMail.com "` becomes `"johndoe@gmail.com"`
- `"j.d@googlemail.com"` becomes `"jd@gmail.com"`
- `"Mary.Ann+x@Example.org"` becomes `"mary.ann+x@example.org"`
- `"NoAt "` becomes `"noat"`

## Phone normalization

`normalize_phone(s: str) -> str` in `contacts/normalize.py`. Look at the digits
of the stripped input. If the input starts with `00`, the result is `+` followed
by the digits after the leading `00`. Otherwise, with exactly 10 digits, the
result is `+1` followed by them. Otherwise, with at least one digit, the result
is `+` followed by all digits. With no digits, the result is `""`.

Examples: `"(555) 123-4567"` becomes `"+15551234567"`, `"0044 20 7946 0958"` and
`"+44 20 7946 0958"` both become `"+442079460958"`, `"12345"` becomes `"+12345"`,
and `"n/a"` becomes `""`.

## De-duplication

`dedupe(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]` in
`contacts/merge.py` returns `(kept_rows, removed_count)`.

- Two rows are duplicates when their normalized emails are equal.
- A row with an empty email is never merged with another row.
- The first row of each key keeps its position and is the kept row.
- Each later duplicate fills only the fields that are empty in the kept row.
  A non-empty field is never changed. If several duplicates supply the same
  empty field, the earliest non-empty value wins.
- Kept rows keep their raw values. `dedupe` does not normalize them.

Worked example. Input rows, in order:

1. `name=John`, `email=john.doe@gmail.com`, `phone=` (empty)
2. `name=` (empty), `email=Mary@x.org`, `phone=555 000 1111`
3. `name=Johnny`, `email=JohnDoe+a@gmail.com`, `phone=5551234567`
4. `name=Nobody`, `email=` (empty), `phone=1`
5. `name=N2`, `email=` (empty), `phone=2`
6. `name=Mary`, `email=mary@x.org`, `phone=` (empty)

Row 3 is merged into row 1: its phone fills row 1, its name is ignored because
`John` is set. Row 6 is merged into row 2 and fills the empty name. Rows 4 and 5
have no email, so both stay. The result is rows 1, 2, 4 and 5.

## Command line

Run as `python -m contacts.cli IN OUT`. `contacts/cli.py` defines
`main(argv=None) -> int`, which returns the exit code. `IN` is a CSV file with a header.

- If the header has no column named `email`, print exactly
  `error: no email column` to stderr, exit with code 2, and do not create `OUT`.
- If `IN` cannot be read, print exactly `error: cannot read IN` to stderr and
  exit with code 1.
- Otherwise run `dedupe` on the rows of `IN`, then normalize the `email` column of
  every kept row with `normalize_email`. If the header has a `phone` column,
  normalize it with `normalize_phone` too.
- `OUT` has the same header and column order as `IN`, written with the `csv` module.
- Print one line to stdout, `kept K, removed R` (K kept rows, R removed count).
  Exit with code 0.

Example. If `IN` holds the header `name,email,phone` and the six rows of the
worked example, then `OUT` contains:

```
name,email,phone
John,johndoe@gmail.com,+15551234567
Mary,mary@x.org,+15550001111
Nobody,,+1
N2,,+2
```

and stdout is `kept 4, removed 2`.
