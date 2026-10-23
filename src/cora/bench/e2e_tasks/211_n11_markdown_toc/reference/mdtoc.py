import re

_HEADING = re.compile(r"^(#{1,6}) (.*)$")


def slug(heading: str) -> str:
    kept = "".join(c for c in heading.lower() if c.isalnum() or c in " -_")
    return kept.replace(" ", "-")


def _headings(markdown: str):
    fence = None
    for line in markdown.splitlines():
        if fence is not None:
            if line.startswith(fence):
                fence = None
            continue
        if line.startswith("```") or line.startswith("~~~"):
            fence = line[:3]
            continue
        match = _HEADING.match(line)
        if match:
            text = re.sub(r" +#+$", "", match.group(2).strip())
            text = text.replace("`", "").strip()
            yield len(match.group(1)), text


def toc(markdown: str, min_level: int = 1, max_level: int = 3) -> str:
    if not 1 <= min_level <= 6 or not 1 <= max_level <= 6 or min_level > max_level:
        raise ValueError(f"invalid level range: {min_level}..{max_level}")
    seen = {}
    lines = []
    for level, text in _headings(markdown):
        base = slug(text)
        count = seen.get(base, 0)
        seen[base] = count + 1
        anchor = base if count == 0 else f"{base}-{count}"
        if min_level <= level <= max_level:
            lines.append("  " * (level - min_level) + f"- [{text}](#{anchor})\n")
    return "".join(lines)
