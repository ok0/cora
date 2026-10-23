import re

from layercfg.errors import ConfigError

_TOKEN = re.compile(r"\$\$|\$\{([^}]*)\}")


def resolve(
    merged: dict[str, dict[str, tuple[str, str]]],
) -> dict[str, dict[str, tuple[str, str]]]:
    cache: dict[tuple[str, str], tuple[str, str]] = {}

    def lookup(ident: tuple[str, str], stack: list[tuple[str, str]]) -> tuple[str, str]:
        if ident in cache:
            return cache[ident]
        if ident in stack:
            chain = stack[stack.index(ident):] + [ident]
            raise ConfigError("reference cycle: " + " -> ".join(f"{s}.{k}" for s, k in chain))
        section, key = ident
        raw, source = merged[section][key]
        inner = stack + [ident]

        def sub(match: re.Match[str]) -> str:
            if match.group(0) == "$$":
                return "$"
            ref = match.group(1)
            if ":" in ref:
                ref_section, ref_key = ref.split(":", 1)
            else:
                ref_section, ref_key = section, ref
            if ref_section not in merged or ref_key not in merged[ref_section]:
                raise ConfigError(f"unknown reference ${{{ref}}} in [{section}] {key}")
            return lookup((ref_section, ref_key), inner)[0]

        text = _TOKEN.sub(sub, raw)
        cache[ident] = (text, source)
        return cache[ident]

    out: dict[str, dict[str, tuple[str, str]]] = {}
    for section in sorted(merged):
        for key in sorted(merged[section]):
            out.setdefault(section, {})[key] = lookup((section, key), [])
    return out
