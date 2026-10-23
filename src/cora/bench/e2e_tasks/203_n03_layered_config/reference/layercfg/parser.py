from layercfg.errors import ConfigError


def parse(text: str) -> dict[str, dict[str, tuple[str, int]]]:
    result: dict[str, dict[str, tuple[str, int]]] = {}
    section: str | None = None
    last: tuple[str, str] | None = None
    for lineno, raw in enumerate(text.split("\n"), start=1):
        stripped = raw.strip()
        if not stripped or stripped[0] in "#;":
            continue
        if raw[0] in " \t":
            if last is None:
                raise ConfigError(f"line {lineno}: cannot parse")
            sec, key = last
            value, first_line = result[sec][key]
            result[sec][key] = (value + "\n" + stripped, first_line)
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            result.setdefault(section, {})
            last = None
            continue
        if "=" in stripped:
            if section is None:
                raise ConfigError(f"line {lineno}: key outside section")
            key, value = stripped.split("=", 1)
            key = key.strip().lower()
            if key in result[section]:
                raise ConfigError(f"line {lineno}: duplicate key '{key}' in [{section}]")
            result[section][key] = (value.strip(), lineno)
            last = (section, key)
            continue
        raise ConfigError(f"line {lineno}: cannot parse")
    return result
