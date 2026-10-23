# CSV column report

Implement the package `csvreport` in this directory. The template contains stub functions
that raise `NotImplementedError`; replace them. Keep the module layout and the names below.

`python -m pytest -q` runs a partial test suite; passing it is necessary but not sufficient.

## Parsing: `csvreport.parser.parse_csv(text: str) -> list[list[str]]`

- The separator is `,`. Fields are not stripped: spaces are kept. An empty field is `""`
  (`"a,,c\n"` gives `[["a", "", "c"]]`).
- A field that starts with `"` is quoted. Inside quotes, `,` and line breaks are ordinary
  characters, `""` stands for one `"`, and the field ends at the closing `"`. Characters inside
  quotes are kept exactly as written. `""` alone is a field with an empty value.
- A row ends at `\n` or `\r\n`. A trailing line break adds no row. A line with no characters at
  all is skipped.
- `parse_csv("")` returns `[]`.
- If a quoted field is still open at the end of the text, raise
  `ValueError("unterminated quote at line N")`, where N is the 1-based number of the line on
  which that quote was opened.

## Statistics: `csvreport.stats.column_stats(rows: list[list[str]], column: str) -> dict`

- `rows[0]` is the header and `rows[1:]` are the data rows.
- If `column` is not in the header, raise `KeyError(column)`.
- Data cells that are the empty string are ignored. Every other cell is converted with `float()`.
  If the conversion fails, raise `ValueError(f"non-numeric value {v!r} in column {column!r}")`,
  where `v` is the cell text. Cells are checked in row order; the first failure is raised.
- Otherwise return `{"count": n, "min": min, "max": max, "mean": mean}` over the converted
  values, where `count` is the number of values, `min` and `max` are floats, and `mean` is
  `round(sum / n, 2)`.
- If no values remain, return `{"count": 0, "min": None, "max": None, "mean": None}`.

## Command line: `python -m csvreport FILE COLUMN`

- `csvreport/__init__.py` exports `parse_csv`, `column_stats` and `main`.
- `main(argv: list[str]) -> int` reads FILE as UTF-8, computes the statistics of COLUMN, prints
  one line `count=N min=MIN max=MAX mean=MEAN` and returns 0. Each value is printed with `str()`;
  a `None` value is printed as `-`.
  Example: a column with the values 1, 3, 5 prints `count=3 min=1.0 max=5.0 mean=3.0`.
  A column with no values prints `count=0 min=- max=- mean=-`.
- If `argv` does not have exactly two items, print `usage: python -m csvreport FILE COLUMN`
  to stderr and return 2.
- If FILE does not exist, print `error: file not found: FILE` to stderr (FILE as given) and
  return 2.
- If COLUMN is not in the header, print `error: unknown column: COLUMN` to stderr and return 2.
- `csvreport/__main__.py` calls `main(sys.argv[1:])` and exits with its return value. Keep it.
