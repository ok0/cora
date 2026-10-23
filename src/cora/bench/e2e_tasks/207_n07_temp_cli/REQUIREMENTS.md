# Temperature converter CLI

Write a command line tool in `temps.py` that converts one temperature into another unit.

Run it like this:

    python temps.py <value><unit> <target>

- `<value>` is a number. It may be negative and may have a decimal point.
- `<unit>` is the unit the value is written in, written directly after the number. It is `C` (Celsius), `F` (Fahrenheit) or `K` (Kelvin).
- `<target>` is the unit to convert to: `C`, `F` or `K`.
- Units are case-insensitive, so `c`, `C`, `f` and `k` all work.
- On success, print the converted value with exactly one decimal place, followed by the target unit in upper case, on stdout. Exit with code 0.

Examples:

- `python temps.py 100C F` prints `212.0F`
- `python temps.py -40C F` prints `-40.0F`
- `python temps.py 32F C` prints `0.0C`
- `python temps.py 98.6F C` prints `37.0C`
- `python temps.py 373.15K C` prints `100.0C`
- `python temps.py 26.85C K` prints `300.0K`
- `python temps.py -40c f` prints `-40.0F`
- `python temps.py 5C C` prints `5.0C`

Conversion formulas:

- Fahrenheit to Celsius: (F - 32) x 5/9
- Celsius to Fahrenheit: C x 9/5 + 32
- Celsius to Kelvin: C + 273.15
- Kelvin to Celsius: K - 273.15

Converting to the same unit returns the value unchanged.

Absolute zero:

- A value below absolute zero is an error. Absolute zero is -273.15 C, which is 0 K.
- Check the input value after it is converted to Celsius.
- On this error, print `error: below absolute zero` on stderr and exit with code 1.
- Examples: `python temps.py -300C K` and `python temps.py -1K C` both fail this way.

Usage errors:

- A usage error exits with code 2 and prints one line on stderr that starts with `usage:`.
- These cases are usage errors: the wrong number of arguments, an unknown input unit, an unknown target unit, or a value that is not a number.
- Examples: no arguments at all, `python temps.py 100C`, `python temps.py 100X F`, `python temps.py abcC F`.
- Print nothing on stdout when there is an error.

Code shape:

- Keep the code in `temps.py` so that it runs as a script.
- `main(argv)` takes the arguments without the program name and returns the exit code.
- The `__main__` block calls `main` with `sys.argv[1:]`.
