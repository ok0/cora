# Layered configuration loader

We need a small Python package, `layercfg`, that reads an INI-style configuration text, applies environment overrides, expands `${...}` lookups and gives typed access to the final values.

The package skeleton is in place. `layercfg/__init__.py` and `layercfg/errors.py` are complete and must stay as they are. Four modules are not finished: `layercfg/parser.py`, `layercfg/layers.py`, `layercfg/interp.py` and `layercfg/config.py`. Implement them so that `load` works.

Public API, available as `from layercfg import load, Config, ConfigError`:

    load(defaults, text, env) -> Config

- `defaults`: a dict of section name to a dict of key to string value.
- `text`: the configuration file contents.
- `env`: a mapping of environment variables, for example `os.environ`.

Every error is a `ConfigError` (a subclass of `Exception`) whose message is exactly as given below.

Module contracts (the package wires them together, so keep these names and signatures):

- `parser.parse(text) -> dict[str, dict[str, tuple[str, int]]]`: section to key to (raw value, 1-based line number).
- `layers.merge(defaults, parsed, env) -> dict[str, dict[str, tuple[str, str]]]`: section to key to (raw value, source).
- `interp.resolve(merged) -> dict[str, dict[str, tuple[str, str]]]`: same shape, values interpolated, source kept.

## File format

- A section header is `[name]`. Section names are case-insensitive; store them lowercased.
- A key/value line is `key = value`. Split at the first `=`. Strip spaces around the key and the value. Keys are case-insensitive; store them lowercased.
- Blank lines are skipped. A full-line comment starts with `#` or `;` (indentation before the marker is allowed) and is skipped.
- A line that starts with whitespace and is not a comment continues the previous key's value. Each continuation line is stripped and appended to the value with a single `\n` between parts.

Example:

    [server]
    hosts = alpha
      beta
      gamma

The value of `server.hosts` is `alpha\nbeta\ngamma`, and its line is 2 (the line of the key).

Parse errors, where N is the 1-based physical line number:

- `line N: key outside section`: a key/value line before any header.
- `line N: duplicate key 'k' in [s]`: the same key twice in one section. `k` and `s` are the lowercased key and section.
- `line N: cannot parse`: any other line, including a continuation line that has no preceding key (for example directly after a header).

Example: the text `[db]\nhost = a\nHOST = b` raises `line 3: duplicate key 'host' in [db]`.

## Layers

Precedence from lowest to highest: defaults, then the file, then the environment.

- A value from `defaults` has source `default`.
- A value from the file has source `file:N`, where N is the line of its key.
- An environment variable named `APP_<SECTION>__<KEY>` sets the value of section `section` and key `key`, both lowercased, and may create a new section or key. The source is `env:` followed by the full variable name, for example `env:APP_SERVER__PORT`.
- A variable qualifies only if, after the `APP_` prefix, it contains exactly one `__` and both parts are non-empty. Every other variable is ignored, for example `OTHER=1`.

## Interpolation

Interpolation runs after the layers are merged, so lookups see the overridden values.

- `${key}` refers to `key` in the same section.
- `${section:key}` refers to `key` in `section`.
- `$$` is a literal `$`, so `price = $$5` gives `$5`. Any other `$` is kept as it is.
- The name inside the braces is used exactly as written.
- The value being looked up is resolved first (recursively), and its result is substituted.
- Keys are resolved in sorted order of (section, key).
- An unknown reference raises `unknown reference ${x} in [s] k`, where `x` is the text as written, and `s` and `k` are the section and key that contain the lookup.
- A cycle raises `reference cycle: s.a -> s.b -> s.a`. The chain starts at the first key that repeats and ends with the same key again; names are written as `section.key`, joined by ` -> `.

Worked example:

    defaults = {"server": {"port": "8080", "host": "localhost"}}
    text     = "[server]\nhost = example.org\nurl = http://${host}:${port}\n"
    env      = {"APP_SERVER__PORT": "9000"}

Result:

- `server.host` is `example.org`, source `file:2`
- `server.port` is `9000`, source `env:APP_SERVER__PORT`
- `server.url` is `http://example.org:9000`, source `file:3`

## Typed access

`Config` offers these methods. Values are the resolved strings.

- `get(section, key) -> str`: the value. If the key does not exist, raise `missing [s] k`.
- `get_int(section, key) -> int`: the value converted with `int()`. On failure raise `[s] k: not an integer: 'v' (from SOURCE)`, where `v` is the resolved value and `SOURCE` is its source.
- `get_bool(section, key) -> bool`: `true`, `yes`, `on` and `1` give True; `false`, `no`, `off` and `0` give False. Matching ignores case. On any other value raise `[s] k: not a boolean: 'v' (from SOURCE)`.
- `get_list(section, key) -> list[str]`: split the value on commas and newlines, strip each item, and drop empty items.
- `source(section, key) -> str`: the source label of the value.
