PREFIX = "APP_"


def merge(
    defaults: dict[str, dict[str, str]],
    parsed: dict[str, dict[str, tuple[str, int]]],
    env: dict[str, str],
) -> dict[str, dict[str, tuple[str, str]]]:
    merged: dict[str, dict[str, tuple[str, str]]] = {}
    for section, keys in defaults.items():
        for key, value in keys.items():
            merged.setdefault(section, {})[key] = (value, "default")
    for section, keys in parsed.items():
        for key, (value, lineno) in keys.items():
            merged.setdefault(section, {})[key] = (value, f"file:{lineno}")
    for name, value in env.items():
        if not name.startswith(PREFIX):
            continue
        body = name[len(PREFIX):]
        if body.count("__") != 1:
            continue
        section, key = body.split("__")
        if not section or not key:
            continue
        merged.setdefault(section.lower(), {})[key.lower()] = (value, f"env:{name}")
    return merged
