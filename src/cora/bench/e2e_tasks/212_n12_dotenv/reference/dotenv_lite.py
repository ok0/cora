"""Read and write simple .env files."""

import re


def dump(d: dict[str, str]) -> str:
    return "".join(f"{k}={v}\n" for k, v in d.items())


_ESCAPES = {"n": "\n", '"': '"', "\\": "\\"}


def _unescape(s: str) -> str:
    return re.sub(r'\\([n"\\])', lambda m: _ESCAPES[m.group(1)], s)


def parse(text: str) -> dict[str, str]:
    """Parse .env text into a dict of key/value pairs, following REQUIREMENTS.md."""
    result: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            raise ValueError(f"line {number}: missing '='")
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"line {number}: empty key")
        value = value.strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = _unescape(value[1:-1])
        elif len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1]
        else:
            idx = value.find(" #")
            if idx != -1:
                value = value[:idx].rstrip()
        result[key] = value
    return result
